"""US9.5: block deleting a venue that has future bookings.

AC1: delete is refused while the venue has any future active booking, and the
     message tells Venue Staff to mark it unavailable instead (US12.2).
AC2: a venue with no future bookings can still be deleted as in US9.1c. Its
     past and closed bookings are deleted with it, as the team chose; the
     database does that (SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql).
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app.booking_store import Booking, BookingStatus
from tests.test_venue_bookings import GREAT_HALL, request, seed_event

NOW = datetime(2027, 6, 1, 12, 0)


def booking(**overrides) -> Booking:
    fields = {
        "id": 1,
        "event_id": 1,
        "venue_id": 1,
        "venue_name": "Great Hall",
        "starts_at": "2027-06-02T09:00",
        "ends_at": "2027-06-02T17:00",
        "status": BookingStatus.REQUESTED,
        "requested_by_id": 1,
        "requested_at": "2027-05-01T09:00:00",
    }
    return Booking(**{**fields, **overrides})


class TestUpcomingAt:
    """Which bookings count as a future active booking."""






    def test_one_ending_exactly_now_has_ended(self):
        assert not booking(starts_at="2027-06-01T09:00", ends_at="2027-06-01T12:00").upcoming_at(
            NOW
        )




@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def venue_staff(auth_headers):
    return auth_headers("Venue Staff")


@pytest.fixture
def event(event_repository):
    """An Approved event, assigned to the fixture Coordinator, ready to book."""
    return seed_event(event_repository)


def delete(client, headers, venue_id: str = GREAT_HALL):
    return client.delete(f"/venues/{venue_id}", headers=headers)


def book(client, coordinator, booking_repository, **overrides) -> Booking:
    """Request a booking through the route, then reshape it as the test needs."""
    response = request(client, coordinator)
    assert response.status_code == 201, response.text
    stored = replace(booking_repository.bookings[-1], **overrides)
    booking_repository.bookings[-1] = stored
    return stored


@pytest.mark.usefixtures("event")
class TestDeletingAVenueWithFutureBookings:
    """AC1: refused, and pointed at marking the venue unavailable."""

    def test_a_future_booking_blocks_the_delete(
        self, client, coordinator, venue_staff, booking_repository, venue_repository
    ):
        book(client, coordinator, booking_repository)

        response = delete(client, venue_staff)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "venue_has_future_bookings"
        assert detail["futureBookings"] == 1
        assert venue_repository.get_venue(1) is not None

    def test_the_message_says_to_mark_it_unavailable(
        self, client, coordinator, venue_staff, booking_repository
    ):
        book(client, coordinator, booking_repository)

        message = delete(client, venue_staff).json()["detail"]["message"]

        assert message == (
            "Great Hall has 1 future booking, so it cannot be deleted. Mark it "
            "unavailable instead, so the affected bookings are flagged for a "
            "replacement venue."
        )




@pytest.mark.usefixtures("event")
class TestDeletingAVenueWithNoFutureBookings:
    """AC2: nothing ahead to protect."""


    def test_a_venue_with_only_past_bookings_deletes(
        self, client, coordinator, venue_staff, booking_repository, venue_repository
    ):
        book(
            client,
            coordinator,
            booking_repository,
            starts_at="2020-01-01T09:00",
            ends_at="2020-01-01T17:00",
        )

        response = delete(client, venue_staff)

        assert response.status_code == 204
        assert venue_repository.get_venue(1) is None








