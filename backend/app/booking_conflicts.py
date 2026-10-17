"""Venue Staff see the bookings flagged "Conflict – review needed" — US15.2.

`conflict_flags` marks the bookings that clash after a venue's setup or
turnaround time changes; this is where Venue Staff find them. Each one shows
what a decision needs, as the US16.1 queue does: the event, its Coordinator,
the venue, the booking time and the full occupied window, why it was flagged,
and what it clashes with now. Venue Staff resolve a clash with the tools they
already have (reject a request, or ask the Coordinator to cancel or move one),
and the flag clears on its own once the clash is gone.

Resolved flags are cleared before the list is read, so a hold that has expired
since (which writes nothing) does not leave a stale flag behind.

Venue Staff only, under the same permission that decides booking requests:
reviewing a clash is part of deciding what the venue can support.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field

from app import booking_store, conflict_flags
from app.auth import require_permission
from app.booking_decisions import BookingRequestOut, _Context
from app.permissions import Permission
from app.users import User

router = APIRouter(prefix="/booking-conflicts", tags=["booking-conflicts"])

ReviewsConflicts = Annotated[User, Depends(require_permission(Permission.BOOKINGS_DECIDE))]


class FlaggedBookingOut(BookingRequestOut):
    """A flagged booking, with the clashes found under US15.1's rule right now."""

    #: Always "Conflict – review needed".
    label: str = Field(default=conflict_flags.LABEL)


@router.get("", response_model=list[FlaggedBookingOut])
def list_booking_conflicts(user: ReviewsConflicts) -> list[FlaggedBookingOut]:
    """Every booking flagged "Conflict – review needed", soonest first."""
    conflict_flags.resolve_flagged()
    context = _Context()
    return [
        FlaggedBookingOut(
            **context.request_out(booking, counting_requests=True).model_dump(by_alias=False)
        )
        for booking in booking_store.repository().list_flagged()
    ]
