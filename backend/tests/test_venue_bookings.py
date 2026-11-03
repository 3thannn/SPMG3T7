"""Venue bookings for an event — US14.1.

An assigned Coordinator requests one or more venues for a single event, so a
bigger event can use a main hall and its breakout rooms at once. The classes
below follow the acceptance criteria in order, then the status rule, then every
way a request can be refused, then the one place bookings reach back into the
venue catalogue (a booked venue cannot be deleted).

Fixture venues are 1 (Great Hall), 2 (Bertha Room) and 3 (Seminar Room 4); see
conftest. No bookings exist until a test requests one.
"""

from dataclasses import replace

import pytest

from app.booking_store import BookingStatus
from app.event_status import EventStatus
from app.event_store import Event
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

EVENT_ID = 900
GREAT_HALL = "1"
BERTHA_ROOM = "2"
SEMINAR_ROOM = "3"

#: A valid request. Tests override one field at a time, so a failure names the
#: field that broke rather than the whole request.
BOOKING = {
    "venueId": GREAT_HALL,
    "startsAt": "2027-11-02T09:00",
    "endsAt": "2027-11-02T17:00",
}


def seed_event(
    event_repository,
    *,
    event_id: int = EVENT_ID,
    status: EventStatus = EventStatus.APPROVED,
    coordinator_id: int | None = COORDINATOR_ID,
    organiser_id: int = ORGANISER_ID,
    # Small enough for every fixture venue (Bertha Room holds 40), so the US14.1
    # tests are about booking, not about US18.1's suitability check.
    expected_attendance: int | None = 30,
) -> Event:
    """An event straight into the store, at whatever status the test needs."""
    event = Event(
        id=event_id,
        title="Faculty Welcome Night",
        purpose="Welcome the new intake.",
        description="",
        starts_at="2027-11-02T09:00",
        ends_at="2027-11-02T17:00",
        expected_attendance=expected_attendance,
        status=status,
        organiser_id=organiser_id,
        organiser_name="Dylan",
        created_at="2026-10-01T09:00:00",
        updated_at="2026-10-01T09:00:00",
        coordinator_id=coordinator_id,
    )
    event_repository.events.append(event)
    return event


def path(event_id: int = EVENT_ID) -> str:
    return f"/events/{event_id}/bookings"


