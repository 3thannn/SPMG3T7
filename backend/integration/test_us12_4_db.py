"""US12.4 in the database: SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql, then
SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql (Week 9, G12).

* A venue closure flags a Confirmed event's booking "Needs replacement" and
  moves the event back to Planning at once, with who closed the venue and why
  in status_changes; its Coordinator and its Organiser are told.
* us12_4_request_replacement replaces the booking through
  request_replacement_venue and, on a Confirmed event, moves it to Planning
  with the reason in status_changes, in one transaction.

request_replacement_venue is not in the repo (US14.5 created it on the live
database only), so this stands one in with the same arguments and answers:
the new booking's id, or NULL when the booking does not need replacing.
"""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql"
CLOSURE = ROOT / "SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql"

COORDINATOR, STAFF, ORGANISER = 101, 102, 103
HALL, OTHER_HALL = 101, 102
CONFIRMED_EVENT, PLANNING_EVENT, OWN_EVENT = 201, 202, 203
REASON = "Test Hall is unavailable, so Other Hall was requested instead."

STAND_IN = """
CREATE OR REPLACE FUNCTION public.request_replacement_venue(
    p_booking_id INTEGER, p_venue_id INTEGER, p_actor_id INTEGER
) RETURNS INTEGER LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_new INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.venue_bookings
        WHERE id = p_booking_id AND status::text = 'Needs replacement'
    ) THEN
        RETURN NULL;
    END IF;
    INSERT INTO public.venue_bookings (event_id, venue_id, start_at, end_at, requested_by_id)
    SELECT event_id, p_venue_id, start_at, end_at, p_actor_id
    FROM public.venue_bookings WHERE id = p_booking_id
    RETURNING id INTO v_new;
    UPDATE public.venue_bookings SET status = 'Replaced' WHERE id = p_booking_id;
    RETURN v_new;
END;
$$;
"""


@pytest.fixture(scope="module")
def database():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN must point to a disposable PostgreSQL server")
    name = f"us12_4_{uuid4().hex}"
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
                    "SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql",
                    "SUPABASE_US14_5_REPLACED_STATUS.sql",
                ):
                    connection.execute((ROOT / filename).read_text(encoding="utf-8"))
                connection.execute(STAND_IN)
                connection.execute(f"""
                    INSERT INTO users (id, name, email, role) VALUES
                        ({COORDINATOR}, 'Coordinator', 'coordinator@test.invalid',
                         'Event Coordinator'),
                        ({STAFF}, 'Staff', 'staff@test.invalid', 'Venue Staff'),
                        ({ORGANISER}, 'Organiser', 'organiser@test.invalid', 'Event Organiser');
                    INSERT INTO venues (id, name, location, capacity, setup_minutes,
                                        turnaround_minutes) VALUES
                        ({HALL}, 'Test Hall', 'Campus', 100, 0, 0),
                        ({OTHER_HALL}, 'Other Hall', 'Campus', 100, 0, 0);
                    INSERT INTO events (id, name, organiser_id, coordinator_id, status) VALUES
                        ({CONFIRMED_EVENT}, 'Open House', {ORGANISER}, {COORDINATOR},
                         'Confirmed'),
                        ({PLANNING_EVENT}, 'Planning Event', {ORGANISER}, {COORDINATOR},
                         'Planning'),
                        ({OWN_EVENT}, 'Own Event', {COORDINATOR}, {COORDINATOR}, 'Confirmed');
                """)
                # Twice: the script says it is safe to run repeatedly.
                connection.execute(MIGRATION.read_text(encoding="utf-8"))
                connection.execute(MIGRATION.read_text(encoding="utf-8"))
                connection.execute(CLOSURE.read_text(encoding="utf-8"))
                connection.execute(CLOSURE.read_text(encoding="utf-8"))
                yield connection
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def db(database):
    with database.transaction(force_rollback=True):
        yield database


def book(db, *, event_id=CONFIRMED_EVENT, venue_id=HALL, status="Confirmed",
         start="2035-11-11 10:00", end="2035-11-11 12:00"):
    return db.execute("""
        INSERT INTO venue_bookings (event_id, venue_id, start_at, end_at, status,
                                    requested_by_id, decided_at, decided_by_id)
        VALUES (%(event)s, %(venue)s, %(start)s, %(end)s, %(status)s::booking_status,
                %(coordinator)s,
                CASE WHEN %(status)s = 'Confirmed' THEN now() END,
                CASE WHEN %(status)s = 'Confirmed' THEN %(staff)s END)
        RETURNING id
    """, dict(event=event_id, venue=venue_id, start=start, end=end, status=status,
              coordinator=COORDINATOR, staff=STAFF)).fetchone()["id"]


def close_hall(db):
    db.execute("""
        INSERT INTO venue_unavailability
            (venue_id, start_date, end_date, reason_type, other_reason, created_by_id)
        VALUES (%s, '2035-11-10', '2035-11-12', 'maintenance', NULL, %s)
    """, (HALL, STAFF))


def event_status(db, event_id=CONFIRMED_EVENT):
    return db.execute("SELECT status::text FROM events WHERE id = %s",
                      (event_id,)).fetchone()["status"]


def booking_status(db, booking_id):
    return db.execute("SELECT status::text FROM venue_bookings WHERE id = %s",
                      (booking_id,)).fetchone()["status"]


def notices(db):
    return db.execute(
        "SELECT user_id, event_id, kind, status, message FROM notifications ORDER BY id"
    ).fetchall()


def moves(db):
    return db.execute("""
        SELECT event_id, old_status::text, new_status::text, changed_by_id, notes
        FROM status_changes ORDER BY id
    """).fetchall()


def replace_booking(db, booking_id, reason=REASON):
    return db.execute(
        "SELECT public.us12_4_request_replacement(%s, %s, %s, %s) AS result",
        (booking_id, OTHER_HALL, COORDINATOR, reason),
    ).fetchone()["result"]


CLOSURE_NOTE = (
    "Test Hall is unavailable 10 Nov 2035–12 Nov 2035 due to scheduled maintenance. "
    "A replacement venue is needed, then the safety check and confirmation again."
)


class TestTheFlag:
    def test_a_confirmed_event_goes_back_to_planning_and_both_are_told(self, db):
        booking_id = book(db)

        close_hall(db)

        assert booking_status(db, booking_id) == "Needs replacement"
        assert event_status(db) == "Planning"
        assert [tuple(row.values()) for row in moves(db)] == [
            (CONFIRMED_EVENT, "Confirmed", "Planning", STAFF, CLOSURE_NOTE)
        ]
        told = notices(db)
        assert [(n["user_id"], n["kind"], n["status"]) for n in told] == [
            (COORDINATOR, "booking-conflict", None),
            (COORDINATOR, "back-in-planning", None),
            (ORGANISER, "back-in-planning", None),
        ]
        # The Coordinator's notice reads as it did before US12.4.
        assert told[0]["message"] == (
            'The booking of Test Hall for "Open House" needs attention: the venue is '
            "unavailable 10 Nov 2035–12 Nov 2035 due to scheduled maintenance."
        )
        assert told[2]["message"] == f'"Open House" is back in Planning. {CLOSURE_NOTE}'

    def test_a_planning_event_is_flagged_and_left_in_planning(self, db):
        booking_id = book(db, event_id=PLANNING_EVENT)

        close_hall(db)

        assert booking_status(db, booking_id) == "Needs replacement"
        assert event_status(db, PLANNING_EVENT) == "Planning"
        assert moves(db) == []
        assert [n["kind"] for n in notices(db)] == ["booking-conflict"]
