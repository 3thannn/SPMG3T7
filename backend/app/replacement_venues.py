"""Search for and request replacement venues for flagged bookings — US14.5.

When a booking is flagged NEEDS_REPLACEMENT (US12.2), the Coordinator can search
for available replacement venues for the same time, then request a replacement,
which creates a new booking and marks the old one REPLACED.

US12.4: on a Confirmed event, the flag alone changes nothing; the customer said
the system must not move it on its own. Requesting the replacement is the
Coordinator's act, and it moves the event Confirmed -> Planning, with the
reason in its history, so the new venue goes through Venue Staff, the safety
check and confirming (US4.7) as the first one did. The event's other bookings
are untouched, and the Organiser is told.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app import availability, booking_store, event_store, venue_store, venue_unavailability_store
from app.auth import require_permission
from app.booking_store import Booking, BookingStatus
from app.event_status import CLOSED, EventStatus
from app.events import BookingOut, _booking_out
from app.notifications import notify_back_in_planning
from app.permissions import Permission
from app.users import User
from app.venues import VenueOut, _filter_text, _min_capacity, _to_out

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


def reopen_reason(old: Booking, new_venue_name: str) -> str:
    """US12.4: why a Confirmed event went back to Planning, for its history and the notice."""
    because = f" ({old.replacement_reason})" if old.replacement_reason else ""
    return (
        f"{old.venue_name or 'A venue'} is unavailable{because}, so {new_venue_name} was "
        "requested instead. It needs Venue Staff's approval and a new safety check before "
        "the event is Confirmed again."
    )


@router.get("/{booking_id}/replacement-venues", response_model=list[VenueOut])
def search_replacement_venues(
    booking_id: str,
    user: RequestsBookings,
    min_capacity: Annotated[str, Query(alias="minCapacity")] = "",
    location: str = "",
    accessibility: str = "",
) -> list[VenueOut]:
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

    # Verify the coordinator has access to this booking's event
    event = event_store.repository().get_event(booking.event_id)
    if event is None or event.coordinator_id != user.id:
        raise _not_found()
    if booking.status is not BookingStatus.NEEDS_REPLACEMENT or event.status in CLOSED:
        raise _not_flagged()

    # Get all venues
    all_venues = venue_store.repository().list_venues(venue_store.VenueFilters(
        min_capacity=_min_capacity(min_capacity),
        location=_filter_text(location, field="location"),
        accessibility=_filter_text(accessibility, field="accessibility"),
    ))

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
    US12.4: a Confirmed event goes back to Planning in the same transaction.
    """
    try:
        old_booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        old_booking = None

    if old_booking is None:
        raise _not_found()

    # Verify the coordinator has access to this booking's event
    event = event_store.repository().get_event(old_booking.event_id)
    if event is None or event.coordinator_id != user.id:
        raise _not_found()
    if old_booking.status is not BookingStatus.NEEDS_REPLACEMENT or event.status in CLOSED:
        raise _not_flagged()

    # Validate replacement venue
    venue_id_str = payload.venue_id.strip()
    try:
        new_venue_id = int(venue_id_str)
    except ValueError:
        raise _invalid_venue("That venue is not in the catalogue.") from None

    new_venue = venue_store.repository().get_venue(new_venue_id)
    if new_venue is None:
        raise _invalid_venue("That venue is not in the catalogue.")
    if new_venue_id == old_booking.venue_id:
        raise _invalid_venue("Choose a different venue for the replacement.")

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

    reason = reopen_reason(old_booking, new_venue.name)
    try:
        new_booking = booking_store.repository().request_replacement(
            old_booking.id, venue_id=new_venue_id, actor_id=user.id, reason=reason,
        )
    except booking_store.SlotTaken:
        raise _invalid_venue("That venue is not available for the same time slot.") from None
    except booking_store.StaleBookingStatus:
        raise _not_flagged() from None
    # The database decided whether it moved; this only says so.
    reopened = event_store.repository().get_event(event.id)
    if (
        event.status is EventStatus.CONFIRMED
        and reopened is not None
        and reopened.status is EventStatus.PLANNING
    ):
        notify_back_in_planning(reopened, reason, actor_id=user.id)
    return _booking_out(new_booking)
