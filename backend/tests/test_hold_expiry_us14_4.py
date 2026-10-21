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

from app import booking_store, conflict_flags
from app.booking_store import HOLDS_VENUE, Booking, BookingStatus, StaleBookingStatus, to_booking
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

    def test_the_job_runs_the_function_step_one_creates(self):
        definition = (BACKEND / "SUPABASE_US14_4_HOLD_EXPIRY.sql").read_text()
        assert "CREATE OR REPLACE FUNCTION public.sweep_tentative_holds()" in definition
        assert "INTERVAL '24 hours'" in definition


class TestTheExpiredStatus:
    def test_expired_is_a_status_and_reads_back_from_a_row(self):
        assert BookingStatus("Expired") is BookingStatus.EXPIRED
        row = {
            "id": 7, "event_id": EVENT_ID, "venue_id": 1, "start_at": "2027-11-02T09:00:00",
            "end_at": "2027-11-02T17:00:00", "status": "Expired",
            "hold_expires_at": "2027-10-08T17:00:00",
        }
        assert to_booking(row).status is BookingStatus.EXPIRED

    def test_an_expired_hold_never_holds_its_venue(self):
        assert BookingStatus.EXPIRED not in HOLDS_VENUE
        expired = a_hold()
        assert expired.hold_expired is True
        assert expired.holds_venue is False
        # Even with the clock wound back before its expiry: it is final.
        assert expired.holds_venue_at(datetime(2027, 1, 1)) is False

    def test_a_held_hold_past_its_expiry_reads_the_same_before_the_sweep(self):
        unswept = a_hold(status=BookingStatus.HELD)
        assert (unswept.hold_expired, unswept.holds_venue) == (True, False)

    def test_a_live_hold_is_unaffected(self):
        live = a_hold(status=BookingStatus.HELD, expires="2027-10-20T17:00")
        assert (live.hold_expired, live.holds_venue) == (False, True)


class TestTheSlotIsFree:
    def test_the_slot_can_be_requested(self, client, coordinator, event, booking_repository):
        booking_repository.bookings.append(a_hold())
        response = request(client, coordinator)
        assert response.status_code == 201, response.text

    def test_it_is_never_flagged_as_a_conflict(self, venue_repository, booking_repository):
        booking_repository.bookings.append(a_hold())
        venue = venue_repository.get_venue(1)
        assert conflict_flags.clash_now(a_hold(), venue, [a_hold()], [], NOW) is None

    def test_it_does_not_stand_in_the_way_of_the_safety_check(
        self, client, coordinator, event_repository, booking_repository
    ):
        seed_event(event_repository, status=EventStatus.PLANNING)
        confirmed = a_hold(51, BookingStatus.CONFIRMED, starts="2027-11-03T09:00",
                           ends="2027-11-03T17:00")
        booking_repository.bookings.extend([a_hold(), confirmed])
        readiness = client.get(f"/events/{EVENT_ID}/safety-check", headers=coordinator)
        assert readiness.json()["ready"] is True


class TestExpiredHoldsStayInHistory:
    def test_the_event_lists_it_as_expired(self, client, coordinator, event, booking_repository):
        booking_repository.bookings.append(a_hold())
        [listed] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
        assert (listed["status"], listed["holdExpired"], listed["holdExpiresAt"]) == (
            "Expired", True, EXPIRY,
        )
        assert listed["heldByName"] == "Sam"

    def test_the_venue_lists_it_among_its_holds(
        self, client, auth_headers, event, booking_repository
    ):
        live = a_hold(51, BookingStatus.HELD, expires="2027-10-20T17:00",
                      starts="2027-11-03T09:00", ends="2027-11-03T17:00")
        booking_repository.bookings.extend([a_hold(), live])
        listed = client.get(
            "/holds", params={"venueId": "1"}, headers=auth_headers("Venue Staff")
        ).json()
        assert [(item["id"], item["status"], item["holdExpired"]) for item in listed] == [
            ("50", "Expired", True),
            ("51", "Held", False),
        ]


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

    def test_a_sweep_between_the_check_and_the_write_is_reported_as_expired(
        self, client, coordinator, event, booking_repository, monkeypatch
    ):
        live = a_hold(status=BookingStatus.HELD, expires="2027-10-20T17:00")
        booking_repository.bookings.append(live)

        def swept_first(booking_id, **_kwargs):
            booking_repository.bookings = [
                a_hold(expires="2027-10-10T08:59") if b.id == booking_id else b
                for b in booking_repository.bookings
            ]
            raise StaleBookingStatus

        monkeypatch.setattr(booking_repository, "request_hold", swept_first)
        response = client.post(booking_path(50, "request"), headers=coordinator)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "hold-expired"


class TestAnExpiredHoldCannotBeCancelled:
    @pytest.mark.parametrize("status", [BookingStatus.EXPIRED, BookingStatus.HELD])
    def test_there_is_nothing_to_cancel(
        self, client, coordinator, event, booking_repository, status
    ):
        booking_repository.bookings.append(a_hold(status=status))
        response = client.post(
            booking_path(50, "cancel"), json={"reason": "No longer needed."}, headers=coordinator
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "hold-expired"
        assert "There is nothing to cancel." in detail["message"]
        assert booking_repository.get_booking(50).status is status

    def test_a_live_hold_can_still_be_released(
        self, client, coordinator, event, booking_repository
    ):
        booking_repository.bookings.append(a_hold(status=BookingStatus.HELD,
                                                  expires="2027-10-20T17:00"))
        response = client.post(
            booking_path(50, "cancel"), json={"reason": "No longer needed."}, headers=coordinator
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"

    def test_a_sweep_between_the_check_and_the_write_is_reported_as_expired(
        self, client, coordinator, event, booking_repository, monkeypatch
    ):
        booking_repository.bookings.append(a_hold(status=BookingStatus.HELD,
                                                  expires="2027-10-20T17:00"))

        def swept_first(booking_id, **_kwargs):
            booking_repository.bookings = [a_hold(expires="2027-10-10T08:59")]
            raise StaleBookingStatus

        monkeypatch.setattr(booking_repository, "cancel", swept_first)
        response = client.post(
            booking_path(50, "cancel"), json={"reason": "No longer needed."}, headers=coordinator
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "hold-expired"


class TestCancellingTheEvent:
    """US4.6 with US14.4: cancelling an event releases only holds still keeping a slot."""

    def test_an_expired_hold_is_left_as_history(
        self, client, coordinator, event, booking_repository
    ):
        live = a_hold(51, BookingStatus.HELD, expires="2027-10-20T17:00",
                      starts="2027-11-03T09:00", ends="2027-11-03T17:00")
        unswept = a_hold(52, BookingStatus.HELD, starts="2027-11-04T09:00",
                         ends="2027-11-04T17:00")
        booking_repository.bookings.extend([a_hold(), live, unswept])

        response = client.post(
            f"/events/{EVENT_ID}/cancel", json={"reason": "Not going ahead."},
            headers=coordinator,
        )

        assert response.status_code == 200, response.text
        assert {b.id: b.status for b in booking_repository.bookings} == {
            50: BookingStatus.EXPIRED,
            51: BookingStatus.CANCELLED,
            52: BookingStatus.HELD,  # past its expiry; the sweep will mark it Expired
        }
