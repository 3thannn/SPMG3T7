"""Search for and request replacement venues for flagged bookings — US14.5.

When a booking is flagged NEEDS_REPLACEMENT (US12.2), the Coordinator can search
for available replacement venues for the same time, then request a replacement,
which creates a new booking and marks the old one REPLACED.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import availability, booking_store, event_store, venue_store, venue_unavailability_store
from app.auth import require_permission
from app.booking_store import BookingStatus
from app.events import BookingOut, _booking_out
from app.permissions import Permission
from app.users import User
from app.venues import VenueOut, _to_out

router = APIRouter(prefix="/bookings", tags=["bookings"])

RequestsBookings = Annotated[User, Depends(require_permission(Permission.BOOKINGS_REQUEST))]


class ReplacementRequest(BaseModel):
    """The venue ID for the replacement booking."""

    venue_id: str = Field(serialization_alias="venueId", validation_alias="venueId")


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "booking_not_found", "message": "That booking does not exist."},
    )


def _not_flagged() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "not_flagged",
            "message": (
                "Only a booking flagged 'Needs replacement' can have a "
                "replacement searched."
            ),
        },
    )


def _invalid_venue(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "invalid_venue", "message": message},
    )


@router.get("/{booking_id}/replacement-venues", response_model=list[VenueOut])
def search_replacement_venues(booking_id: str, user: RequestsBookings) -> list[VenueOut]:
    """Search for available venues at the same time as a flagged booking.

    US14.5 AC1: From a 'Needs replacement' booking, search shows only venues
    free for the same time (US15.1), excluding the original venue.
    """
    try:
        booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        booking = None

    if booking is None:
        raise _not_found()

    if booking.status is not BookingStatus.NEEDS_REPLACEMENT:
        raise _not_flagged()

    # Verify the coordinator has access to this booking's event
    event = event_store.repository().get_event(booking.event_id)
    if event is None or event.coordinator_id != user.id:
        raise _not_found()

    # Get all venues
    all_venues = venue_store.repository().list_venues()

    # Filter to available venues (excluding the original venue)
    available_venues: list[VenueOut] = []
    for venue in all_venues:
        if venue.id == booking.venue_id:
            # Exclude the original venue
            continue

        # Check if venue is available for the booking's time slot
        bookings_at_venue = booking_store.repository().list_for_venue(venue.id)
        unavailability = venue_unavailability_store.repository().list_for_venue(venue.id)

        slot_check = availability.check_slot(
            venue,
            booking.starts_at,
            booking.ends_at,
            bookings_at_venue=bookings_at_venue,
            unavailability=unavailability,
        )

        if slot_check.available:
            available_venues.append(_to_out(venue))

    return available_venues


@router.post("/{booking_id}/request-replacement", response_model=BookingOut, status_code=201)
def request_replacement_venue(
    booking_id: str, payload: ReplacementRequest, user: RequestsBookings
) -> BookingOut:
    """Request a replacement venue for a flagged booking.

    US14.5 AC2: Creates a new booking request on the same event for the
    replacement venue. Old booking is marked Replaced and kept for history.
    """
    try:
        old_booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        old_booking = None

    if old_booking is None:
        raise _not_found()

    if old_booking.status is not BookingStatus.NEEDS_REPLACEMENT:
        raise _not_flagged()

    # Verify the coordinator has access to this booking's event
    event = event_store.repository().get_event(old_booking.event_id)
    if event is None or event.coordinator_id != user.id:
        raise _not_found()

    # Validate replacement venue
    venue_id_str = payload.venue_id.strip()
    try:
        new_venue_id = int(venue_id_str)
    except ValueError:
        raise _invalid_venue("That venue is not in the catalogue.") from None

    new_venue = venue_store.repository().get_venue(new_venue_id)
    if new_venue is None:
        raise _invalid_venue("That venue is not in the catalogue.")

    # Check if replacement venue is available
    bookings_at_venue = booking_store.repository().list_for_venue(new_venue_id)
    unavailability = venue_unavailability_store.repository().list_for_venue(new_venue_id)

    slot_check = availability.check_slot(
        new_venue,
        old_booking.starts_at,
        old_booking.ends_at,
        bookings_at_venue=bookings_at_venue,
        unavailability=unavailability,
    )

    if not slot_check.available:
        raise _invalid_venue("That venue is not available for the same time slot.")

    # Create new booking for replacement venue
    new_booking = booking_store.repository().create(
        event_id=old_booking.event_id,
        venue_id=new_venue_id,
        starts_at=old_booking.starts_at,
        ends_at=old_booking.ends_at,
        requested_by_id=user.id,
        headcount=old_booking.headcount or event.expected_attendance or 0,
        required_layout=old_booking.required_layout,
        required_facilities=old_booking.required_facilities,
        accessibility_needs=old_booking.accessibility_needs,
    )

    # Mark old booking as REPLACED
    booking_store.repository().mark_replaced(old_booking.id)

    return _booking_out(new_booking)
