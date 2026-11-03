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
from app.event_status import EventStatus
from tests.conftest import VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, request, seed_event

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

    def test_tc_h03_the_events_coordinator_sees_it_on_the_event(
        self, client, staff, coordinator, event
    ):
        place(client, staff)

        listed = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
        assert [(item["status"], item["venueName"]) for item in listed] == [("Held", "Great Hall")]

    def test_tc_h04_placing_a_hold_does_not_move_the_event(
        self, client, staff, event, event_repository
    ):
        place(client, staff)
        assert event_repository.get_event(EVENT_ID).status is EventStatus.APPROVED

    def test_tc_h05_a_hold_can_be_placed_for_a_planning_event(
        self, client, staff, event_repository
    ):
        seed_event(event_repository, status=EventStatus.PLANNING)
        assert place(client, staff).status_code == 201

    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_h06_only_venue_staff_place_holds(self, client, auth_headers, event, role):
        assert place(client, auth_headers(role)).status_code == 403

    def test_tc_h07_an_event_with_no_coordinator_cannot_be_held_for(
        self, client, staff, event_repository
    ):
        seed_event(event_repository, coordinator_id=None)
        assert refused(place(client, staff))["reason"] == "no-coordinator"

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (EventStatus.SUBMITTED, "not-approved"),
            (EventStatus.UNDER_REVIEW, "not-approved"),
            (EventStatus.REJECTED, "event-closed"),
            (EventStatus.CANCELLED, "event-closed"),
        ],
    )
    def test_tc_h08_only_an_event_that_can_take_bookings_can_be_held_for(
        self, client, staff, event_repository, status, reason
    ):
        seed_event(event_repository, status=status)
        assert refused(place(client, staff))["reason"] == reason

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"venueId": None}, "Choose a venue."),
            ({"venueId": "999"}, "That venue is not in the catalogue."),
            ({"venueId": "abc"}, "That venue is not in the catalogue."),
            ({"eventId": None}, "Choose the event to hold this venue for."),
            ({"eventId": "999"}, "That event does not exist."),
            ({"eventId": "abc"}, "That event does not exist."),
            ({"startsAt": None}, "Give the booking a start time."),
            ({"endsAt": "2027-11-02T08:00"}, "The booking must end after it starts."),
            (
                {"startsAt": "2027-02-30T09:00"},
                "The start time 2027-02-30T09:00 is not a real date and time.",
            ),
        ],
        ids=["no-venue", "unknown-venue", "bad-venue-id", "no-event", "unknown-event",
             "bad-event-id", "no-start", "end-before-start", "impossible-date"],
    )
    def test_tc_h09_a_bad_hold_is_refused_with_a_sentence(
        self, client, staff, event, overrides, message
    ):
        assert bad_request(place(client, staff, **overrides)) == message

    def test_tc_h10_a_draft_event_is_not_offered(self, client, staff, event_repository):
        seed_event(event_repository, status=EventStatus.DRAFT)
        assert bad_request(place(client, staff)) == "That event does not exist."


class TestExpiry:
    """AC2: expiry date/time is required and must be in the future."""

    def test_tc_h11_expiry_is_required(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt=None)) == (
            "Give the hold an expiry date and time."
        )

    def test_tc_h12_a_blank_expiry_is_missing(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="  ")) == (
            "Give the hold an expiry date and time."
        )

    @pytest.mark.parametrize("raw", ["next week", "2027-10-08", "08/10/2027 17:00"])
    def test_tc_h13_expiry_must_be_a_date_and_time(self, client, staff, event, raw):
        assert bad_request(place(client, staff, expiresAt=raw)) == (
            "Give the expiry as YYYY-MM-DDTHH:MM."
        )

    def test_tc_h14_expiry_must_be_a_real_date(self, client, staff, event):
        assert "is not a real date and time" in bad_request(
            place(client, staff, expiresAt="2027-10-32T10:00")
        )

    def test_tc_h15_expiry_in_the_past_is_refused(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="2027-09-30T09:00")) == (
            "The hold must expire in the future."
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

    def test_tc_h19_expiry_exactly_at_the_start_is_accepted(self, client, staff, event):
        assert place(client, staff, expiresAt="2027-11-02T09:00").status_code == 201

    def test_tc_h20_a_hold_cannot_start_in_the_past(self, client, staff, event):
        assert bad_request(
            place(client, staff, startsAt="2027-09-30T09:00", endsAt="2027-09-30T17:00")
        ) == "A hold cannot start in the past."


class TestTheSlotIsTaken:
    """AC3: while Held and not expired, the slot counts as taken (US15.1, US9.4)."""

    def test_tc_h21_an_unexpired_hold_holds_the_venue(
        self, client, staff, event, booking_repository
    ):
        place(client, staff)
        [hold] = booking_repository.bookings
        assert hold.holds_venue is True
        assert hold.hold_expired is False

    def test_tc_h22_an_expired_hold_frees_the_venue_on_its_own(
        self, client, staff, event, booking_repository, frozen_now
    ):
        place(client, staff)
        frozen_now(datetime(2027, 10, 8, 17, 0))

        [hold] = booking_repository.bookings
        assert hold.status is BookingStatus.HELD
        assert hold.holds_venue is False
        assert hold.hold_expired is True

    def test_tc_h23_a_minute_before_expiry_it_still_holds(
        self, client, staff, event, booking_repository, frozen_now
    ):
        place(client, staff)
        frozen_now(datetime(2027, 10, 8, 16, 59))
        assert booking_repository.bookings[0].holds_venue is True

    def test_tc_h24_a_hold_clashes_with_a_request_for_the_same_slot(
        self, client, staff, coordinator, event, booking_repository
    ):
        hold = place(client, staff).json()

        # US15.1: the held slot is taken, so a request for it is refused outright.
        response = request(client, coordinator)

        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["reason"] == "not-available"
        assert f"booking #{hold['id']}" in detail["clashes"][0]
        assert "Held" in detail["clashes"][0]
        assert len(booking_repository.bookings) == 1

        # US15.1: the held slot is taken, so a request for it is refused outright.
