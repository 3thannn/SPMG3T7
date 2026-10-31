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

from app import venue_store
from app.booking_store import Booking, BookingStatus, Cancellation
from tests.test_venue_bookings import GREAT_HALL, SEMINAR_ROOM, request, seed_event

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

    @pytest.mark.parametrize("status", [BookingStatus.REQUESTED, BookingStatus.CONFIRMED])
    def test_an_active_booking_still_to_come_counts(self, status):
        assert booking(status=status).upcoming_at(NOW)

    def test_an_unexpired_hold_counts(self):
        held = booking(status=BookingStatus.HELD, hold_expires_at="2027-06-01T18:00")

        assert held.upcoming_at(NOW)

    def test_a_lapsed_hold_does_not(self):
        held = booking(status=BookingStatus.HELD, hold_expires_at="2027-06-01T09:00")

        assert not held.upcoming_at(NOW)

    def test_a_booking_under_way_counts(self):
        assert booking(starts_at="2027-06-01T09:00", ends_at="2027-06-01T17:00").upcoming_at(NOW)

    def test_a_booking_that_has_ended_does_not(self):
        assert not booking(starts_at="2027-05-01T09:00", ends_at="2027-05-01T17:00").upcoming_at(
            NOW
        )

    def test_one_ending_exactly_now_has_ended(self):
        assert not booking(starts_at="2027-06-01T09:00", ends_at="2027-06-01T12:00").upcoming_at(
            NOW
        )

    @pytest.mark.parametrize(
        "status",
        [
            BookingStatus.CANCELLED,
            BookingStatus.REJECTED,
            BookingStatus.EXPIRED,
            BookingStatus.NEEDS_REPLACEMENT,
            BookingStatus.REPLACED,
        ],
    )
    def test_a_closed_booking_does_not(self, status):
        assert not booking(status=status).upcoming_at(NOW)

    def test_an_end_that_cannot_be_read_counts(self):
        assert booking(ends_at="not a time").upcoming_at(NOW)


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

    def test_the_count_covers_every_future_booking(
        self, client, coordinator, venue_staff, booking_repository
    ):
        first = book(client, coordinator, booking_repository)
        # The event already holds its slot, so a second one goes straight in.
        booking_repository.bookings.append(
            replace(
                first, id=first.id + 1, starts_at="2027-11-03T09:00", ends_at="2027-11-03T17:00"
            )
        )

        detail = delete(client, venue_staff).json()["detail"]

        assert detail["futureBookings"] == 2
        assert "has 2 future bookings" in detail["message"]

    def test_a_confirmed_booking_blocks_the_delete(
        self, client, coordinator, venue_staff, booking_repository
    ):
        book(client, coordinator, booking_repository, status=BookingStatus.CONFIRMED)

        assert delete(client, venue_staff).json()["detail"]["code"] == "venue_has_future_bookings"


@pytest.mark.usefixtures("event")
class TestDeletingAVenueWithNoFutureBookings:
    """AC2: nothing ahead to protect."""

    def test_a_venue_never_booked_still_deletes(
        self, client, coordinator, venue_staff, booking_repository, venue_repository
    ):
        book(client, coordinator, booking_repository)

        response = delete(client, venue_staff, SEMINAR_ROOM)

        assert response.status_code == 204
        assert venue_repository.get_venue(3) is None

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

    @pytest.mark.parametrize(
        "status",
        [
            BookingStatus.CANCELLED,
            BookingStatus.REJECTED,
            BookingStatus.EXPIRED,
            BookingStatus.REPLACED,
        ],
    )
    def test_a_venue_whose_future_bookings_are_all_closed_deletes(
        self, client, coordinator, venue_staff, booking_repository, venue_repository, status
    ):
        cancellation = (
            Cancellation(at="2027-01-01T09:00:00", by_id=1, by_name="", reason="x")
            if status is BookingStatus.CANCELLED
            else None
        )
        book(client, coordinator, booking_repository, status=status, cancellation=cancellation)

        assert delete(client, venue_staff).status_code == 204
        assert venue_repository.get_venue(1) is None

    def test_a_lapsed_hold_does_not_block(
        self, client, coordinator, venue_staff, booking_repository
    ):
        book(
            client,
            coordinator,
            booking_repository,
            status=BookingStatus.HELD,
            hold_expires_at="2020-01-01T09:00",
        )

        assert delete(client, venue_staff).status_code == 204


@pytest.mark.usefixtures("event")
class TestBookingsWaitingForAReplacement:
    """Deleting the venue would delete a booking its Coordinator still has to move."""

    def test_a_future_flagged_booking_blocks_the_delete(
        self, client, coordinator, venue_staff, booking_repository, venue_repository
    ):
        book(client, coordinator, booking_repository, status=BookingStatus.NEEDS_REPLACEMENT)

        response = delete(client, venue_staff)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "venue_has_future_bookings"
        assert detail["message"] == (
            "Great Hall has 1 booking waiting for a replacement venue, so it cannot "
            "be deleted until their Coordinators have moved them."
        )
        assert venue_repository.get_venue(1) is not None

    def test_a_past_flagged_booking_does_not_block(
        self, client, coordinator, venue_staff, booking_repository
    ):
        book(
            client,
            coordinator,
            booking_repository,
            status=BookingStatus.NEEDS_REPLACEMENT,
            starts_at="2020-01-01T09:00",
            ends_at="2020-01-01T17:00",
        )

        assert delete(client, venue_staff).status_code == 204


@pytest.mark.usefixtures("event")
def test_a_booking_that_lands_after_the_check_is_still_refused(
    client, venue_staff, venue_repository, monkeypatch
):
    """The database trigger refuses the delete; the route says why, not 500."""

    def refused(venue_id: int) -> None:
        raise venue_store.VenueHasFutureBookings

    monkeypatch.setattr(venue_repository, "delete_venue", refused)

    response = delete(client, venue_staff)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "venue_has_future_bookings"
    assert "Mark it unavailable instead" in detail["message"]
    assert "futureBookings" not in detail


class TestAwaitingReplacementAt:
    def test_a_flagged_booking_still_to_come_counts(self):
        assert booking(status=BookingStatus.NEEDS_REPLACEMENT).awaiting_replacement_at(NOW)

    def test_a_flagged_booking_that_has_ended_does_not(self):
        flagged = booking(
            status=BookingStatus.NEEDS_REPLACEMENT,
            starts_at="2027-05-01T09:00",
            ends_at="2027-05-01T17:00",
        )

        assert not flagged.awaiting_replacement_at(NOW)

    def test_an_active_booking_is_not_awaiting_replacement(self):
        assert not booking().awaiting_replacement_at(NOW)
