"""Tentative venue holds — US14.3, US14.6.

Week 9 settled the order: a tentative hold starts after venue approval. Venue
Staff approve a booking request as a hold, with an expiry
(`POST /booking-requests/{id}/approve` with `holdUntil`, in
`app.booking_decisions`), and the booking is Held. While it is Held and has not
expired, the slot counts as taken (`Booking.holds_venue`, which US9.4's re-check
and US15.1's availability check read). The Coordinator confirms it from the
event page before it expires (`POST /events/{id}/bookings/{bookingId}/confirm`
in `app.events`); if they do not, it lapses and the slot is free again (US14.4).

These routes are what Venue Staff do with a hold once it exists (US14.6, Week 9:
Venue Staff set and update the hold duration):

* list the holds at a venue, expired ones included as history;
* change a hold's expiry, while it is still Held and has not lapsed;
* release a hold early, with a reason.

The event's Coordinator is told of each change. Venue Staff hold no event
permissions, so a hold carries its event's title.

Assumptions, not customer-confirmed:

* A hold expires no later than the booking starts. Keeping a slot past the
  moment it is used would mean nothing. That is the maximum duration.
* A released hold is Cancelled, with who released it, when and why, as a
  Coordinator's cancellation is (US14.2).
"""

import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app import arrangement_review, booking_store, conflict_flags, event_store
from app.auth import require_permission
from app.booking_store import Booking, BookingStatus, StaleBookingStatus
from app.events import (
    CANCELLATION_REASON_MAX,
    BookingOut,
    EventError,
    _booking_not_found,
    _booking_out,
    _invalid_booking,
    _venue_missing,
)
from app.notifications import notify_hold_released, notify_hold_updated
from app.permissions import Permission
from app.users import User

router = APIRouter(prefix="/holds", tags=["holds"])

ManagesHolds = Annotated[User, Depends(require_permission(Permission.HOLDS_MANAGE))]

_ISO_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?")
_ID = re.compile(r"[0-9]+")


class HoldOut(BookingOut):
    """A hold, with the event it keeps the slot for: Venue Staff cannot open events."""

    event_title: str = Field(serialization_alias="eventTitle")


class HoldUpdate(BaseModel):
    """US14.6: the new expiry. Text, so a bad value is our 400."""

    model_config = ConfigDict(populate_by_name=True)

    expires_at: str | None = Field(default=None, alias="expiresAt")


class HoldRelease(BaseModel):
    reason: str = ""


def _hold_out(booking: Booking, titles: dict[int, str]) -> HoldOut:
    return HoldOut(
        **_booking_out(booking).model_dump(),
        event_title=titles.get(booking.event_id, ""),
    )


def _event_title(event_id: int) -> str:
    event = event_store.repository().get_event(event_id)
    return event.title if event is not None else ""


def expiry(raw: str | None, *, starts_at: str) -> str:
    """US14.3/US14.6: required, in the future, and no later than the booking starts."""
    text = (raw or "").strip()
    if not text:
        raise _invalid_booking("Give the hold an expiry date and time.")
    if not _ISO_DATETIME.fullmatch(text):
        raise _invalid_booking("Give the expiry as YYYY-MM-DDTHH:MM.")
    try:
        expires = datetime.fromisoformat(text)
    except ValueError:
        raise _invalid_booking(f"The expiry {text} is not a real date and time.") from None
    if expires <= booking_store.local_now():
        raise _invalid_booking("The hold must expire in the future.")
    try:
        starts = datetime.fromisoformat(starts_at)
    except ValueError:
        starts = None
    if starts is not None and expires > starts:
        raise _invalid_booking("The hold must expire no later than the booking starts.")
    return text


def _refused(message: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": EventError.REFUSED, "message": message, "reason": reason},
    )


