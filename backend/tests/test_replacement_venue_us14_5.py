"""US14.5: Request a replacement venue for a flagged booking.

As an Event Coordinator, I want to search for and request a replacement venue
for a booking that's been affected, so that my event can still go ahead.

Acceptance Criteria:
* From a 'Needs replacement' booking, Coordinator can search venues (US9.3
  filters), only showing venues free for the same time (US15.1).
* Requesting a replacement creates a new booking request on the same event. Old
  booking is marked Replaced and kept for history.
* Other bookings on the event are untouched.
"""

import pytest

from app.booking_store import BookingStatus
from tests.conftest import COORDINATOR_ID


class TestSearchReplacementVenues:
    """AC1: Search venues available for the same time as the flagged booking."""

    def test_coordinator_can_search_replacement_venues_for_flagged_booking(
        self, client, auth_headers, event_repository, booking_repository, venue_repository
    ):
        """From a flagged booking, search shows only available venues at same time."""
        from datetime import datetime, timedelta

        from app.booking_store import Booking
        from app.event_store import Event

        # Create an event
        future_date = (datetime.now().date() + timedelta(days=30)).isoformat()
        event = Event(
            id=1,
            title="Tech Conference",
            purpose="Annual tech conference",
            description="",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            expected_attendance=100,
            organiser_id=1,
            organiser_name="Dylan",
            status="Approved",
            coordinator_id=COORDINATOR_ID,
            created_at="2026-10-01T10:00:00",
            updated_at="2026-10-01T10:00:00",
        )
        event_repository.events.append(event)

        # Create a booking with NEEDS_REPLACEMENT status
        booking = Booking(
            id=1,
            event_id=1,
            venue_id=1,  # Great Hall
            venue_name="Great Hall",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            status=BookingStatus.NEEDS_REPLACEMENT,
            requested_by_id=COORDINATOR_ID,
            requested_at="2026-10-01T10:30:00",
            replacement_reason="Unexpected flooding",
        )
        booking_repository.bookings.append(booking)

        # Search for replacement venues
        response = client.get(
            f"/bookings/{booking.id}/replacement-venues",
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        venues = response.json()

        # Should return available venues (excluding the original venue)
        assert len(venues) > 0
        venue_ids = [v["id"] for v in venues]
        assert 1 not in venue_ids  # Original venue should be excluded

    def test_search_applies_us9_3_filters(self, client, auth_headers):
        """Replacement search supports capacity, location, accessibility filters."""
        pytest.skip("Not implemented yet")

    def test_search_excludes_unavailable_venues(self, client, auth_headers):
        """Venues with conflicting bookings or blackouts are excluded (US15.1)."""
        pytest.skip("Not implemented yet")


class TestRequestReplacement:
    """AC2: Request a replacement creates new booking and marks old one Replaced."""

    def test_requesting_replacement_creates_new_booking_request(
        self, client, auth_headers, event_repository, booking_repository
    ):
        """New booking created on same event with Requested status."""
        from datetime import datetime, timedelta

        from app.booking_store import Booking
        from app.event_store import Event

        # Create an event
        future_date = (datetime.now().date() + timedelta(days=30)).isoformat()
        event = Event(
            id=1,
            title="Tech Conference",
            purpose="Annual tech conference",
            description="",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            expected_attendance=100,
            organiser_id=1,
            organiser_name="Dylan",
            status="Approved",
            coordinator_id=COORDINATOR_ID,
            created_at="2026-10-01T10:00:00",
            updated_at="2026-10-01T10:00:00",
        )
        event_repository.events.append(event)

        # Create a booking with NEEDS_REPLACEMENT status
        old_booking = Booking(
            id=1,
            event_id=1,
            venue_id=1,  # Great Hall
            venue_name="Great Hall",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            status=BookingStatus.NEEDS_REPLACEMENT,
            requested_by_id=COORDINATOR_ID,
            requested_at="2026-10-01T10:30:00",
            replacement_reason="Unexpected flooding",
        )
        booking_repository.bookings.append(old_booking)

        # Request a replacement venue (Bertha Room, id=2)
        response = client.post(
            f"/bookings/{old_booking.id}/request-replacement",
            json={"venueId": "2"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 201
        new_booking = response.json()

        # New booking should be on same event
        assert new_booking["eventId"] == "1"
        # New booking should be for the replacement venue
        assert new_booking["venueId"] == "2"
        assert new_booking["venueName"] == "Bertha Room"
        # New booking should have same times
        assert new_booking["startsAt"] == f"{future_date}T09:00"
        assert new_booking["endsAt"] == f"{future_date}T17:00"
        # New booking should be Requested
        assert new_booking["status"] == "Requested"

    def test_old_booking_is_marked_replaced(
        self, client, auth_headers, event_repository, booking_repository
    ):
        """Original booking status changes to Replaced."""
        from datetime import datetime, timedelta

        from app.booking_store import Booking
        from app.event_store import Event

        # Create an event
        future_date = (datetime.now().date() + timedelta(days=30)).isoformat()
        event = Event(
            id=1,
            title="Tech Conference",
            purpose="Annual tech conference",
            description="",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            expected_attendance=100,
            organiser_id=1,
            organiser_name="Dylan",
            status="Approved",
            coordinator_id=COORDINATOR_ID,
            created_at="2026-10-01T10:00:00",
            updated_at="2026-10-01T10:00:00",
        )
        event_repository.events.append(event)

        # Create a booking with NEEDS_REPLACEMENT status
        old_booking = Booking(
            id=1,
            event_id=1,
            venue_id=1,
            venue_name="Great Hall",
            starts_at=f"{future_date}T09:00",
            ends_at=f"{future_date}T17:00",
            status=BookingStatus.NEEDS_REPLACEMENT,
            requested_by_id=COORDINATOR_ID,
            requested_at="2026-10-01T10:30:00",
            replacement_reason="Unexpected flooding",
        )
        booking_repository.bookings.append(old_booking)

        # Request a replacement venue
        client.post(
            f"/bookings/{old_booking.id}/request-replacement",
            json={"venueId": "2"},
            headers=auth_headers("Event Coordinator"),
        )

        # Check old booking is now REPLACED
        updated_old = booking_repository.get_booking(old_booking.id)
        assert updated_old is not None
        assert updated_old.status is BookingStatus.REPLACED

    def test_replaced_booking_kept_for_history(
        self, client, auth_headers, booking_repository
    ):
        """Replaced booking remains in database, not deleted."""
        pytest.skip("Not implemented yet")

    def test_other_bookings_on_event_untouched(
        self, client, auth_headers, event_repository, booking_repository
    ):
        """Only the flagged booking is replaced, others remain unchanged."""
        pytest.skip("Not implemented yet")
