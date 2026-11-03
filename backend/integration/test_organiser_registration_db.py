"""D3 against real PostgreSQL: SUPABASE_FIX_ORGANISER_REGISTRATION.sql.

The owning Organiser may open and close registration as well as the assigned
Coordinator; anyone else is refused. Only the tables and columns
set_event_registration reads are built, in a schema of the test's own.
The API half is tests/test_registration_us20_1.py::TestWhoMaySetIt.

TEST_POSTGRES_DSN must point to disposable PostgreSQL.
"""

import os
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "SUPABASE_FIX_ORGANISER_REGISTRATION.sql"
ORGANISER, COORDINATOR, OTHER_ORGANISER, OTHER_COORDINATOR = 1, 2, 3, 4


@pytest.fixture
def db():
    dsn = os.environ.get("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN must point to a disposable PostgreSQL server")
    schema = f"d3_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"SET search_path TO {schema}")
        for role in ("anon", "authenticated", "service_role"):
            connection.execute(
                f"DO $$ BEGIN CREATE ROLE {role}; EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
        connection.execute("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT NOT NULL);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY, status TEXT NOT NULL, organiser_id INTEGER NOT NULL,
                coordinator_id INTEGER, registration_open BOOLEAN NOT NULL DEFAULT FALSE,
                registration_capacity INTEGER
            );
            CREATE TABLE registrations (event_id INTEGER NOT NULL, status TEXT NOT NULL);
        """)
        connection.execute(
            "INSERT INTO users VALUES (1,'Event Organiser'),(2,'Event Coordinator'),"
            "(3,'Event Organiser'),(4,'Event Coordinator')"
        )
        connection.execute("INSERT INTO events VALUES (1,'Confirmed',1,2,FALSE,NULL)")
        script = MIGRATION.read_text(encoding="utf-8").replace("public.", schema + ".")
        connection.execute(script)
        connection.execute(script)  # safe to run twice
        try:
            yield connection
        finally:
            connection.execute(f"DROP SCHEMA {schema} CASCADE")


def save(db, actor, is_open=True, capacity=40):
    return db.execute(
        "SELECT set_event_registration(1, %s, %s, %s)->>'outcome'", (actor, is_open, capacity)
    ).fetchone()[0]


def settings(db):
    return db.execute(
        "SELECT registration_open, registration_capacity FROM events WHERE id = 1"
    ).fetchone()


def test_the_owning_organiser_opens_and_closes_it(db):
    assert save(db, ORGANISER) == "saved"
    assert settings(db) == (True, 40)
    assert save(db, ORGANISER, is_open=False, capacity=None) == "saved"
    assert settings(db) == (False, 40)


def test_the_assigned_coordinator_still_can(db):
    assert save(db, COORDINATOR) == "saved"


@pytest.mark.parametrize("actor", [OTHER_ORGANISER, OTHER_COORDINATOR])
def test_anyone_else_is_refused_and_nothing_changes(db, actor):
    assert save(db, actor) == "not-assigned"
    assert settings(db) == (False, None)
