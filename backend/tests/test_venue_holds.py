"""Tentative venue holds — US14.3.

Venue Staff place a hold on a venue with an expiry, to keep a slot for a
Coordinator who is still finalising without blocking the venue forever. Test
case ids (TC-H…) match the US14.3 test cases document; the classes follow the
acceptance criteria in order.

"Now" is pinned to NOW for every test, so expiry is decided by the test rather
than by the day it runs. Fixture venues are 1 (Great Hall) and 2 (Bertha
Room); the fixture Venue Staff member is Sam and the Coordinator is Priya.
"""

from datetime import datetime

import pytest

from app import booking_store
from app.booking_store import BookingStatus
from tests.conftest import COORDINATOR_ID, VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, seed_event

NOW = datetime(2027, 10, 1, 9, 0)
GREAT_HALL = "1"

#: A valid hold. Tests override one field at a time.
HOLD = {
    "venueId": GREAT_HALL,
    "eventId": str(EVENT_ID),
    "startsAt": "2027-11-02T09:00",
    "endsAt": "2027-11-02T17:00",
    "expiresAt": "2027-10-08T17:00",
}


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    """Pin the clock holds are judged by. Returns a setter to move it on."""
    current = {"now": NOW}
    monkeypatch.setattr(booking_store, "local_now", lambda: current["now"])

    def move_to(moment: datetime) -> None:
        current["now"] = moment

    return move_to


@pytest.fixture
def staff(auth_headers):
    return auth_headers("Venue Staff")


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def event(event_repository):
    """An Approved event assigned to the fixture Coordinator."""
    return seed_event(event_repository)


def place(client, headers, **overrides):
    """POST a hold with overrides; `None` drops the field from the body."""
    body = {**HOLD, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post("/holds", json=body, headers=headers)


def to_request(client, headers, booking_id: str, event_id: int = EVENT_ID):
    return client.post(f"/events/{event_id}/bookings/{booking_id}/request", headers=headers)


def bad_request(response) -> str:
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_booking"
    return detail["message"]


def refused(response) -> dict:
    assert response.status_code == 409, response.text
    return response.json()["detail"]


class TestPlacingAHold:
    """AC1: a hold is a venue booking with status Held, linked to an event and its Coordinator."""

    def test_tc_h01_venue_staff_place_a_hold(self, client, staff, event):
        response = place(client, staff)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "Held"
        assert body["eventId"] == str(EVENT_ID)
        assert body["eventTitle"] == "Faculty Welcome Night"
        assert body["venueName"] == "Great Hall"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["endsAt"] == "2027-11-02T17:00"
        assert body["holdExpiresAt"] == "2027-10-08T17:00"
        assert body["holdExpired"] is False
        assert body["heldByName"] == "Sam"

    def test_tc_h02_it_is_stored_as_a_booking_nobody_has_requested_yet(
        self, client, staff, event, booking_repository
    ):
        place(client, staff)

        [stored] = booking_repository.bookings
        assert stored.status is BookingStatus.HELD
        assert stored.event_id == EVENT_ID
        assert stored.held_by_id == VENUE_STAFF_ID
        assert stored.requested_by_id is None
        assert stored.headcount == 30




    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_h06_only_venue_staff_place_holds(self, client, auth_headers, event, role):
        assert place(client, auth_headers(role)).status_code == 403






class TestExpiry:
    """AC2: expiry date/time is required and must be in the future."""

    def test_tc_h11_expiry_is_required(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt=None)) == (
            "Give the hold an expiry date and time."
        )





    def test_tc_h16_expiry_exactly_now_is_refused(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="2027-10-01T09:00")) == (
            "The hold must expire in the future."
        )

    def test_tc_h17_expiry_a_minute_from_now_is_accepted(self, client, staff, event):
        assert place(client, staff, expiresAt="2027-10-01T09:01").status_code == 201

    def test_tc_h18_expiry_after_the_booking_starts_is_refused(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="2027-11-02T09:01")) == (
            "The hold must expire no later than the booking starts."
        )




class TestTheSlotIsTaken:
    """AC3: while Held and not expired, the slot counts as taken (US15.1, US9.4)."""



    def test_tc_h23_a_minute_before_expiry_it_still_holds(
        self, client, staff, event, booking_repository, frozen_now
    ):
        place(client, staff)
        frozen_now(datetime(2027, 10, 8, 16, 59))
        assert booking_repository.bookings[0].holds_venue is True





class TestTurningAHoldIntoARequest:
    """AC4: the Coordinator can turn the hold into a booking request before it expires."""

    def test_tc_h27_the_coordinator_requests_a_held_venue(
        self, client, staff, coordinator, event, booking_repository
    ):
        hold = place(client, staff).json()

        response = to_request(client, coordinator, hold["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Requested"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["holdExpiresAt"] == "2027-10-08T17:00"
        assert body["holdExpired"] is False
        [stored] = booking_repository.bookings
        assert stored.requested_by_id == COORDINATOR_ID
        assert stored.holds_venue is True



    def test_tc_h30_an_expired_hold_cannot_be_requested(
        self, client, staff, coordinator, event, booking_repository, frozen_now
    ):
        hold = place(client, staff).json()
        frozen_now(datetime(2027, 10, 8, 17, 0))

        detail = refused(to_request(client, coordinator, hold["id"]))

        assert detail["reason"] == "hold-expired"
        assert "expired at 2027-10-08 17:00" in detail["message"]
        assert booking_repository.bookings[0].status is BookingStatus.HELD












class TestNeverConfirmed:
    """AC5: a Held booking is never shown or counted as Confirmed."""

    def test_tc_h41_venue_staff_cannot_confirm_a_hold(
        self, client, staff, event, booking_repository
    ):
        # US16.1 added Confirmed. A hold must be requested by the Coordinator
        # before Venue Staff can confirm it, so it is never Confirmed as a hold.
        hold = place(client, staff).json()

        response = client.post(f"/booking-requests/{hold['id']}/approve", headers=staff)

        assert refused(response)["reason"] == "not-requested"
        assert booking_repository.bookings[0].status is BookingStatus.HELD

    def test_tc_h42_a_hold_is_reported_as_held_however_long_it_waits(
        self, client, staff, coordinator, event, frozen_now
    ):
        place(client, staff)
        for moment in (NOW, datetime(2027, 10, 8, 17, 0), datetime(2027, 11, 3, 0, 0)):
            frozen_now(moment)
            [listed] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
            assert listed["status"] == "Held"







HELD_ROW = {
    "id": 41,
    "event_id": EVENT_ID,
    "venue_id": 1,
    "start_at": "2027-11-02T09:00:00",
    "end_at": "2027-11-02T17:00:00",
    "status": "Held",
    "requested_by_id": None,
    "created_at": "2027-10-01T09:00:00",
    "headcount": 30,
    "hold_expires_at": "2027-10-08T17:00:00",
    "held_by_id": VENUE_STAFF_ID,
    "venues": {"name": "Great Hall"},
    "held_by": {"name": "Sam"},
}


class FakeSupabase:
    """Records inserts and RPC calls; answers reads with HELD_ROW."""

    def __init__(self, rpc_answer: str = "requested"):
        self.inserted: list[dict] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.rpc_answer = rpc_answer

    def table(self, _name):
        return self

    def insert(self, row):
        self.inserted.append(row)
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        self._answer = self.rpc_answer
        return self

    def execute(self):
        if getattr(self, "_answer", None) is not None:
            answer, self._answer = self._answer, None
            return type("Response", (), {"data": answer})()
        return type("Response", (), {"data": [dict(HELD_ROW)]})()




