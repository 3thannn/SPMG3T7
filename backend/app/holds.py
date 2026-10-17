"""Tentative venue holds — US14.3.

Venue Staff keep a slot for a Coordinator who is still finalising, without
blocking the venue forever. A hold is a venue booking with status Held, linked
to an event and so to the event's Coordinator, with an expiry that must be in
the future. While it is Held and has not expired, the slot counts as taken
(`Booking.holds_venue`, which US9.4's re-check and US15.1's availability check
read). The Coordinator turns it into a request from the event page
(`POST /events/{id}/bookings/{bookingId}/request` in `app.events`). A hold is
never Confirmed on its own.

Venue Staff hold no event permissions, so these routes show them only what a
hold needs: the events that can take one, and the holds already at a venue.

Assumptions, not customer-confirmed:

* Only Venue Staff place holds (the story's own assumption).
* A hold can be placed only for an event a Coordinator can request venues for:
  assigned, and Approved or Planning (US14.1's `check_booking`).
* A hold expires no later than the booking starts. Keeping a slot past the
  moment it is used would mean nothing.

US15.1: a hold is placed only where the slot is free under the same rule a
request is checked with, setup and turnaround included. Venue Staff see every
event, so a clash names the other event too.
"""

import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app import booking_store, event_store, users, venue_store
from app.auth import require_permission
from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus, booking_refusal_message, check_booking
from app.event_store import Event
from app.events import (
    BookingOut,
    EventError,
    _booking_out,
    _booking_time,
    _invalid_booking,
    _venue_missing,
    not_available,
    slot_check,
)
from app.permissions import Permission
from app.users import User

router = APIRouter(prefix="/holds", tags=["holds"])

PlacesHolds = Annotated[User, Depends(require_permission(Permission.HOLDS_PLACE))]

_ISO_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?")
_ID = re.compile(r"[0-9]+")


class HoldableEventOut(BaseModel):
    """An event Venue Staff may hold a venue for, and whose slot it would keep."""

    id: str
    title: str
    status: EventStatus
    coordinator_name: str = Field(serialization_alias="coordinatorName")
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")


class HoldOut(BookingOut):
    """A hold, with the event it keeps the slot for: Venue Staff cannot open events."""

    event_title: str = Field(serialization_alias="eventTitle")


class HoldInput(BaseModel):
    """What Venue Staff send to place a hold. Text, so a bad value is our 400."""

    model_config = ConfigDict(populate_by_name=True)

    venue_id: str | int | None = Field(default=None, alias="venueId")
    event_id: str | int | None = Field(default=None, alias="eventId")
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")
    expires_at: str | None = Field(default=None, alias="expiresAt")


def _holdable(event: Event) -> bool:
    return event.coordinator_id is not None and check_booking(status=event.status) is None


def _coordinator_names() -> dict[int, str]:
    return {user.id: user.name for user in users.list_users()}


def _hold_out(booking: Booking, titles: dict[int, str]) -> HoldOut:
    return HoldOut(
        **_booking_out(booking).model_dump(),
        event_title=titles.get(booking.event_id, ""),
    )


def _event_title(event_id: int) -> str:
    event = event_store.repository().get_event(event_id)
    return event.title if event is not None else ""


def _expiry(raw: str | None, *, starts: datetime) -> str:
    """US14.3: required, in the future, and no later than the booking starts."""
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
    if expires > starts:
        raise _invalid_booking("The hold must expire no later than the booking starts.")
    return text


def _refused(message: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": EventError.REFUSED, "message": message, "reason": reason},
    )


@router.get("/events", response_model=list[HoldableEventOut])
def list_holdable_events(user: PlacesHolds) -> list[HoldableEventOut]:
    """The events a hold can be placed for: assigned, and Approved or Planning."""
    names = _coordinator_names()
    events = event_store.repository().list_events(organiser_id=None, include_drafts=False)
    return [
        HoldableEventOut(
            id=str(event.id),
            title=event.title,
            status=event.status,
            coordinator_name=names.get(event.coordinator_id or 0, ""),
            starts_at=event.starts_at,
            ends_at=event.ends_at,
        )
        for event in sorted(events, key=lambda item: (item.starts_at, item.id))
        if _holdable(event)
    ]


@router.get("", response_model=list[HoldOut])
def list_holds(
    user: PlacesHolds, venue_id: Annotated[str, Query(alias="venueId")] = ""
) -> list[HoldOut]:
    """The holds at one venue, soonest first, expired ones included and flagged."""
    if not _ID.fullmatch(venue_id.strip()):
        raise _venue_missing()
    bookings = booking_store.repository().list_for_venue(int(venue_id))
    held = [booking for booking in bookings if booking.status is BookingStatus.HELD]
    titles = {booking.event_id: _event_title(booking.event_id) for booking in held}
    return [_hold_out(booking, titles) for booking in held]


@router.post("", response_model=HoldOut, status_code=status.HTTP_201_CREATED)
def place_hold(payload: HoldInput, user: PlacesHolds) -> HoldOut:
    """US14.3: keep a venue's slot for an event's Coordinator until the expiry.

    400 for what the form got wrong, then 409 for an event that cannot take a
    hold however well-formed the request is.
    """
    raw_venue = "" if payload.venue_id is None else str(payload.venue_id).strip()
    if not raw_venue:
        raise _invalid_booking("Choose a venue.")
    if not _ID.fullmatch(raw_venue):
        raise _venue_missing()
    raw_event = "" if payload.event_id is None else str(payload.event_id).strip()
    if not raw_event:
        raise _invalid_booking("Choose the event to hold this venue for.")
    event = (
        event_store.repository().get_event(int(raw_event)) if _ID.fullmatch(raw_event) else None
    )
    if event is None or event.status is EventStatus.DRAFT:
        raise _invalid_booking("That event does not exist.")

    starts_at, start = _booking_time(payload.starts_at, which="start")
    ends_at, end = _booking_time(payload.ends_at, which="end")
    if end <= start:
        raise _invalid_booking("The booking must end after it starts.")
    if start <= booking_store.local_now():
        raise _invalid_booking("A hold cannot start in the past.")
    expires_at = _expiry(payload.expires_at, starts=start)

    venue = venue_store.repository().get_venue(int(raw_venue))
    if venue is None:
        raise _venue_missing()
    refusal = check_booking(status=event.status)
    if refusal is not None:
        raise _refused(booking_refusal_message(refusal), str(refusal))
    if event.coordinator_id is None:
        raise _refused(
            "Assign a Coordinator to this event before holding a venue for it.",
            "no-coordinator",
        )
    # US15.1: a hold takes its slot, so it is placed only where the slot is free.
    found = slot_check(venue.id, starts_at, ends_at, venue=venue)
    if not found.available:
        titles = {item.booking.id: _event_title(item.booking.event_id) for item in found.bookings}
        raise not_available(venue.name, found, titles)

    hold = booking_store.repository().place_hold(
        event_id=event.id,
        venue_id=venue.id,
        starts_at=starts_at,
        ends_at=ends_at,
        expires_at=expires_at,
        held_by_id=user.id,
        # The table refuses a headcount below 1; no attendance is no headcount.
        headcount=event.expected_attendance or None,
    )
    return _hold_out(hold, {event.id: event.title})
