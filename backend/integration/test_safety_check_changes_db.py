"""D1 against real PostgreSQL: SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql.

An important change during the safety check sends the event back to Planning, in
the database itself, whether the Coordinator edits directly (us11_edit) or
accepts an Organiser's change request (us11_approve_change). The API half is
tests/test_safety_approval_after_change.py.

TEST_POSTGRES_DSN must point to disposable PostgreSQL. Each test owns a schema.
"""

import pytest
from psycopg.types.json import Jsonb

from integration.test_change_review_db import ROOT
from integration.test_change_review_db import database as us11_database  # noqa: F401

REASON = "The Coordinator changed the expected attendance during the safety check."


@pytest.fixture
def database(us11_database):  # noqa: F811 - wraps the US11.2 schema with this fix
    db, dsn, schema = us11_database
    fix = (ROOT / "SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql").read_text(encoding="utf-8")
    fix = fix.replace("public.", schema + ".")
    fix = fix.replace("'public'::regnamespace", f"'{schema}'::regnamespace")
    db.execute(fix)
    db.execute(fix)  # safe to run twice
    db.execute("UPDATE events SET status='Pending Safety Check', expected_attendance=30")
    return db


def change(field, new, important=True, old=""):
    return {
        "changed_field": field,
        "old_value": old,
        "new_value": new,
        "change_type": "important" if important else "routine",
    }


def edit(db, changes, reason=REASON):
    return db.execute(
        "SELECT us11_edit(1,2,(SELECT updated_at FROM events WHERE id=1),%s,%s)",
        (Jsonb(changes), reason),
    ).fetchone()[0]


def status(db):
    return db.execute("SELECT status::TEXT FROM events WHERE id=1").fetchone()[0]


def history(db):
    return db.execute(
        "SELECT old_status::TEXT,new_status::TEXT,changed_by_id,notes FROM status_changes"
    ).fetchall()


def test_an_important_edit_sends_it_back_to_planning(database):
    assert edit(database, [change("expected_attendance", "40", old="30")])

    assert status(database) == "Planning"
    assert history(database) == [("Pending Safety Check", "Planning", 2, REASON)]


def test_a_routine_edit_keeps_it_pending(database):
    assert edit(database, [change("name", "Open Day", important=False, old="Original")])

    assert status(database) == "Pending Safety Check"
    assert history(database) == []


def test_the_old_four_argument_call_still_works(database):
    """The backend deployed before this script sends no reason."""
    assert database.execute(
        "SELECT us11_edit(1,2,(SELECT updated_at FROM events WHERE id=1),%s)",
        (Jsonb([change("name", "Open Day", important=False)]),),
    ).fetchone()[0]


def test_an_accepted_important_change_request_sends_it_back_to_planning(database):
    proposal = {"note": "More people", "changes": [change("expected_attendance", "40", old="30")]}
    assert database.execute("SELECT us11_review(1,1,'submit',0,%s)", (Jsonb(proposal),)).fetchone()[
        0
    ]

    assert database.execute(
        "SELECT us11_approve_change(1,2,1,%s,%s)", (Jsonb({}), REASON)
    ).fetchone()[0]

    assert status(database) == "Planning"
    assert history(database)[-1][:2] == ("Pending Safety Check", "Planning")
