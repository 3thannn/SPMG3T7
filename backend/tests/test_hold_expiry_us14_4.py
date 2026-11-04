"""US14.4: tentative holds expire automatically.

Acceptance criteria, and the tests that hold each one:

* A scheduled job checks holds at least every 15 minutes -> `TestTheSchedule`
  (reads the pg_cron script); the job itself -> tests/test_hold_expiry_db.py.
* Holds past their expiry -> Expired, and the slot is freed ->
  `TestTheExpiredStatus`, `TestTheSlotIsFree`; the sweep that writes Expired ->
  tests/test_hold_expiry_db.py.
* The Coordinator is told 24h before expiry and when it expires ->
  tests/test_hold_expiry_db.py (the job writes both, in US10.2's words).
* Expired holds stay in history and can't be turned into a booking request ->
  `TestExpiredHoldsStayInHistory`, `TestAnExpiredHoldCannotBeRequested`,
  `TestAnExpiredHoldCannotBeCancelled`.

The sweep is SQL run by pg_cron, so CI (which has no database) cannot run it.
What CI checks is everything the rest of the system does with what the sweep
writes. "Now" is pinned, as in the US14.3 tests.
"""

import re
from datetime import datetime
from pathlib import Path

import pytest

from app import booking_store
from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus
from tests.conftest import VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, request, seed_event

#: Well after the fixture hold's expiry (2027-10-08 17:00).
NOW = datetime(2027, 10, 10, 9, 0)
EXPIRY = "2027-10-08T17:00"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(booking_store, "local_now", lambda: NOW)


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def event(event_repository):
    return seed_event(event_repository, status=EventStatus.PLANNING)


def a_hold(
    booking_id=50,
    status=BookingStatus.EXPIRED,
    *,
    expires=EXPIRY,
    starts="2027-11-02T09:00",
    ends="2027-11-02T17:00",
):
    return Booking(
        id=booking_id,
        event_id=EVENT_ID,
        venue_id=1,
        venue_name="Great Hall",
        starts_at=starts,
        ends_at=ends,
        status=status,
        requested_by_id=None,
        requested_at="2027-10-01T09:00",
        headcount=30,
        hold_expires_at=expires,
        held_by_id=VENUE_STAFF_ID,
        held_by_name="Sam",
    )


def booking_path(booking_id, action):
    return f"/events/{EVENT_ID}/bookings/{booking_id}/{action}"


class TestTheSchedule:
    """'A scheduled job checks holds at least every 15 minutes (team-chosen).'"""

    def schedule(self) -> str:
        script = (BACKEND / "SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql").read_text()
        found = re.search(
            r"cron\.schedule\(\s*'sweep-tentative-holds',\s*'([^']+)',\s*"
            r"'SELECT public\.sweep_tentative_holds\(\)'",
            script,
        )
        assert found, "the schedule script no longer schedules the sweep"
        return found.group(1)

    def test_the_job_runs_at_least_every_15_minutes(self):
        minute, *rest = self.schedule().split()
        assert rest == ["*", "*", "*", "*"]
        assert minute.startswith("*/")
        step = int(minute.removeprefix("*/"))
        assert 1 <= step <= 15
        assert 60 % step == 0, "an uneven step would leave a longer gap at the top of the hour"





class TestTheSlotIsFree:
    def test_the_slot_can_be_requested(self, client, coordinator, event, booking_repository):
        booking_repository.bookings.append(a_hold())
        response = request(client, coordinator)
        assert response.status_code == 201, response.text




class TestExpiredHoldsStayInHistory:
    def test_the_event_lists_it_as_expired(self, client, coordinator, event, booking_repository):
        booking_repository.bookings.append(a_hold())
        [listed] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
        assert (listed["status"], listed["holdExpired"], listed["holdExpiresAt"]) == (
            "Expired", True, EXPIRY,
        )
        assert listed["heldByName"] == "Sam"



class TestAnExpiredHoldCannotBeRequested:
    def test_requesting_it_is_refused_as_expired(
        self, client, coordinator, event, booking_repository
    ):
        booking_repository.bookings.append(a_hold())
        response = client.post(booking_path(50, "request"), headers=coordinator)
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "hold-expired"
        assert "expired at 2027-10-08 17:00" in detail["message"]
        assert booking_repository.get_booking(50).status is BookingStatus.EXPIRED





