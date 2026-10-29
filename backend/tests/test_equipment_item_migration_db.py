"""Run the real exact-item migration in an isolated, rolled-back schema.

Opt in with US19_DB_TEST_URL pointing to a disposable PostgreSQL database whose
user may create schemas. No application rows are read or changed. Production
trigger definitions are loaded from the prerequisite migration files.
"""

import os
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
URL = os.getenv("US19_DB_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires disposable US19_DB_TEST_URL")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database():
    schema = "us19_migration_" + uuid4().hex
    with psycopg.connect(URL) as db:

        def local(sql):
            return sql.replace("public.", schema + ".").replace(
                "search_path = public", "search_path = " + schema
            )

        db.execute(f"CREATE SCHEMA {schema}")
        db.execute(f"SET LOCAL search_path = {schema}")
        db.execute("""
            CREATE TYPE event_status AS ENUM
              ('Planning','Pending Safety Check','Confirmed','Completed','Cancelled');
            CREATE TABLE events (id INTEGER PRIMARY KEY, status event_status NOT NULL);
            CREATE TABLE equipment (id INTEGER PRIMARY KEY, name TEXT, equipment_type TEXT,
                location TEXT, total_quantity INTEGER, out_of_service_quantity INTEGER);
            CREATE TABLE equipment_requests (
                id INTEGER PRIMARY KEY, event_id INTEGER REFERENCES events(id),
                equipment_id INTEGER REFERENCES equipment(id), equipment_type TEXT,
                quantity INTEGER CHECK(quantity > 0), technical_requirements TEXT DEFAULT '',
                support_notes TEXT DEFAULT '', start_at TIMESTAMP, end_at TIMESTAMP,
                status TEXT, unavailable_reason TEXT DEFAULT '', requested_by_id INTEGER,
                updated_by_id INTEGER, version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT '2026-10-01',
                updated_at TIMESTAMP DEFAULT '2026-10-01');
            CREATE TABLE equipment_request_history (
                request_id INTEGER, event_id INTEGER, actor_id INTEGER, action TEXT,
                before_data JSONB, after_data JSONB);
            INSERT INTO equipment VALUES (1,'Projector','Projector','Store',10,2),
                (2,'Other projector','Projector','Store',5,0);
            INSERT INTO events VALUES (1,'Planning'),(2,'Pending Safety Check'),
                (3,'Confirmed'),(4,'Completed'),(5,'Cancelled');
            INSERT INTO equipment_requests(id,event_id,equipment_id,equipment_type,quantity,
                start_at,end_at,status,updated_by_id)
                SELECT id,id,1,'Projector',1,'2030-01-01 09:00','2030-01-01 17:00',
                    CASE WHEN id=5 THEN 'Removed' ELSE 'Reserved' END,42 FROM events;
            INSERT INTO equipment_requests
                (id,event_id,equipment_type,quantity,start_at,end_at,status)
                VALUES (6,1,'Projector',1,'2030-01-01 09:00','2030-01-01 17:00','Requested');
        """)
        original = (ROOT / "SUPABASE_ADD_EQUIPMENT_REQUESTS.sql").read_text()
        audit = original.split("CREATE OR REPLACE FUNCTION public.equipment_request_snapshot", 1)[1]
        audit = "CREATE OR REPLACE FUNCTION public.equipment_request_snapshot" + audit
        audit = audit.split("-- Serialize request writes", 1)[0]
        db.execute(local(audit))
        cancellation = (ROOT / "SUPABASE_US4_6_CANCEL_EVENT.sql").read_text()
        guard = cancellation.split(
            "CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()", 1
        )[1].split("-- 4.", 1)[0]
        db.execute(
            local(
                "CREATE OR REPLACE FUNCTION public.require_planning_for_equipment_request()" + guard
            )
        )
        db.execute("""
            CREATE TRIGGER require_planning_for_equipment_request
                BEFORE INSERT OR UPDATE ON equipment_requests
                FOR EACH ROW EXECUTE FUNCTION require_planning_for_equipment_request();
        """)
        migration = (ROOT / "SUPABASE_US19_EXACT_ITEM_REQUESTS.sql").read_text()
        # Let pytest's outer transaction own rollback, including all migration DDL.
        migration = migration.replace("BEGIN;", "", 1).replace("COMMIT;", "", 1)
        try:
            yield db, local, migration, schema
        finally:
            db.rollback()


def triggers(db, schema):
    return db.execute(
        "SELECT tgname,tgenabled FROM pg_trigger WHERE tgrelid=%s::regclass "
        "AND NOT tgisinternal ORDER BY tgname",
        (schema + ".equipment_requests",),
    ).fetchall()


