"""US8.4 in the database: SUPABASE_US8_4_REASSIGN_COORDINATOR.sql.

reassign_event_coordinator moves an assigned, active event to a different
Coordinator in one transaction: it logs the move in status_changes, naming the
previous Coordinator, and notifies both Coordinators (and the new one of any
booking that needs replacing). It refuses anything else, changing nothing.
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
MIGRATION = ROOT / "SUPABASE_US8_4_REASSIGN_COORDINATOR.sql"

PRIYA, ALEX, LEAD, ORGANISER, NAMELESS = 201, 202, 203, 204, 205
EVENT = 301
UPDATED_AT = "2035-01-02 12:00:00"


@pytest.fixture(scope="module")
def database():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN must point to a disposable PostgreSQL server")
    name = f"us8_4_{uuid4().hex}"
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
                ):
                    connection.execute((ROOT / filename).read_text(encoding="utf-8"))
                # US1.4's role, without SUPABASE_ADD_NEW_ROLES.sql's seed accounts.
                connection.execute(
                    "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead'"
                )
                connection.execute(f"""
                    INSERT INTO users (id, name, email, role) VALUES
                        ({PRIYA}, 'Priya', 'priya@test.invalid', 'Event Coordinator'),
                        ({ALEX}, 'Alex', 'alex@test.invalid', 'Event Coordinator'),
                        ({LEAD}, 'Jordan', 'lead@test.invalid', 'Event Coordinator Lead'),
                        ({ORGANISER}, 'Dylan', 'organiser@test.invalid', 'Event Organiser'),
                        ({NAMELESS}, '  ', 'nameless@test.invalid', 'Event Coordinator');
                    INSERT INTO venues (id, name, location, capacity) VALUES
                        (401, 'Main Hall', 'Campus', 100);
                """)
                # Twice: the script says it is safe to run repeatedly.
                connection.execute(MIGRATION.read_text(encoding="utf-8"))
                connection.execute(MIGRATION.read_text(encoding="utf-8"))
                yield connection
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def db(database):
    with database.transaction(force_rollback=True):
        database.execute(
            """
            INSERT INTO events (id, name, organiser_id, coordinator_id, status, updated_at)
            VALUES (%s, 'Open House', %s, %s, 'Planning', %s)
            """,
            (EVENT, ORGANISER, PRIYA, UPDATED_AT),
        )
        yield database


def reassign(db, to=ALEX, by=LEAD, expected=UPDATED_AT):
    return db.execute(
        "SELECT public.reassign_event_coordinator(%s, %s, %s, %s) AS done",
        (EVENT, to, by, expected),
    ).fetchone()["done"]


def event(db):
    return db.execute(
        "SELECT coordinator_id, status::text, updated_at FROM events WHERE id = %s", (EVENT,)
    ).fetchone()


def log(db):
    return db.execute(
        "SELECT old_status::text, new_status::text, changed_by_id, notes FROM status_changes"
    ).fetchall()


def notices(db):
    return db.execute(
        "SELECT user_id, kind, status, message FROM notifications ORDER BY user_id, kind"
    ).fetchall()


def test_reassigns_logs_and_notifies_both_coordinators(db):
    assert reassign(db) is True

    moved = event(db)
    assert moved["coordinator_id"] == ALEX
    assert moved["status"] == "Planning"
    assert str(moved["updated_at"]) != UPDATED_AT
    assert log(db) == [
        dict(
            old_status="Planning",
            new_status="Planning",
            changed_by_id=LEAD,
            notes="Coordinator reassigned from Priya to Alex.",
        )
    ]
    assert notices(db) == [
        dict(
            user_id=PRIYA,
            kind="unassigned",
            status=None,
            message='"Open House" is no longer assigned to you.',
        ),
        dict(user_id=ALEX, kind="assigned", status=None, message='You were assigned "Open House".'),
    ]








@pytest.mark.parametrize("status", ["Completed", "Cancelled", "Rejected"])
def test_a_finished_event_is_refused(db, status):
    db.execute("UPDATE events SET status = %s::event_status WHERE id = %s", (status, EVENT))

    assert reassign(db) is False

    assert event(db)["coordinator_id"] == PRIYA
    assert log(db) == []
    assert notices(db) == []


