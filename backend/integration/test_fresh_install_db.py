"""A3: a fresh database builds from the repo's SQL, in the README's order.

scripts/fresh_install.py applies every script in `ORDER`, twice, to an empty
PostgreSQL 16. This proves the order works and every script is safe to run
again, then checks the pieces the API calls exist and one Week 9 hold goes
through: approved as a hold, then confirmed by the Coordinator.

Needs TEST_POSTGRES_DSN pointing at a disposable server, as the other
integration tests do; CI provides one.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))
from fresh_install import EXCLUDED, ORDER, apply_all, ensure_roles  # noqa: E402


def test_every_script_is_in_the_order_or_left_out_on_purpose():
    scripts = {path.name for path in BACKEND.glob("SUPABASE_*.sql")}
    assert scripts == set(ORDER) | set(EXCLUDED)
    assert len(ORDER) == len(set(ORDER))


@pytest.fixture(scope="module")
def database():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN must point to a disposable PostgreSQL server")
    name = f"fresh_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        ensure_roles(admin)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(
                make_conninfo(dsn, dbname=name), autocommit=True, row_factory=dict_row
            ) as connection:
                apply_all(connection)
                yield connection
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.mark.parametrize(
    "function",
    [
        "approve_venue_booking",
        "approve_venue_booking_as_hold",
        "confirm_held_booking",
        "request_venue_and_plan",
        "request_replacement_venue",
        "us12_4_request_replacement",
        "sweep_tentative_holds",
        "send_event_to_safety_check",
        "confirm_event",
        "cancel_event",
        "reassign_event_coordinator",
        "register_for_event",
        "withdraw_registration",
    ],
)
def test_the_functions_the_api_calls_exist(database, function):
    found = database.execute(
        "SELECT 1 FROM pg_proc WHERE proname = %s AND pronamespace = 'public'::regnamespace",
        (function,),
    ).fetchone()
    assert found is not None, function


def test_no_story_s_notice_kind_was_lost(database):
    definition = database.execute(
        "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint "
        "WHERE conname = 'notifications_kind_valid'"
    ).fetchone()["d"]
    for kind in (
        "equipment-request", "assigned", "hold-expiring", "booking-confirmed", "event-full",
        "safety-rejected", "change-submitted", "equipment-reserved", "back-in-planning",
        "safety-approved", "event-updated", "hold-placed", "hold-released", "booking-requested",
        "registration-opened", "attendee-withdrew",
    ):
        assert kind in definition, kind


def test_a_request_approved_as_a_hold_is_confirmed_by_the_coordinator(database):
    start = (datetime.now() + timedelta(days=30)).replace(microsecond=0)
    with database.transaction(force_rollback=True):
        database.execute("""
            INSERT INTO users (id, name, email, role) VALUES
                (9101, 'Coordinator', 'fresh-coordinator@test.invalid', 'Event Coordinator'),
                (9102, 'Staff', 'fresh-staff@test.invalid', 'Venue Staff'),
                (9103, 'Organiser', 'fresh-organiser@test.invalid', 'Event Organiser');
            INSERT INTO venues (id, name, location, capacity) VALUES
                (9101, 'Fresh Hall', 'Campus', 100);
            INSERT INTO events (id, name, organiser_id, coordinator_id, status) VALUES
                (9101, 'Fresh Event', 9103, 9101, 'Planning');
        """)
        booking = database.execute(
            """
            INSERT INTO venue_bookings
                (event_id, venue_id, start_at, end_at, status, requested_by_id)
            VALUES (9101, 9101, %s, %s, 'Requested', 9101) RETURNING id
            """,
            (start, start + timedelta(hours=2)),
        ).fetchone()["id"]

        held = database.execute(
            "SELECT public.approve_venue_booking_as_hold(%s, 9102, %s) AS outcome",
            (booking, start - timedelta(days=1)),
        ).fetchone()["outcome"]
        confirmed = database.execute(
            "SELECT public.confirm_held_booking(%s, 9101) AS outcome", (booking,)
        ).fetchone()["outcome"]

        assert (held, confirmed) == ("held", "confirmed")
        row = database.execute(
            "SELECT status::text, decided_by_id, held_by_id FROM venue_bookings WHERE id = %s",
            (booking,),
        ).fetchone()
        assert (row["status"], row["decided_by_id"], row["held_by_id"]) == (
            "Confirmed", 9102, 9102
        )