def request(client, headers, event_id: int = EVENT_ID, **overrides):
    """POST a booking with overrides; `None` drops the field from the body."""
    body = {**BOOKING, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(path(event_id), json=body, headers=headers)


def refusal(response) -> dict:
    """The 400 body, asserting it is the shape this story promises."""
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_booking"
    return detail


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def organiser(auth_headers):
    return auth_headers("Event Organiser")


@pytest.fixture
def event(event_repository):
    """An Approved event, assigned to the fixture Coordinator."""
    return seed_event(event_repository)


class TestRequestingABooking:
    """AC1 and AC5: a booking is its own record, and it starts Requested."""

    def test_flagged_booking_exposes_replacement_details(
        self, client, coordinator, event, booking_repository
    ):
        response = request(client, coordinator)
        assert response.status_code == 201
        booking_repository.bookings[0] = replace(
            booking_repository.bookings[0],
            status=BookingStatus.NEEDS_REPLACEMENT,
            replacement_reason="Unexpected flooding",
            flagged_by_unavailability_id=42,
        )

        listed = client.get(path(), headers=coordinator)

        assert listed.status_code == 200
        assert listed.json()[0]["status"] == "Needs replacement"
        assert listed.json()[0]["replacementReason"] == "Unexpected flooding"
        assert listed.json()[0]["flaggedByUnavailabilityId"] == 42

    def test_the_assigned_coordinator_requests_a_venue(self, client, coordinator, event):
        response = request(client, coordinator)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["eventId"] == str(EVENT_ID)
        assert body["venueId"] == GREAT_HALL
        assert body["venueName"] == "Great Hall"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["endsAt"] == "2027-11-02T17:00"
        assert body["requestedAt"]

    def test_a_new_booking_is_requested_and_waits_for_venue_staff(
        self, client, coordinator, event
    ):
        assert request(client, coordinator).json()["status"] == "Requested"

    def test_the_response_uses_the_wire_names_and_nothing_else(self, client, coordinator, event):
        body = request(client, coordinator).json()

        assert set(body) == {
            "replacementReason",
            "flaggedByUnavailabilityId",
            "id",
            "eventId",
            "venueId",
            "venueName",
            "startsAt",
            "endsAt",
            "status",
            "requestedAt",
            "headcount",
            "requiredLayout",
            "requiredFacilities",
            "accessibilityNeeds",
            "cancellation",
            # US14.3: empty and False on a booking that was never a hold.
            "holdExpiresAt",
            "holdExpired",
            "heldByName",
            # US16.1: null until Venue Staff decide it.
            "decision",
            # US15.2: null unless flagged "Conflict – review needed".
            "conflict",
        }
        assert isinstance(body["id"], str)
        # US14.2: only a cancelled booking says who cancelled it.
        assert body["cancellation"] is None

    def test_the_booking_is_stored_against_the_event_and_the_venue(
        self, client, coordinator, event, booking_repository
    ):
        request(client, coordinator)

        [stored] = booking_repository.bookings
        assert stored.event_id == EVENT_ID
        assert stored.venue_id == 1
        assert stored.starts_at == "2027-11-02T09:00"
        assert stored.ends_at == "2027-11-02T17:00"
        assert stored.status is BookingStatus.REQUESTED

    def test_the_record_keeps_who_requested_it(
        self, client, coordinator, event, booking_repository
    ):
        request(client, coordinator)

        assert booking_repository.bookings[0].requested_by_id == COORDINATOR_ID

    def test_a_venue_id_sent_as_a_number_is_accepted(self, client, coordinator, event):
        response = request(client, coordinator, venueId=1)

        assert response.status_code == 201, response.text
        assert response.json()["venueId"] == GREAT_HALL

    def test_times_with_seconds_are_accepted(self, client, coordinator, event):
        response = request(
            client, coordinator, startsAt="2027-11-02T09:00:00", endsAt="2027-11-02T17:00:00"
        )

        assert response.status_code == 201, response.text

    def test_values_are_trimmed_before_they_are_read(self, client, coordinator, event):
        response = request(
            client,
            coordinator,
            venueId=f" {GREAT_HALL} ",
            startsAt="  2027-11-02T09:00 ",
            endsAt="\t2027-11-02T17:00\n",
        )

        assert response.status_code == 201, response.text
        assert response.json()["startsAt"] == "2027-11-02T09:00"

    def test_the_booking_need_not_match_the_event_times(self, client, coordinator, event):
        """A breakout room may be wanted for the afternoon only, or a hall the night before."""
        response = request(
            client, coordinator, startsAt="2027-11-01T18:00", endsAt="2027-11-01T22:00"
        )

        assert response.status_code == 201, response.text


class TestManyBookingsForOneEvent:
    """AC1 and AC3: one event can have many, and each stands on its own."""

    def test_an_event_can_have_several_venues(self, client, coordinator, event):
        hall = request(client, coordinator, venueId=GREAT_HALL).json()
        breakout_a = request(client, coordinator, venueId=SEMINAR_ROOM).json()
        breakout_b = request(client, coordinator, venueId=BERTHA_ROOM).json()

        listed = client.get(path(), headers=coordinator).json()

        assert {booking["id"] for booking in listed} == {
            hall["id"],
            breakout_a["id"],
            breakout_b["id"],
        }
        assert len({hall["id"], breakout_a["id"], breakout_b["id"]}) == 3

    def test_the_same_venue_can_be_booked_twice_for_one_event(self, client, coordinator, event):
        """Two days in the same hall is two bookings. Clashes are US15.1's to judge."""
        first = request(client, coordinator)
        second = request(
            client, coordinator, startsAt="2027-11-03T09:00", endsAt="2027-11-03T17:00"
        )

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

    def test_a_refused_booking_does_not_block_the_others(self, client, coordinator, event):
        hall = request(client, coordinator, venueId=GREAT_HALL)
        refused = request(client, coordinator, venueId="999")
        breakout = request(client, coordinator, venueId=SEMINAR_ROOM)

        assert hall.status_code == 201, hall.text
        refusal(refused)
        assert breakout.status_code == 201, breakout.text
        listed = client.get(path(), headers=coordinator).json()
        assert [booking["venueName"] for booking in listed] == ["Great Hall", "Seminar Room 4"]

    def test_a_refused_booking_leaves_an_earlier_one_untouched(self, client, coordinator, event):
        created = request(client, coordinator).json()

        request(client, coordinator, endsAt="2027-11-02T08:00")

        assert client.get(path(), headers=coordinator).json() == [created]

    def test_bookings_belong_to_the_event_they_were_requested_for(
        self, client, coordinator, event, event_repository
    ):
        seed_event(event_repository, event_id=901)
        request(client, coordinator, event_id=EVENT_ID)

        assert client.get(path(901), headers=coordinator).json() == []


