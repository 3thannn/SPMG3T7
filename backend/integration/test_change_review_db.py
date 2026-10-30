"""Run US11.2's real migration twice and race its revision-checked RPCs.

TEST_POSTGRES_DSN must point to disposable PostgreSQL. Each test owns a unique
schema; no application schema or data is touched.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("requires disposable TEST_POSTGRES_DSN")
    schema = "us11_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as db:
        for role in ("anon", "authenticated", "service_role"):
            if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                db.execute(f"CREATE ROLE {role}")
        db.execute(f"CREATE SCHEMA {schema}")
        db.execute(f"SET search_path={schema}")
        db.execute("""
            CREATE TYPE event_status AS ENUM ('Draft','Submitted','Under Review','Approved',
                'Planning','Pending Safety Check','Confirmed','Rejected','Completed','Cancelled');
            CREATE TYPE change_type AS ENUM ('important','routine');
            CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE events(id INTEGER PRIMARY KEY,name TEXT,purpose TEXT,description TEXT,
                proposed_date TIMESTAMP,end_date TIMESTAMP,expected_attendance INTEGER,
                venue_requirements TEXT,preferred_layout TEXT,accessibility_needs TEXT,
                equipment_needs TEXT,registration_needs TEXT,status event_status,
                organiser_id INTEGER,coordinator_id INTEGER,updated_at TIMESTAMP);
            CREATE TABLE event_change_requests(id SERIAL PRIMARY KEY,event_id INTEGER,
                changed_field TEXT,old_value TEXT,new_value TEXT,change_type TEXT,
                requested_by_user_id INTEGER,requested_at TIMESTAMP,request_note TEXT,
                status TEXT DEFAULT 'pending',reviewed_at TIMESTAMP,
                reviewed_by_user_id INTEGER,review_note TEXT);
            CREATE TABLE event_changes(id SERIAL PRIMARY KEY,event_id INTEGER,changed_field TEXT,
                old_value TEXT,new_value TEXT,change_type change_type,
                changed_by_user_id INTEGER,changed_at TIMESTAMP);
            CREATE TABLE status_changes(event_id INTEGER,old_status event_status,
                new_status event_status,changed_by_id INTEGER,changed_at TIMESTAMP,notes TEXT);
            CREATE TABLE venue_bookings(id INTEGER PRIMARY KEY,event_id INTEGER,status TEXT,
                start_at TIMESTAMP,end_at TIMESTAMP,headcount INTEGER,hold_expires_at TIMESTAMP,
                conflict_flagged_at TIMESTAMP);
            CREATE TABLE safety_review_flags(event_id INTEGER,resolved_at TIMESTAMP);
            CREATE TABLE equipment(id INTEGER PRIMARY KEY,name TEXT,location TEXT,
                total_quantity INTEGER,out_of_service_quantity INTEGER);
            CREATE TABLE equipment_requests(id INTEGER,event_id INTEGER,status TEXT,
                quantity INTEGER,version INTEGER DEFAULT 1,
                equipment_id INTEGER,requested_equipment_id INTEGER,
                start_at TIMESTAMP,end_at TIMESTAMP);
            CREATE TABLE notifications(kind TEXT,status TEXT,
                equipment_request_id INTEGER,
                CONSTRAINT notifications_kind_valid CHECK(kind='assigned'));
            CREATE FUNCTION record_equipment_request_history() RETURNS TRIGGER LANGUAGE plpgsql
                AS $$ BEGIN RETURN NEW; END $$;
            INSERT INTO users VALUES(1,'Organiser'),(2,'Coordinator');
            INSERT INTO events(id,name,status,organiser_id,coordinator_id,updated_at)
                VALUES(1,'Original','Confirmed',1,2,'2026-10-30');
        """)
        guard = (ROOT / "SUPABASE_US4_6_CANCEL_EVENT.sql").read_text(encoding="utf-8")
        guard = (
            "CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()"
            + guard.split(
                "CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()", 1
            )[1].split("-- 4.", 1)[0]
        )
        db.execute(guard.replace("public.", schema + "."))
        db.execute("""CREATE TRIGGER require_planning_for_equipment_request
            BEFORE INSERT OR UPDATE ON equipment_requests FOR EACH ROW
            EXECUTE FUNCTION require_planning_for_equipment_request()""")
        migration = (ROOT / "SUPABASE_US11_2_CHANGE_REVIEW.sql").read_text(encoding="utf-8")
        migration = migration.replace("public.", schema + ".").replace(
            "search_path = public", "search_path = " + schema
        )
        fixes = (ROOT / "SUPABASE_US11_2_REVIEW_FIXES.sql").read_text(encoding="utf-8")
        fixes = fixes.replace("public.", schema + ".")
        try:
            db.execute(migration)
            db.execute(migration)
            db.execute(fixes)
            db.execute(fixes)
            yield db, dsn, schema
        finally:
            db.execute("SET search_path=public")
            db.execute(f"DROP SCHEMA {schema} CASCADE")


def proposal(value="Revised"):
    return {
        "note": "Amended",
        "changes": [
            {
                "changed_field": "name",
                "old_value": "Original",
                "new_value": value,
                "change_type": "routine",
            }
        ],
    }


def review(db, actor, action, revision, payload):
    return db.execute(
        "SELECT us11_review(1,%s,%s,%s,%s)", (actor, action, revision, Jsonb(payload))
    ).fetchone()[0]


def test_revisions_history_and_concurrent_decisions(database):
    db, dsn, schema = database
    assert review(db, 1, "submit", 0, proposal())
    assert review(db, 2, "clarify", 1, {"message": "Use another title"})
    assert review(db, 1, "submit", 2, proposal("Final"))
    assert not review(db, 2, "approve", 1, {})

    def approve():
        with psycopg.connect(dsn, autocommit=True) as other:
            other.execute(f"SET search_path={schema}")
            return review(other, 2, "approve", 3, {})

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: approve(), range(2))) == [False, True]
    assert db.execute("SELECT name,status FROM events").fetchone() == ("Final", "Confirmed")
    assert db.execute("SELECT count(*) FROM event_changes").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT count(*) FROM event_change_requests WHERE status='superseded'"
        ).fetchone()[0]
        == 1
    )
    state = db.execute("SELECT review_state FROM events").fetchone()[0]
    assert len(state["messages"]) == 4


def test_reject_assignment_and_transaction_rollback(database):
    db, _, _ = database
    assert review(db, 1, "submit", 0, proposal())
    assert not review(db, 9, "approve", 1, {})
    assert not review(db, 2, "reject", 1, {"note": " "})
    with pytest.raises(psycopg.Error):
        with db.transaction():
            assert review(db, 2, "approve", 1, {})
            db.execute("SELECT 1/0")
    assert db.execute("SELECT name FROM events").fetchone()[0] == "Original"
    assert review(db, 2, "reject", 1, {"note": "Keep the title"})
    assert db.execute("SELECT count(*) FROM event_changes").fetchone()[0] == 0


def test_submission_preserves_each_proposed_field_and_accepts_them_together(database):
    db, _, _ = database
    payload = proposal()
    payload["changes"].append(
        {
            "changed_field": "expected_attendance",
            "old_value": "",
            "new_value": "40",
            "change_type": "important",
        }
    )
    assert review(db, 1, "submit", 0, payload)
    assert db.execute("""SELECT changed_field,old_value,new_value,change_type,
        requested_by_user_id,request_note,status FROM event_change_requests
        ORDER BY changed_field""").fetchall() == [
        ("expected_attendance", "", "40", "important", 1, "Amended", "pending"),
        ("name", "Original", "Revised", "routine", 1, "Amended", "pending"),
    ]
    assert db.execute("SELECT name,expected_attendance,status FROM events").fetchone() == (
        "Original", None, "Confirmed"
    )
    assert review(db, 2, "approve", 1, {})
    assert db.execute("SELECT name,expected_attendance,status FROM events").fetchone() == (
        "Revised", 40, "Confirmed"
    )
    assert db.execute("""SELECT changed_field,new_value,change_type::TEXT,changed_by_user_id
        FROM event_changes ORDER BY changed_field""").fetchall() == [
        ("expected_attendance", "40", "important", 2),
        ("name", "Revised", "routine", 2),
    ]
    assert db.execute("SELECT status FROM event_change_requests").fetchall() == [
        ("approved",), ("approved",)
    ]
    assert db.execute("SELECT arrangement_review_pending FROM events").fetchone()[0]


def test_direct_edit_marker_and_sgt_timestamp(database):
    db, _, _ = database
    changes = Jsonb(
        [
            {
                "changed_field": "proposed_date",
                "old_value": "",
                "new_value": "2027-01-01T00:30",
                "change_type": "important",
            }
        ]
    )
    assert db.execute("SELECT us11_edit(1,2,'2026-10-30',%s)", (changes,)).fetchone()[0]
    assert db.execute(
        "SELECT proposed_date::TEXT,arrangement_review_pending,status FROM events"
    ).fetchone() == (
        "2027-01-01 00:30:00",
        True,
        "Confirmed",
    )
    assert not db.execute("SELECT us11_edit(1,2,'2026-10-30',%s)", (changes,)).fetchone()[0]
    content_version = db.execute("SELECT updated_at FROM events").fetchone()[0]
    db.execute("UPDATE events SET arrangement_review='[]', arrangement_review_pending=FALSE")
    assert db.execute("SELECT updated_at FROM events").fetchone()[0] == content_version


def test_equipment_metadata_allowed_after_planning_but_content_is_guarded(database):
    db, _, _ = database
    db.execute("UPDATE events SET status='Planning'")
    db.execute("INSERT INTO equipment VALUES(1,'Projector','Store',2,0)")
    db.execute("""INSERT INTO equipment_requests(id,event_id,status,quantity,equipment_id,
        requested_equipment_id,start_at,end_at)
        VALUES(1,1,'Reserved',2,1,1,'2027-01-01 00:00','2027-01-01 01:00')""")
    db.execute("UPDATE events SET status='Confirmed'")
    db.execute("UPDATE equipment_requests SET event_conflict_reason='Review needed'")
    assert db.execute("SELECT shortfall FROM equipment_availability(1)").fetchone()[0] == 0
    with pytest.raises(psycopg.Error):
        db.execute("UPDATE equipment_requests SET quantity=3")


def arrangement_fixture(db):
    db.execute("UPDATE events SET status='Planning',arrangement_review_pending=TRUE")
    db.execute("""INSERT INTO venue_bookings(id,event_id,status,start_at,end_at,headcount)
        VALUES(1,1,'Confirmed','2027-11-02 18:00','2027-11-02 21:00',40)""")
    db.execute("INSERT INTO equipment VALUES(1,'Projector','Store',2,0)")
    db.execute("""INSERT INTO equipment_requests(id,event_id,status,quantity,equipment_id,
        requested_equipment_id,start_at,end_at)
        VALUES(1,1,'Reserved',1,1,1,'2027-11-02 18:00','2027-11-02 21:00')""")
    return db.execute("SELECT updated_at FROM events").fetchone()[0]


def commit_review(db, version, reason, pending=False):
    return db.execute(
        "SELECT us11_commit_arrangement_review(1,%s,%s,%s,%s,%s)",
        (
            version,
            Jsonb([{"reason": reason}]),
            pending,
            Jsonb(
                [
                    {
                        "id": 1,
                        "reason": reason,
                        "status": "Confirmed",
                        "headcount": 40,
                        "startsAt": "2027-11-02T18:00",
                        "endsAt": "2027-11-02T21:00",
                    }
                ]
            ),
            Jsonb([{"id": 1, "reason": reason, "status": "Reserved", "version": 1}]),
        ),
    ).fetchone()[0]


@pytest.mark.parametrize("old_reason,new_reason", [("Old failure", ""), ("", "New failure")])
def test_stale_check_cannot_publish_any_flags_or_report(database, old_reason, new_reason):
    db, _, _ = database
    old_version = arrangement_fixture(db)
    db.execute("UPDATE events SET expected_attendance=40")
    new_version = db.execute("SELECT updated_at FROM events").fetchone()[0]
    assert commit_review(db, new_version, new_reason)
    assert not commit_review(db, old_version, old_reason)
    assert (
        db.execute("SELECT event_conflict_reason FROM venue_bookings").fetchone()[0] == new_reason
    )
    assert (
        db.execute("SELECT event_conflict_reason FROM equipment_requests").fetchone()[0]
        == new_reason
    )
    assert db.execute("SELECT arrangement_review FROM events").fetchone()[0] == [
        {"reason": new_reason}
    ]
    assert not db.execute("SELECT arrangement_review_pending FROM events").fetchone()[0]


def test_arrangement_snapshot_must_still_match_before_any_flag_write(database):
    db, _, _ = database
    version = arrangement_fixture(db)
    db.execute("UPDATE equipment_requests SET version=2")
    assert not commit_review(db, version, "Stale failure")
    assert db.execute("SELECT event_conflict_reason FROM venue_bookings").fetchone()[0] == ""
    assert db.execute("SELECT event_conflict_reason FROM equipment_requests").fetchone()[0] == ""
    assert db.execute("SELECT arrangement_review_pending FROM events").fetchone()[0]


@pytest.mark.parametrize("failure", ["venue", "equipment", "pending"])
def test_sql_safety_guard_rechecks_event_conflicts(database, failure):
    db, _, _ = database
    version = arrangement_fixture(db)
    assert commit_review(db, version, "")
    if failure == "venue":
        db.execute("UPDATE venue_bookings SET event_conflict_reason='Over capacity'")
    elif failure == "equipment":
        db.execute("UPDATE equipment_requests SET event_conflict_reason='Stock shortfall'")
    else:
        db.execute("UPDATE events SET arrangement_review_pending=TRUE")
    assert not db.execute("SELECT send_event_to_safety_check(1,2)").fetchone()[0]
    assert db.execute("SELECT status FROM events").fetchone()[0] == "Planning"
    db.execute("UPDATE venue_bookings SET event_conflict_reason=''")
    db.execute("UPDATE equipment_requests SET event_conflict_reason=''")
    db.execute("UPDATE events SET arrangement_review_pending=FALSE")
    assert db.execute("SELECT send_event_to_safety_check(1,2)").fetchone()[0]


def test_sql_reservation_peak_demand(database):
    db, _, _ = database
    arrangement_fixture(db)
    db.execute("""INSERT INTO equipment_requests(id,event_id,status,quantity,equipment_id,
        requested_equipment_id,start_at,end_at) VALUES
        (2,1,'Reserved',1,1,1,'2027-11-02 18:00','2027-11-02 19:00'),
        (3,1,'Reserved',1,1,1,'2027-11-02 19:00','2027-11-02 20:00')""")
    assert (
        db.execute("SELECT shortfall FROM equipment_reservation_availability(1)").fetchone()[0] == 0
    )
    db.execute("UPDATE equipment_requests SET start_at='2027-11-02 18:59:59' WHERE id=3")
    assert (
        db.execute("SELECT shortfall FROM equipment_reservation_availability(1)").fetchone()[0] == 1
    )
