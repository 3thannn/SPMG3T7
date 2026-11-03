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
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, TODAY

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


    def test_a_new_booking_is_requested_and_waits_for_venue_staff(
        self, client, coordinator, event
    ):
        assert request(client, coordinator).json()["status"] == "Requested"


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


    def test_a_refused_booking_does_not_block_the_others(self, client, coordinator, event):
        hall = request(client, coordinator, venueId=GREAT_HALL)
        refused = request(client, coordinator, venueId="999")
        breakout = request(client, coordinator, venueId=SEMINAR_ROOM)

        assert hall.status_code == 201, hall.text
        refusal(refused)
        assert breakout.status_code == 201, breakout.text
        listed = client.get(path(), headers=coordinator).json()
        assert [booking["venueName"] for booking in listed] == ["Great Hall", "Seminar Room 4"]




class TestBookingsShowOnTheEvent:
    """AC4: every booking for the event, together, readable on the event page."""



    def test_bookings_come_back_soonest_first(self, client, coordinator, event):
        request(
            client,
            coordinator,
            venueId=SEMINAR_ROOM,
            startsAt="2027-11-02T13:00",
            endsAt="2027-11-02T15:00",
        )
        request(client, coordinator, venueId=GREAT_HALL)
        request(
            client,
            coordinator,
            venueId=BERTHA_ROOM,
            startsAt="2027-11-02T09:00",
            endsAt="2027-11-02T12:00",
        )

        listed = client.get(path(), headers=coordinator).json()

        # Great Hall and Bertha Room both start at 09:00; the earlier end leads.
        assert [booking["venueName"] for booking in listed] == [
            "Bertha Room",
            "Great Hall",
            "Seminar Room 4",
        ]








class TestOnlyTheAssignedCoordinatorRequests:
    """AC6 (US8.6): the role, and then the assignment."""

    def test_the_owning_organiser_cannot_request(
        self, client, organiser, event, booking_repository
    ):
        response = request(client, organiser)

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert detail["required"] == "bookings:request"
        assert booking_repository.bookings == []


    def test_a_coordinator_not_assigned_to_the_event_cannot_request(
        self, client, coordinator, event_repository, booking_repository
    ):
        seed_event(event_repository, coordinator_id=99)

        response = request(client, coordinator)

        # The same answer US8.1 gives for the event itself: not theirs, not found.
        assert response.status_code == 404
        assert booking_repository.bookings == []





class TestEventStatus:
    """Venues can be requested only after approval and during planning."""


    @pytest.mark.parametrize(
        "event_status",
        [EventStatus.REJECTED, EventStatus.CANCELLED, EventStatus.CONFIRMED, EventStatus.COMPLETED],
    )
    def test_a_closed_event_is_refused_with_the_reason(
        self, client, coordinator, event_repository, booking_repository, event_status
    ):
        seed_event(event_repository, status=event_status)

        response = request(client, coordinator)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "rule_refused"
        assert detail["reason"] == "event-closed"
        assert detail["message"]
        assert booking_repository.bookings == []







class TestRefusals:
    """Every way a well-addressed request can still be wrong, and nothing is stored."""

    @pytest.fixture(autouse=True)
    def _event(self, event):
        return event

    @pytest.fixture(autouse=True)
    def _nothing_stored(self, booking_repository):
        yield
        assert booking_repository.bookings == []











    def test_an_end_equal_to_the_start_is_refused(self, client, coordinator):
        """A booking of no length is not a booking; the table's CHECK agrees."""
        detail = refusal(request(client, coordinator, endsAt=BOOKING["startsAt"]))

        assert detail["message"] == "The booking must end after it starts."

    def test_a_start_in_the_past_is_refused(self, client, coordinator):
        detail = refusal(
            request(client, coordinator, startsAt="2020-01-01T09:00", endsAt="2020-01-01T17:00")
        )

        assert detail["message"] == "A booking cannot start in the past."



def test_a_booking_starting_today_is_accepted(client, auth_headers, event):
    """The past is judged by date, so a time earlier today is not refused as past."""
    today = TODAY.isoformat()

    response = request(
        client,
        auth_headers("Event Coordinator"),
        startsAt=f"{today}T09:00",
        endsAt=f"{today}T10:00",
    )

    assert response.status_code == 201, response.text




