import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql"


@pytest.fixture(scope="module")
def database():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN must point to a disposable PostgreSQL server")
    name = f"us12_2_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        for role in ("anon", "authenticated", "service_role"):
            if not admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                admin.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(
                make_conninfo(dsn, dbname=name), autocommit=True, row_factory=dict_row
            ) as connection:
                for filename in (
                    "SUPABASE_SETUP.sql",
                    "SUPABASE_ADD_COORDINATOR_ASSIGNMENT.sql",
                    "SUPABASE_ADD_EQUIPMENT_REQUESTS.sql",
                    "SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql",
                ):
                    connection.execute((ROOT / filename).read_text())
                connection.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'Expired'")
                connection.execute("""
                    INSERT INTO users (id, name, email, role) VALUES
                        (101, 'Coordinator', 'coordinator@test.invalid', 'Event Coordinator'),
                        (102, 'Staff', 'staff@test.invalid', 'Venue Staff');
                    INSERT INTO venues (id, name, location, capacity, setup_minutes,
                                        turnaround_minutes) VALUES
                        (101, 'Test Hall', 'Campus', 100, 30, 30),
                        (102, 'Other Hall', 'Campus', 100, 0, 0);
                    INSERT INTO events (id, name, organiser_id, coordinator_id) VALUES
                        (101, 'Assigned Event', 101, 101),
                        (102, 'Unassigned Event', 101, NULL),
                        (103, 'Second Event', 101, 101);
                    INSERT INTO venue_unavailability (venue_id, start_date, end_date, reason)
                    VALUES (101, '2020-01-01', '2020-01-01', 'Legacy closure'),
                           (101, '2020-02-01', '2020-02-01', '   ');
                """)
                connection.execute(MIGRATION.read_text())
                connection.execute(MIGRATION.read_text())
                yield connection
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def db(database):
    with database.transaction(force_rollback=True):
        yield database


def book(db, *, status="Requested", event_id=101, venue_id=101,
         start="2035-11-11 10:00", end="2035-11-11 12:00", expired=False):
    return db.execute("""
        INSERT INTO venue_bookings (
            event_id, venue_id, start_at, end_at, status, requested_by_id,
            decided_at, decided_by_id, rejection_reason,
            cancelled_at, cancellation_reason, cancelled_by_id, hold_expires_at
        ) VALUES (
            %(event)s, %(venue)s, %(start)s, %(end)s, %(status)s, 101,
            CASE WHEN %(status)s IN ('Confirmed', 'Rejected') THEN now() END,
            CASE WHEN %(status)s IN ('Confirmed', 'Rejected') THEN 102 END,
            CASE WHEN %(status)s = 'Rejected' THEN 'Unsuitable' END,
            CASE WHEN %(status)s = 'Cancelled' THEN now() END,
            CASE WHEN %(status)s = 'Cancelled' THEN 'Cancelled by organiser' END,
            CASE WHEN %(status)s = 'Cancelled' THEN 101 END,
            CASE WHEN %(status)s = 'Held'
                THEN timezone('UTC', now()) + %(expiry)s::interval END
        ) RETURNING id
    """, dict(event=event_id, venue=venue_id, start=start, end=end, status=status,
              expiry="-1 day" if expired else "1 day")).fetchone()["id"]


def close_venue(db, reason="maintenance", other=None):
    return db.execute("""
        INSERT INTO venue_unavailability
            (venue_id, start_date, end_date, reason_type, other_reason, created_by_id)
        VALUES (101, '2035-11-10', '2035-11-12', %s, %s, 102) RETURNING id
    """, (reason, other)).fetchone()["id"]


def test_migration_preserves_legacy_reasons_and_is_rerunnable(db):
    rows = db.execute("""
        SELECT reason_type, other_reason FROM venue_unavailability ORDER BY start_date
    """).fetchall()
    assert rows == [
        dict(reason_type="other", other_reason="Legacy closure"),
        dict(reason_type="other", other_reason="Venue unavailable"),
    ]


def test_active_bookings_flagged_once_and_decisions_preserved(db):
    active = [book(db, status=status) for status in ("Requested", "Held", "Confirmed")]
    active.append(book(db, event_id=102))
    active.append(book(db, event_id=103))
    unchanged = [book(db, status=status) for status in ("Cancelled", "Rejected", "Expired")]
    unchanged += [book(db, status="Held", expired=True), book(db, venue_id=102),
                  book(db, start="2035-11-20 10:00", end="2035-11-20 12:00")]
    blackout_id = close_venue(db)
    rows = db.execute("SELECT * FROM venue_bookings ORDER BY id").fetchall()
    assert {row["id"] for row in rows if row["status"] == "Needs replacement"} == set(active)
    assert all(row["flagged_by_unavailability_id"] is None
               for row in rows if row["id"] in unchanged)
    assert all(row["flagged_by_unavailability_id"] == blackout_id
               and row["replacement_reason"] == "scheduled maintenance"
               for row in rows if row["id"] in active)
    confirmed = next(row for row in rows if row["id"] == active[2])
    assert confirmed["decided_at"] is not None
    assert confirmed["decided_by_id"] == 102
    notices = db.execute("SELECT * FROM notifications ORDER BY event_id").fetchall()
    assert [row["event_id"] for row in notices] == [101, 103]
    assert all(row["user_id"] == 101 and row["kind"] == "booking-conflict"
               and row["status"] is None and not row["is_read"] for row in notices)
    assert all("Test Hall" in row["message"] and "scheduled maintenance" in row["message"]
               and "10 Nov 2035" in row["message"] and "12 Nov 2035" in row["message"]
               for row in notices)
    close_venue(db)
    assert db.execute("SELECT count(*) AS total FROM notifications").fetchone()["total"] == 2


def test_setup_turnaround_overlap_excludes_exact_midnight_boundaries(db):
    overlaps = [
        book(db, start="2035-11-13 00:29", end="2035-11-13 02:00"),
        book(db, start="2035-11-09 20:00", end="2035-11-09 23:31"),
    ]
    book(db, start="2035-11-13 00:30", end="2035-11-13 02:00")
    book(db, start="2035-11-09 20:00", end="2035-11-09 23:30")
    close_venue(db)
    rows = db.execute(
        "SELECT id FROM venue_bookings WHERE status = 'Needs replacement'"
    ).fetchall()
    assert {row["id"] for row in rows} == set(overlaps)


@pytest.mark.parametrize(("reason", "other", "label"), [
    ("other", "Unexpected flooding", "Unexpected flooding"),
    ("equipment_failure", None, "equipment failure"),
    ("renovation", None, "renovation work"),
    ("safety_concern", None, "safety concern"),
])
def test_reason_reaches_booking_and_notification(db, reason, other, label):
    booking_id = book(db)
    close_venue(db, reason, other)
    assert db.execute("SELECT replacement_reason FROM venue_bookings WHERE id = %s",
                      (booking_id,)).fetchone()["replacement_reason"] == label
    assert label in db.execute("SELECT message FROM notifications").fetchone()["message"]
