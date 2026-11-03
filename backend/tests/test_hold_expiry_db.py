"""US14.4 against the real database: the sweep the pg_cron job runs.

CI has no database, so this file is opt-in. Apply
SUPABASE_US14_4_HOLD_EXPIRY.sql first, then run it from backend/:

    SPMG3T7_DB_TESTS=1 python -m pytest tests/test_hold_expiry_db.py          # bash
    $env:SPMG3T7_DB_TESTS=1; python -m pytest tests/test_hold_expiry_db.py    # PowerShell

It needs `SUPABASE_DB_URL` in backend/.env and psycopg (requirements-dev.txt).

Everything happens in one transaction that is rolled back at the end, so the
test leaves nothing behind in the shared project: its users, venue, events,
holds and notices go with it. The sweep it calls sweeps the project's real
holds too, inside the same transaction, so that is rolled back as well; a real
hold it touches stays locked for the second or so the test takes.
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv

if not os.getenv("SPMG3T7_DB_TESTS"):
    pytest.skip(
        "opt-in: set SPMG3T7_DB_TESTS=1 to run against SUPABASE_DB_URL",
        allow_module_level=True,
    )

psycopg = pytest.importorskip("psycopg")

from app import notifications  # noqa: E402 - only once the module is not skipped
from app.event_status import EventStatus  # noqa: E402
from app.event_store import Event  # noqa: E402


@pytest.fixture
def db():
    """A cursor in a transaction that is always rolled back."""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        pytest.skip("SUPABASE_DB_URL is not set in backend/.env")
    connection = psycopg.connect(url, connect_timeout=15)
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.rollback()
        connection.close()


def one(db, sql, *params):
    db.execute(sql, params)
    return db.fetchone()[0]


class World:
    """A coordinator, a venue, an open and a cancelled event, and a hold maker."""

    def __init__(self, db):
        self.db = db
        self.tag = uuid.uuid4().hex[:8]
        self.now = one(db, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::timestamp(0)")
        self.organiser = self.user("Event Organiser")
        self.coordinator = self.user("Event Coordinator")
        self.venue_name = f"US14.4 test venue {self.tag}"
        self.venue = one(
            db,
            "INSERT INTO public.venues (name, location, capacity) VALUES (%s, 'Test', 50) "
            "RETURNING id",
            self.venue_name,
        )
        self.open_title = f"US14.4 open {self.tag}"
        self.open_event = self.event(self.open_title, "Planning")
        self.closed_event = self.event(f"US14.4 cancelled {self.tag}", "Cancelled")
        self.days = 0

    def user(self, role):
        return one(
            self.db,
            "INSERT INTO public.users (email, name, role) "
            "VALUES (%s, %s, %s::public.user_role) RETURNING id",
            f"us14-4-{role.split()[-1].lower()}-{self.tag}@example.invalid",
            f"US14.4 {role}",
            role,
        )

    def event(self, title, status):
        return one(
            self.db,
            "INSERT INTO public.events (name, description, organiser_id, coordinator_id, status) "
            "VALUES (%s, 'Test', %s, %s, %s::public.event_status) RETURNING id",
            title, self.organiser, self.coordinator, status,
        )

    def hold(self, event, expires_in, *, status="Held", warned=False):
        """A booking on its own far-off day, so no two of them share a slot."""
        self.days += 2
        starts = self.now + timedelta(days=60 + self.days)
        return one(
            self.db,
            "INSERT INTO public.venue_bookings "
            "(event_id, venue_id, start_at, end_at, status, headcount, hold_expires_at, "
            " expiry_warned_at) "
            "VALUES (%s, %s, %s, %s, %s::public.booking_status, 30, %s, %s) RETURNING id",
            event, self.venue, starts, starts + timedelta(hours=8), status,
            self.now + expires_in, self.now if warned else None,
        )

    def sweep(self):
        return one(self.db, "SELECT public.sweep_tentative_holds()")

    def booking(self, booking_id):
        self.db.execute(
            "SELECT status::text, expiry_warned_at IS NOT NULL, start_at, end_at, hold_expires_at "
            "FROM public.venue_bookings WHERE id = %s",
            (booking_id,),
        )
        return self.db.fetchone()

    def notices(self):
        self.db.execute(
            "SELECT user_id, kind, status, message FROM public.notifications "
            "WHERE event_id IN (%s, %s) ORDER BY kind",
            (self.open_event, self.closed_event),
        )
        return self.db.fetchall()


def test_the_sweep_expires_warns_and_tells_the_coordinator_once(db, notification_repository):
    world = World(db)
    expired = world.hold(world.open_event, timedelta(minutes=-1))
    due = world.hold(world.open_event, timedelta(hours=2))
    later = world.hold(world.open_event, timedelta(days=3))
    warned = world.hold(world.open_event, timedelta(hours=1), warned=True)
    closed_expired = world.hold(world.closed_event, timedelta(minutes=-1))
    closed_due = world.hold(world.closed_event, timedelta(hours=2))
    requested = world.hold(world.open_event, timedelta(days=-1), status="Requested")
    mine = {expired, due, later, warned, closed_expired, closed_due, requested}

    result = world.sweep()

    # Holds past their expiry become Expired; a hold due within 24 hours is warned once.
    assert set(result["expired"]) & mine == {expired, closed_expired}
    assert set(result["warned"]) & mine == {due}
    assert world.booking(expired)[:2] == ("Expired", False)
    assert world.booking(closed_expired)[0] == "Expired"
    assert world.booking(due)[:2] == ("Held", True)
    assert world.booking(later)[:2] == ("Held", False)
    assert world.booking(warned)[:2] == ("Held", True)
    assert world.booking(closed_due)[:2] == ("Held", False)
    assert world.booking(requested)[0] == "Requested"

    # The Coordinator hears about the open event only, in US10.2's exact words.
    title_event = Event(
        id=world.open_event, title=world.open_title, purpose="", description="", starts_at="",
        ends_at="", expected_attendance=None, status=EventStatus.PLANNING,
        organiser_id=world.organiser, organiser_name="", created_at="", updated_at="",
        coordinator_id=world.coordinator,
    )
    notifications.notify_hold_expired(title_event, world.venue_name)
    notifications.notify_hold_expiring(
        title_event, world.venue_name, world.booking(due)[4].strftime("%d %b %Y, %H:%M")
    )
    expected_expired, expected_expiring = (n.message for n in notification_repository.notifications)
    assert world.notices() == [
        (world.coordinator, "hold-expired", None, expected_expired),
        (world.coordinator, "hold-expiring", None, expected_expiring),
    ]

    # Nothing happens twice.
    again = world.sweep()
    assert not (set(again["expired"]) | set(again["warned"])) & mine
    assert len(world.notices()) == 2




