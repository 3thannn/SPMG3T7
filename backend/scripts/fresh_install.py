"""Build a fresh ConnectSphere database from the SQL scripts, in the one order that works.

    python scripts/fresh_install.py <postgres-dsn>

Every script is applied in `ORDER`, then once more: each addition is meant to
be safe to run twice, and the second pass proves it. The base schema
(`RUN_ONCE`) creates the database from nothing and is applied once only.
`integration/test_fresh_install_db.py`
runs this against an empty PostgreSQL 16 in CI, so the order in the README is
the order that was tested.

Two scripts are left out on purpose:

* SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql needs pg_cron, which only a Supabase
  project has. On Supabase, run it last (README step 3).
* SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql repaired a live function changed
  outside the repo. On a fresh database it would put back the pre-US12.4
  trigger, so it must not be run.

The Supabase roles (anon, authenticated, service_role) are created if the
server lacks them, as they are on plain PostgreSQL.
"""

import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

BACKEND = Path(__file__).resolve().parents[1]

#: The fresh-install order. Each script's own header names what it must follow.
ORDER: tuple[str, ...] = (
    # Base schema and early additions.
    "SUPABASE_SETUP.sql",
    "SUPABASE_ADD_NEW_ROLES.sql",
    "SUPABASE_ALLOW_PARTIAL_DRAFTS.sql",
    "SUPABASE_CASCADE_STATUS_CHANGES.sql",
    "SUPABASE_ATOMIC_EVENT_DECISIONS.sql",
    "SUPABASE_ADD_COORDINATOR_ASSIGNMENT.sql",
    "SUPABASE_US5_2_EVENT_CHANGES.sql",
    # Venues.
    "SUPABASE_ADD_VENUE_LAYOUTS.sql",
    "SUPABASE_ADD_VENUE_TURNAROUND.sql",
    "SUPABASE_ADD_VENUE_UNAVAILABILITY.sql",
    # Notifications and equipment (the notice-kind list is rebuilt here, so the
    # scripts that replace it outright come before every script that adds to it).
    "SUPABASE_ADD_NOTIFICATIONS.sql",
    "SUPABASE_ADD_EQUIPMENT_REQUESTS.sql",
    "SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql",
    # Bookings and the event lifecycle.
    "SUPABASE_ADD_VENUE_BOOKINGS.sql",
    "SUPABASE_CANCEL_VENUE_BOOKINGS.sql",
    "SUPABASE_ADD_BOOKING_NEEDS.sql",
    "SUPABASE_ADD_CHANGE_REQUESTS.sql",
    "SUPABASE_US4_5_LIFECYCLE.sql",
    "SUPABASE_ADD_EVENT_NEEDS.sql",
    "SUPABASE_ADD_VENUE_HOLDS.sql",
    "SUPABASE_ADD_BOOKING_DECISIONS.sql",
    "SUPABASE_ADD_BOOKING_CONFLICTS.sql",
    "SUPABASE_US14_4_HOLD_EXPIRY.sql",
    "SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql",
    "SUPABASE_US14_5_REPLACED_STATUS.sql",
    "SUPABASE_FIX_DECISION_RECORDED.sql",
    # Safety check, cancellation and registration.
    "SUPABASE_ADD_SAFETY_CHECK_STATUS.sql",
    "SUPABASE_US4_6_CANCEL_EVENT.sql",
    "SUPABASE_US20_1_REGISTRATION.sql",
    "SUPABASE_US20_2_WITHDRAW.sql",
    "SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql",
    "SUPABASE_US17_2_SAFETY_DECISIONS.sql",
    # Equipment reservations.
    "SUPABASE_US19_3_EQUIPMENT_RESERVATIONS.sql",
    "SUPABASE_US19_EXACT_ITEM_REQUESTS.sql",
    "SUPABASE_US19_REPAIR_EQUIPMENT_NOTICES.sql",
    # Change review, reconfirmation and confirming.
    "SUPABASE_US11_2_CHANGE_REVIEW.sql",
    "SUPABASE_US11_2_REVIEW_FIXES.sql",
    "SUPABASE_US11_3_RECONFIRM.sql",
    "SUPABASE_US4_7_CONFIRM_EVENT.sql",
    "SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql",
    "SUPABASE_FIX_ORGANISER_REGISTRATION.sql",
    "SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql",
    "SUPABASE_US8_4_REASSIGN_COORDINATOR.sql",
    "SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql",
    # Replacement venues and closures (US14.5, US12.4).
    "SUPABASE_US14_5_REQUEST_REPLACEMENT_VENUE.sql",
    "SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql",
    "SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql",
    # The 2026-11-04 gap closure.
    "SUPABASE_US14_6_HOLD_AFTER_APPROVAL.sql",
    "SUPABASE_G13_WEEK1_NOTICES.sql",
    # Security and sample data.
    "SUPABASE_HARDENING.sql",
    "SUPABASE_SEED_VENUES.sql",
)

#: Applied on the first pass only: it creates the base types and tables with no
#: IF NOT EXISTS, because it is the starting point rather than an addition.
RUN_ONCE: frozenset[str] = frozenset({"SUPABASE_SETUP.sql"})

#: Kept out of `ORDER`, with the reason above.
EXCLUDED: tuple[str, ...] = (
    "SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql",
    "SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql",
)

SUPABASE_ROLES = ("anon", "authenticated", "service_role")


def ensure_roles(connection: psycopg.Connection) -> None:
    for role in SUPABASE_ROLES:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            connection.execute(f'CREATE ROLE "{role}"')


#: `ALTER TYPE ... ADD VALUE` lines. Postgres refuses to use a new enum value in
#: the transaction that added it, and a script sent in one go is one
#: transaction, so these are committed first, one by one. Every one of them is
#: IF NOT EXISTS, so running it again with its script changes nothing. In the
#: Supabase SQL Editor, run such a line on its own first (SUPABASE_ADD_NEW_ROLES.sql).
ENUM_ADDITION = re.compile(r"^ALTER TYPE [^;]+ ADD VALUE [^;]+;", re.IGNORECASE | re.MULTILINE)


def apply_script(connection: psycopg.Connection, name: str) -> None:
    text = (BACKEND / name).read_text(encoding="utf-8")
    try:
        for addition in ENUM_ADDITION.findall(text):
            connection.execute(addition)
        connection.execute(text)
    except psycopg.Error as error:
        raise RuntimeError(f"{name} failed: {error}") from error


def apply_all(connection: psycopg.Connection, *, passes: int = 2) -> None:
    """Apply every script in order, `passes` times. Stops at the first failure."""
    for number in range(passes):
        for name in ORDER:
            if number and name in RUN_ONCE:
                continue
            apply_script(connection, name)


@contextmanager
def fresh_database(dsn: str, *, passes: int = 1) -> Iterator[str]:
    """A new database on `dsn`'s server, built from `ORDER`; its URL; dropped after.

    For the database tests (TEST_POSTGRES_DSN in CI), so none of them needs a
    project of its own or touches the shared one.
    """
    name = f"fresh_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        ensure_roles(admin)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            url = make_conninfo(dsn, dbname=name)
            with psycopg.connect(url, autocommit=True) as connection:
                apply_all(connection, passes=passes)
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def main(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        ensure_roles(connection)
        apply_all(connection)
    print(f"Applied {len(ORDER)} scripts twice.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
