"""Venue Staff approve or reject venue booking requests — US16.1.

Only bookings Venue Staff can support get confirmed, and the Coordinator knows
where they stand:

* The queue is every Requested booking, oldest request first, with what Venue
  Staff need to decide: the event, venue, booking time, the full occupied
  window including setup and turnaround (US9.4, used by US15.1), headcount and
  layout, and any booking already taking an overlapping slot.
* Approve -> Confirmed, or (US14.3, Week 9) approve as a tentative hold ->
  Held until an expiry Venue Staff choose, which the Coordinator then confirms
  (`app.events`) before it lapses. Either way the conflict check (US15.1, `availability`) runs again
  at approval: a Confirmed or unexpired Held booking whose occupied window
  overlaps, or a venue unavailability period, blocks it and is shown, so two
  requests for the same slot cannot both be approved. Another Requested booking
  does not block it; see `availability` for why.
* Reject -> Rejected, with a required reason and an optional suggested
  alternative venue or time. A rejected booking frees its slot.
* Only that booking's row is written. The event and its other bookings are
  left exactly as they were.
* The assigned Coordinator is notified of the decision and reason (US10.2).
* US10.4: approving a replacement venue (US14.5/US12.4) tells the event's
  registered Attendees where it now is.
* Venue Staff only, and each decision records who and when.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app import (
    arrangement_review,
    availability,
    booking_store,
    conflict_flags,
    event_store,
    users,
    venue_store,
    venue_unavailability_store,
)
from app.auth import require_permission
from app.availability import SlotCheck
from app.booking_store import Booking, BookingStatus, SlotTaken, StaleBookingStatus
from app.events import BookingOut, EventError, _booking_out, _invalid_booking
from app.holds import expiry
from app.notifications import (
    notify_attendees_of_new_venue,
    notify_booking_decision,
    notify_hold_placed,
)
from app.permissions import Permission
from app.users import User
from app.venue_store import Venue
from app.venue_turnaround import OccupiedBooking
from app.venue_unavailability_store import Unavailability

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


class UnavailableOut(BaseModel):
    """US15.1: a venue unavailability period (US12.1) the booking overlaps."""

    id: str
    #: "YYYY-MM-DD", inclusive at both ends.
    start_date: str = Field(serialization_alias="startDate")
    end_date: str = Field(serialization_alias="endDate")
    reason: str


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
    #: US15.1: unavailability periods it overlaps. Approval is blocked by these too.
    unavailable: list[UnavailableOut] = Field(default_factory=list)


class Approval(BaseModel):
    """US14.3: give `holdUntil` to approve as a tentative hold rather than outright."""

    model_config = ConfigDict(populate_by_name=True)

    hold_until: str | None = Field(default=None, alias="holdUntil")


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
        self._blackouts: dict[int, list[Unavailability]] = {}
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

    def unavailability(self, venue_id: int) -> list[Unavailability]:
        if venue_id not in self._blackouts:
            self._blackouts[venue_id] = venue_unavailability_store.repository().list_for_venue(
                venue_id
            )
        return self._blackouts[venue_id]

    def check(self, booking: Booking, *, counting_requests: bool = False) -> SlotCheck:
        """US15.1 for a booking on record. Approval's rule unless told to count requests."""
        return availability.check_booking(
            booking,
            self.venue(booking.venue_id),
            self.bookings_at(booking.venue_id),
            self.unavailability(booking.venue_id),
            counting_requests=counting_requests,
        )

    def unavailable_out(self, entry: Unavailability) -> UnavailableOut:
        return UnavailableOut(
            id=str(entry.id),
            start_date=entry.start_date.isoformat(),
            end_date=entry.end_date.isoformat(),
            reason=entry.other_reason if entry.reason_type == "other" else "",
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

    def request_out(
        self, booking: Booking, *, counting_requests: bool = False
    ) -> BookingRequestOut:
        """A booking with its window and what it clashes with now.

        The queue checks Requested bookings under approval's rule. US15.2's
        flagged list passes `counting_requests` to check any booking that still
        holds its venue under US15.1's own rule.
        """
        venue = self.venue(booking.venue_id)
        window = availability.occupied(booking, venue)
        setup, turnaround = availability.buffers(venue)
        checked = booking.status is BookingStatus.REQUESTED or (
            counting_requests and booking.holds_venue
        )
        found = self.check(booking, counting_requests=counting_requests) if checked else None
        return BookingRequestOut(
            **_booking_out(booking).model_dump(),
            event_title=self.title(booking.event_id),
            coordinator_name=self.coordinator_name(booking.event_id),
            occupied_from=_iso(window.occupied_from),
            occupied_to=_iso(window.occupied_to),
            setup_minutes=setup,
            turnaround_minutes=turnaround,
            clashes=[self.clash_out(clash) for clash in found.bookings] if found else [],
            unavailable=[self.unavailable_out(entry) for entry in found.blackouts] if found else [],
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
    BookingStatus.HELD: (
        "This booking is already approved as a tentative hold. The Coordinator confirms it."
    ),
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
    found = context.check(booking)
    clashes = [context.clash_out(clash) for clash in found.bookings]
    venue = context.venue(booking.venue_id)
    name = venue.name if venue else "This venue"
    named = "; ".join(
        f'"{clash.event_title or "another event"}" ({clash.status}, occupying '
        f"{clash.occupied_from.replace('T', ' ')} to {clash.occupied_to.replace('T', ' ')})"
        for clash in clashes
    )
    sentences: list[str] = []
    if named or not found.blackouts:
        by = f" by {named}." if named else "."
        sentences.append(f"{name} is already taken for this slot{by}")
    if found.blackouts:
        # US15.1: a venue unavailability period blocks approval as a booking does.
        sentences.append(
            f"{name} is unavailable for this slot: "
            + "; ".join(availability.describe_blackout(entry) for entry in found.blackouts)
            + "."
        )
    sentences.append("Reject this request, or resolve the clash first.")
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": " ".join(sentences),
            "reason": "slot-taken",
            "clashes": [clash.model_dump(by_alias=True) for clash in clashes],
            "unavailable": [
                context.unavailable_out(entry).model_dump(by_alias=True)
                for entry in found.blackouts
            ],
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


def _notify_attendees_if_replaced(booking: Booking) -> None:
    """US10.4: a confirmed replacement venue is news for the event's Attendees."""
    siblings = booking_store.repository().list_for_event(booking.event_id)
    event = event_store.repository().get_event(booking.event_id)
    if event is None or not booking_store.is_replacement(booking, siblings):
        return
    venue = venue_store.repository().get_venue(booking.venue_id)
    notify_attendees_of_new_venue(
        event, booking.venue_name or "a new venue", venue.location if venue else ""
    )


@router.get("", response_model=list[BookingRequestOut])
def list_booking_requests(user: DecidesBookings) -> list[BookingRequestOut]:
    """Every Requested booking, oldest request first, with what a decision needs."""
    context = _Context()
    return [context.request_out(item) for item in booking_store.repository().list_requested()]


@router.post("/{booking_id}/approve", response_model=BookingRequestOut)
def approve_booking_request(
    booking_id: str, user: DecidesBookings, payload: Approval | None = None
) -> BookingRequestOut:
    """Requested -> Confirmed, unless the slot is already taken (US15.1, again).

    US14.3: with `holdUntil`, Requested -> Held instead: approved, and kept for
    the Coordinator until then. The expiry follows the hold rules (`expiry`).
    """
    booking = _requested(booking_id)
    raw_expiry = payload.hold_until if payload is not None else None
    expires_at = (
        expiry(raw_expiry, starts_at=booking.starts_at) if (raw_expiry or "").strip() else ""
    )
    context = _Context()
    if not context.check(booking).available:
        raise _slot_taken(booking, context)
    try:
        if expires_at:
            held = booking_store.repository().approve_as_hold(
                booking.id, actor_id=user.id, expires_at=expires_at
            )
        else:
            confirmed = booking_store.repository().approve(booking.id, actor_id=user.id)
    except SlotTaken:
        # Another approval took the slot between the check above and the write.
        raise _slot_taken(booking, _Context()) from None
    except StaleBookingStatus:
        raise _not_requested(_current_status(booking.id)) from None
    if expires_at:
        event = event_store.repository().get_event(held.event_id)
        if event is not None:
            notify_hold_placed(event, held.venue_name or "a venue", expires_at)
        return context.request_out(held)
    _notify(confirmed, confirmed=True)
    _notify_attendees_if_replaced(confirmed)
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
    # US15.2: a rejected booking frees its slot, which may resolve a flagged clash.
    conflict_flags.resolve_quietly(rejected.venue_id)
    arrangement_review.refresh_if_reviewed(rejected.event_id)
    if rejected.conflict is not None or rejected.event_conflict_reason:
        rejected = booking_store.repository().get_booking(rejected.id) or rejected
    return _Context().request_out(rejected)