def _live_hold(booking_id: str) -> Booking:
    """A booking that is a hold Venue Staff can still change: Held, not yet lapsed."""
    booking = (
        booking_store.repository().get_booking(int(booking_id))
        if _ID.fullmatch(booking_id.strip())
        else None
    )
    if booking is None:
        raise _booking_not_found()
    if booking.hold_expired:
        raise _refused(
            f"The hold on {booking.venue_name or 'this venue'} expired at "
            f"{booking.hold_expires_at.replace('T', ' ')[:16]}, so its slot is already free.",
            "hold-expired",
        )
    if booking.status is not BookingStatus.HELD:
        message = (
            "The Coordinator has already confirmed this booking."
            if booking.status is BookingStatus.CONFIRMED
            else "This hold has already been released or cancelled."
            if booking.status is BookingStatus.CANCELLED
            else "Only a tentative hold can be changed or released."
        )
        raise _refused(message, "not-held")
    return booking


def _lost_race(booking: Booking) -> HTTPException:
    """A write that matched nothing: the sweep, the Coordinator or another
    member of staff moved the hold on first. Say what it is now."""
    _live_hold(str(booking.id))
    return _refused("This hold changed while you were working. Reload it and try again.", "stale")


@router.get("", response_model=list[HoldOut])
def list_holds(
    user: ManagesHolds, venue_id: Annotated[str, Query(alias="venueId")] = ""
) -> list[HoldOut]:
    """The holds at one venue, soonest first, expired ones included and flagged.

    US14.4: a hold the sweep marked Expired stays on the list as history.
    """
    if not _ID.fullmatch(venue_id.strip()):
        raise _venue_missing()
    bookings = booking_store.repository().list_for_venue(int(venue_id))
    held = [
        booking
        for booking in bookings
        if booking.status in (BookingStatus.HELD, BookingStatus.EXPIRED)
    ]
    titles = {booking.event_id: _event_title(booking.event_id) for booking in held}
    return [_hold_out(booking, titles) for booking in held]


@router.patch("/{booking_id}", response_model=HoldOut)
def update_hold(booking_id: str, payload: HoldUpdate, user: ManagesHolds) -> HoldOut:
    """US14.6: Venue Staff give a hold a new expiry, longer or shorter.

    Same rules as when the hold was approved: in the future and no later than
    the booking starts. Only a hold still Held and not lapsed can change: an
    expired one already gave its slot back. The Coordinator is told.
    """
    hold = _live_hold(booking_id)
    expires_at = expiry(payload.expires_at, starts_at=hold.starts_at)
    try:
        updated = booking_store.repository().update_hold(hold.id, expires_at=expires_at)
    except StaleBookingStatus:
        raise _lost_race(hold) from None
    event = event_store.repository().get_event(updated.event_id)
    if event is not None:
        notify_hold_updated(event, updated.venue_name or "a venue", expires_at)
    return _hold_out(updated, {updated.event_id: event.title if event else ""})


@router.post("/{booking_id}/release", response_model=HoldOut)
def release_hold(booking_id: str, payload: HoldRelease, user: ManagesHolds) -> HoldOut:
    """US14.6: Venue Staff release a hold before it expires, with a reason.

    The booking is Cancelled with who, when and why, and its slot is free at
    once. The Coordinator is told why.
    """
    hold = _live_hold(booking_id)
    reason = payload.reason.strip()
    if not reason:
        raise _invalid_booking("Give the Coordinator a reason for releasing this hold.")
    if len(reason) > CANCELLATION_REASON_MAX:
        raise _invalid_booking(f"Keep the reason to {CANCELLATION_REASON_MAX} characters or fewer.")
    try:
        released = booking_store.repository().cancel(hold.id, actor_id=user.id, reason=reason)
    except StaleBookingStatus:
        raise _lost_race(hold) from None
    # US15.2: a released hold frees its slot, which may resolve a flagged clash.
    conflict_flags.resolve_quietly(released.venue_id)
    arrangement_review.refresh_if_reviewed(released.event_id)
    event = event_store.repository().get_event(released.event_id)
    if event is not None:
        notify_hold_released(event, released.venue_name or "a venue", reason)
    return _hold_out(released, {released.event_id: event.title if event else ""})
