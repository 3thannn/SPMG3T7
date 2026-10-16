"""Venue Staff approve or reject venue booking requests — US16.1.

Only bookings Venue Staff can support get confirmed, and the Coordinator knows
where they stand:

* The queue is every Requested booking, oldest request first, with what Venue
  Staff need to decide: the event, venue, booking time, the full occupied
  window including setup and turnaround (US9.4, used by US15.1), headcount and
  layout, and any booking already taking an overlapping slot.
* Approve -> Confirmed. The conflict check (`availability.find_clashes`, the
  US15.1 placeholder) runs again at approval. A clash blocks it and is shown,
  so two requests for the same slot cannot both be approved.
* Reject -> Rejected, with a required reason and an optional suggested
  alternative venue or time. A rejected booking frees its slot.
* Only that booking's row is written. The event and its other bookings are
  left exactly as they were.
* The assigned Coordinator is notified of the decision and reason (US10.2).
* Venue Staff only, and each decision records who and when.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import availability, booking_store, event_store, users, venue_store
from app.auth import require_permission
from app.booking_store import Booking, BookingStatus, SlotTaken, StaleBookingStatus
from app.events import BookingOut, EventError, _booking_out, _invalid_booking
from app.notifications import notify_booking_decision
from app.permissions import Permission
from app.users import User
from app.venue_store import Venue
from app.venue_turnaround import OccupiedBooking

router = APIRouter(prefix="/booking-requests", tags=["booking-requests"])

DecidesBookings = Annotated[User, Depends(require_permission(Permission.BOOKINGS_DECIDE))]

#: The reason and suggestion are TEXT. The cap keeps them readable, as US14.2's is.
DECISION_TEXT_MAX = 2000


class ClashOut(BaseModel):
    """A booking that already takes a slot overlapping this one."""

    booking_id: str = Field(serialization_alias="bookingId")
    event_title: str = Field(serialization_alias="eventTitle")
    status: BookingStatus
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    occupied_from: str = Field(serialization_alias="occupiedFrom")
    occupied_to: str = Field(serialization_alias="occupiedTo")


class BookingRequestOut(BookingOut):
    """A booking as Venue Staff decide it: Venue Staff cannot open the event."""

    event_title: str = Field(serialization_alias="eventTitle")
    coordinator_name: str = Field(serialization_alias="coordinatorName")
    #: The full occupied window: start minus setup, end plus turnaround.
    occupied_from: str = Field(serialization_alias="occupiedFrom")
    occupied_to: str = Field(serialization_alias="occupiedTo")
    setup_minutes: int = Field(serialization_alias="setupMinutes")
    turnaround_minutes: int = Field(serialization_alias="turnaroundMinutes")
    #: Bookings already taking an overlapping slot. Approval is blocked while any remain.
    clashes: list[ClashOut]


class Rejection(BaseModel):
    reason: str = ""
    suggestion: str = ""


def _iso(moment) -> str:
    return moment.isoformat(timespec="minutes")


class _Context:
    """Event titles, Coordinator names and venues, each read once per request."""

    def __init__(self) -> None:
        self._titles: dict[int, str] = {}
        self._venues: dict[int, Venue | None] = {}
        self._at_venue: dict[int, list[Booking]] = {}
        self._names: dict[int, str] | None = None

    def title(self, event_id: int) -> str:
        if event_id not in self._titles:
            event = event_store.repository().get_event(event_id)
            self._titles[event_id] = event.title if event else ""
        return self._titles[event_id]

    def coordinator_name(self, event_id: int) -> str:
        event = event_store.repository().get_event(event_id)
        if event is None or event.coordinator_id is None:
            return ""
        if self._names is None:
            self._names = {user.id: user.name for user in users.list_users()}
        return self._names.get(event.coordinator_id, "")

    def venue(self, venue_id: int) -> Venue | None:
        if venue_id not in self._venues:
            self._venues[venue_id] = venue_store.repository().get_venue(venue_id)
        return self._venues[venue_id]

    def bookings_at(self, venue_id: int) -> list[Booking]:
        if venue_id not in self._at_venue:
            self._at_venue[venue_id] = booking_store.repository().list_for_venue(venue_id)
        return self._at_venue[venue_id]

    def clashes(self, booking: Booking) -> list[OccupiedBooking]:
        return availability.find_clashes(
            booking, self.venue(booking.venue_id), self.bookings_at(booking.venue_id)
        )

    def clash_out(self, clash: OccupiedBooking) -> ClashOut:
        other = clash.booking
        return ClashOut(
            booking_id=str(other.id),
            event_title=self.title(other.event_id),
            status=other.status,
            starts_at=other.starts_at,
            ends_at=other.ends_at,
            occupied_from=_iso(clash.occupied_from),
            occupied_to=_iso(clash.occupied_to),
        )

    def request_out(self, booking: Booking) -> BookingRequestOut:
        venue = self.venue(booking.venue_id)
        window = availability.occupied(booking, venue)
        setup, turnaround = venue.buffers if venue is not None else (0, 0)
        return BookingRequestOut(
            **_booking_out(booking).model_dump(),
            event_title=self.title(booking.event_id),
            coordinator_name=self.coordinator_name(booking.event_id),
            occupied_from=_iso(window.occupied_from),
            occupied_to=_iso(window.occupied_to),
            setup_minutes=setup,
            turnaround_minutes=turnaround,
            clashes=(
                [self.clash_out(clash) for clash in self.clashes(booking)]
                if booking.status is BookingStatus.REQUESTED
                else []
            ),
        )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": EventError.BOOKING_NOT_FOUND, "message": "That booking does not exist."},
    )


_ALREADY = {
    BookingStatus.CONFIRMED: "This booking has already been confirmed.",
    BookingStatus.REJECTED: "This booking has already been rejected.",
    BookingStatus.CANCELLED: "The Coordinator cancelled this booking.",
    BookingStatus.HELD: "This is a tentative hold. The Coordinator has not requested it yet.",
}


def _not_requested(current: BookingStatus) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": _ALREADY.get(current, "Only a requested booking can be decided."),
            "reason": "not-requested",
        },
    )


def _slot_taken(booking: Booking, context: _Context) -> HTTPException:
    clashes = [context.clash_out(clash) for clash in context.clashes(booking)]
    venue = context.venue(booking.venue_id)
    named = "; ".join(
        f'"{clash.event_title or "another event"}" ({clash.status}, occupying '
        f"{clash.occupied_from.replace('T', ' ')} to {clash.occupied_to.replace('T', ' ')})"
        for clash in clashes
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": (
                f"{venue.name if venue else 'This venue'} is already taken for this slot"
                + (f" by {named}." if named else ".")
                + " Reject this request, or resolve the clash first."
            ),
            "reason": "slot-taken",
            "clashes": [clash.model_dump(by_alias=True) for clash in clashes],
        },
    )


def _requested(booking_id: str) -> Booking:
    try:
        booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        booking = None
    if booking is None:
        raise _not_found()
    if booking.status is not BookingStatus.REQUESTED:
        raise _not_requested(booking.status)
    return booking


def _current_status(booking_id: int) -> BookingStatus:
    current = booking_store.repository().get_booking(booking_id)
    return current.status if current else BookingStatus.CANCELLED


def _notify(booking: Booking, **decision) -> None:
    event = event_store.repository().get_event(booking.event_id)
    if event is not None:
        notify_booking_decision(event, booking.venue_name, **decision)


@router.get("", response_model=list[BookingRequestOut])
def list_booking_requests(user: DecidesBookings) -> list[BookingRequestOut]:
    """Every Requested booking, oldest request first, with what a decision needs."""
    context = _Context()
    return [context.request_out(item) for item in booking_store.repository().list_requested()]


@router.post("/{booking_id}/approve", response_model=BookingRequestOut)
def approve_booking_request(booking_id: str, user: DecidesBookings) -> BookingRequestOut:
    """Requested -> Confirmed, unless the slot is already taken (US15.1, again)."""
    booking = _requested(booking_id)
    context = _Context()
    if context.clashes(booking):
        raise _slot_taken(booking, context)
    try:
        confirmed = booking_store.repository().approve(booking.id, actor_id=user.id)
    except SlotTaken:
        # Another approval took the slot between the check above and the write.
        raise _slot_taken(booking, _Context()) from None
    except StaleBookingStatus:
        raise _not_requested(_current_status(booking.id)) from None
    _notify(confirmed, confirmed=True)
    return context.request_out(confirmed)


@router.post("/{booking_id}/reject", response_model=BookingRequestOut)
def reject_booking_request(
    booking_id: str, payload: Rejection, user: DecidesBookings
) -> BookingRequestOut:
    """Requested -> Rejected with a reason, and optionally a suggested alternative."""
    booking = _requested(booking_id)
    reason = payload.reason.strip()
    suggestion = payload.suggestion.strip()
    if not reason:
        raise _invalid_booking("Give the Coordinator a reason for rejecting this booking.")
    if len(reason) > DECISION_TEXT_MAX:
        raise _invalid_booking(f"Keep the reason to {DECISION_TEXT_MAX} characters or fewer.")
    if len(suggestion) > DECISION_TEXT_MAX:
        raise _invalid_booking(
            f"Keep the suggestion to {DECISION_TEXT_MAX} characters or fewer."
        )
    try:
        rejected = booking_store.repository().reject(
            booking.id, actor_id=user.id, reason=reason, suggestion=suggestion
        )
    except StaleBookingStatus:
        raise _not_requested(_current_status(booking.id)) from None
    _notify(rejected, confirmed=False, reason=reason, suggestion=suggestion)
    return _Context().request_out(rejected)