def rows(db):
    return db.execute(
        "SELECT to_jsonb(r) - 'requested_equipment_id' FROM equipment_requests r ORDER BY id"
    ).fetchall()


def test_backfill_preserves_history_and_restores_guards(database):
    db, local, migration, schema = database
    before = rows(db)
    expected_triggers = triggers(db, schema)
    db.execute(local(migration))
    assert rows(db) == before  # Times, statuses, quantities, actors, versions unchanged.
    assert db.execute(
        "SELECT requested_equipment_id FROM equipment_requests ORDER BY id"
    ).fetchall() == [(1,), (1,), (1,), (1,), (1,), (None,)]
    assert db.execute("SELECT count(*) FROM equipment_request_history").fetchone()[0] == 0
    assert triggers(db, schema) == expected_triggers
    # Do not overwrite a Coordinator selection or duplicate history on a rerun.
    db.execute("UPDATE equipment_requests SET requested_equipment_id=2 WHERE id=1")
    db.execute(local(migration))
    assert db.execute(
        "SELECT requested_equipment_id FROM equipment_requests WHERE id=1"
    ).fetchone() == (2,)
    assert db.execute("SELECT count(*) FROM equipment_request_history").fetchone()[0] == 1
    for request_id in (2, 3, 4, 5):
        with pytest.raises(psycopg.errors.RaiseException, match="only change while"):
            with db.transaction():
                db.execute("UPDATE equipment_requests SET quantity=2 WHERE id=%s", (request_id,))
    # Normal Planning edits still succeed and the audit trigger still records them.
    db.execute("UPDATE equipment_requests SET quantity=2 WHERE id=1")
    assert db.execute("SELECT count(*) FROM equipment_request_history").fetchone()[0] == 2
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with db.transaction():
            db.execute("UPDATE equipment_requests SET requested_equipment_id=999 WHERE id=1")


def test_backfill_failure_rolls_back_data_column_and_trigger_state(database):
    db, local, migration, schema = database
    before, expected_triggers = rows(db), triggers(db, schema)
    # Fail after data backfill but before either trigger is restored.
    broken = migration.replace(
        "ALTER TABLE public.equipment_requests ENABLE TRIGGER record_equipment_request_history;",
        "SELECT 1/0;",
        1,
    )
    with pytest.raises(psycopg.errors.DivisionByZero):
        with db.transaction():
            db.execute(local(broken))
    assert rows(db) == before
    assert triggers(db, schema) == expected_triggers
    assert not db.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema=%s "
        "AND table_name='equipment_requests' AND column_name='requested_equipment_id'",
        (schema,),
    ).fetchall()
    assert db.execute("SELECT count(*) FROM equipment_request_history").fetchone()[0] == 0


@pytest.mark.parametrize("partial", [False, True])
def test_notice_repair_preserves_old_kinds_and_is_repeatable(database, partial):
    db, local, _, _ = database
    db.execute("CREATE TABLE notifications(kind TEXT, status TEXT, equipment_request_id INTEGER)")
    existing = (
        "(kind='event-status' AND status IS NOT NULL AND equipment_request_id IS NULL) OR "
        "(kind IN ('booking-confirmed','safety-rejected') AND status IS NULL "
        "AND equipment_request_id IS NULL)"
    )
    if partial:
        existing += " OR (kind='equipment-reserved' AND status IS NULL "
        existing += "AND equipment_request_id IS NULL)"
    db.execute(
        "ALTER TABLE notifications ADD CONSTRAINT notifications_kind_valid CHECK (" + existing + ")"
    )
    db.execute(
        "INSERT INTO notifications VALUES ('event-status','Confirmed',NULL), "
        "('booking-confirmed',NULL,NULL),('safety-rejected',NULL,NULL)"
    )
    repair = (ROOT / "SUPABASE_US19_REPAIR_EQUIPMENT_NOTICES.sql").read_text()
    repair = repair.replace("BEGIN;", "", 1).replace("COMMIT;", "", 1)
    db.execute(local(repair))
    db.execute(local(repair))
    db.execute(
        "INSERT INTO notifications VALUES ('equipment-reserved',NULL,NULL), "
        "('equipment-unavailable',NULL,NULL),('booking-confirmed',NULL,NULL)"
    )
    assert db.execute("SELECT count(*) FROM notifications").fetchone()[0] == 6
    for kind, status, request_id in [
        ("unknown-kind", None, None),
        ("equipment-reserved", "Confirmed", None),
        ("equipment-unavailable", None, 1),
        ("event-status", None, None),
    ]:
        with pytest.raises(psycopg.errors.CheckViolation):
            with db.transaction():
                db.execute(
                    "INSERT INTO notifications VALUES (%s,%s,%s)", (kind, status, request_id)
                )
