"""Event routes — US4.1 (see your events and their status) and US4.2 (draft and submit).

These are the endpoints the frontend's event store used to fake in localStorage.
Two rules moved with them, and this is now their enforcement point rather than
their second opinion:

* An Organiser sees the events they own; a Coordinator sees submitted events (US4.1).
* An event goes Draft -> Submitted exactly once, by the Organiser who owns it,
  and the change is timestamped and attributable (US4.2).

The client still checks both so it can disable a button and explain why. That
stays a courtesy. A browser store was trivially editable and a request is not,
which is the whole reason this file exists.

Ids go out as strings for the same reason they do in `auth.Identity`: the client
only ever compares them.
"""

import re
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app import booking_store, event_store, venue_store
from app.auth import CurrentUser, ErrorCode, require_any_permission, require_permission
from app.booking_store import Booking, BookingStatus
from app.event_status import (
    EventStatus,
    booking_refusal_message,
    check_booking,
    check_clarification,
    check_submit,
    clarification_refusal_message,
    refusal_message,
    transition_allowed,
    transition_refusal_message,
)
from app.event_store import Event, StaleEventStatus
from app.permissions import Permission, has_permission
from app.users import User

router = APIRouter(prefix="/events", tags=["events"])

READ_ANY = (Permission.EVENTS_READ_OWN, Permission.EVENTS_READ_SUBMITTED)


class EventError:
    NOT_FOUND = "event_not_found"
    INVALID = "invalid_event"
    REFUSED = "rule_refused"
    INVALID_BOOKING = "invalid_booking"


class StatusChangeOut(BaseModel):
    """One audit entry. `from` is null on the entry that records creation.

    `notes` carries a Coordinator's clarification request (US7.3) or rejection
    reason (US7.1), and is empty on automatic entries. The history is already
    something the Organiser reads, so each message travels with the status
    change that caused it.
    """

    from_status: EventStatus | None = Field(serialization_alias="from")
    to: EventStatus
    at: str
    by_id: str = Field(serialization_alias="byId")
    by_name: str = Field(serialization_alias="byName")
    notes: str = ""


class EventOut(BaseModel):
    id: str
    title: str
    purpose: str
    description: str
    starts_at: str = Field(serialization_alias="startsAt")
    #: `events.end_date`. Empty for an event created through the US4.2 draft
    #: flow, which has no end time to record; set for an event request.
    ends_at: str = Field(serialization_alias="endsAt")
    expected_attendance: int | None = Field(serialization_alias="expectedAttendance")
    status: EventStatus
    organiser_id: str = Field(serialization_alias="organiserId")
    organiser_name: str = Field(serialization_alias="organiserName")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
    #: US8.1: The assigned Event Coordinator's ID, or None if unassigned.
    coordinator_id: str | None = Field(default=None, serialization_alias="coordinatorId")
    history: list[StatusChangeOut]


class EventDraft(BaseModel):
    """What the client sends to create or save an event.

    The fields mirror the writable columns of `events`. A draft may leave any
    individual field empty, but must contain a letter or number somewhere.
    Text is kept exactly as supplied; validation must not rewrite an
    Organiser's event details.

    `purpose` and `expectedAttendance` are nullable columns, so both are
    optional here. An absent attendance is None rather than 0 — the column
    distinguishes "not estimated yet" from an estimate of nobody, and flattening
    the two would lose that.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = ""
    purpose: str = ""
    description: str = ""
    starts_at: str = Field(default="", alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")
    expected_attendance: int | None = Field(default=None, alias="expectedAttendance")


def _to_out(event: Event) -> EventOut:
    return EventOut(
        id=str(event.id),
        title=event.title,
        purpose=event.purpose,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        expected_attendance=event.expected_attendance,
        status=event.status,
        organiser_id=str(event.organiser_id),
        organiser_name=event.organiser_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        coordinator_id=str(event.coordinator_id) if event.coordinator_id is not None else None,
        history=[
            StatusChangeOut(
                from_status=change.from_status,
                to=change.to_status,
                at=change.at,
                by_id=str(change.by_id),
                by_name=change.by_name,
                notes=change.notes,
            )
            for change in event.history
        ],
    )


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": EventError.INVALID, "message": message},
    )


def _require_transition(from_status: EventStatus, to_status: EventStatus) -> None:
    """US4.3: reject every status move outside the workflow allowlist."""
    if transition_allowed(from_status=from_status, to_status=to_status):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": transition_refusal_message(
                from_status=from_status, to_status=to_status
            ),
            "reason": "invalid-transition",
        },
    )


def _not_found() -> HTTPException:
    """The same answer whether the event is missing or simply not the caller's.

    Telling someone an event exists but is not theirs is telling them something
    about another Organiser's work that they had no way to know.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": EventError.NOT_FOUND, "message": "That event no longer exists."},
    )


#: `events.name` is VARCHAR(255) and `events.purpose` VARCHAR(500). Checking the
#: lengths here turns a database error into a sentence the form can show.
TITLE_MAX = 255
PURPOSE_MAX = 500
DRAFT_CONTENT_ERROR = "Enter at least one letter or number in any field to save a draft."


def _has_draft_content(draft: EventDraft) -> bool:
    values = (
        draft.title,
        draft.purpose,
        draft.description,
        draft.starts_at,
        draft.ends_at or "",
        "" if draft.expected_attendance is None else str(draft.expected_attendance),
    )
    return any(character.isalnum() for value in values for character in value)


def _validated(draft: EventDraft) -> EventDraft:
    if not _has_draft_content(draft):
        raise _invalid(DRAFT_CONTENT_ERROR)
    if len(draft.title) > TITLE_MAX:
        raise _invalid(f"Keep the title to {TITLE_MAX} characters or fewer.")
    if len(draft.purpose) > PURPOSE_MAX:
        raise _invalid(f"Keep the purpose to {PURPOSE_MAX} characters or fewer.")
    if draft.expected_attendance is not None and draft.expected_attendance < 0:
        raise _invalid("Expected attendance cannot be negative.")

    start = draft.starts_at.strip()
    end = (draft.ends_at or "").strip()
    if start and end:
        try:
            if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
                raise _invalid("The end date must be after the start date.")
        except ValueError:
            # A malformed datetime is already rejected by the field format at the
            # boundary; if a draft slips through, keep the user-facing message
            # consistent with the form's date validation.
            raise _invalid("Give the event a valid date.") from None
    return draft


def _validate_submission(event: Event) -> None:
    if not event.title.strip():
        raise _invalid("Give the event a title.")
    if not event.starts_at.strip():
        raise _invalid("Give the event a date.")
    if not event.purpose.strip():
        raise _invalid("Give the event a purpose.")
    if event.expected_attendance is None:
        raise _invalid("Give the expected attendance.")
    if event.expected_attendance < 1:
        raise _invalid("Expected attendance must be at least 1.")
    try:
        start_date = date.fromisoformat(event.starts_at[:10])
    except ValueError:
        raise _invalid("Give the event a valid date.") from None
    if start_date < date.today():
        raise _invalid("The start date cannot be in the past.")
    if event.ends_at and event.ends_at.strip():
        try:
            end_date = datetime.fromisoformat(event.ends_at)
            start_date_time = datetime.fromisoformat(event.starts_at)
        except ValueError:
            raise _invalid("Give the event a valid date.") from None
        if end_date <= start_date_time:
            raise _invalid("The end date must be after the start date.")


def _readable(event_id: int, user: User) -> Event:
    """Fetch an event the caller is allowed to see, or 404.

    US8.1: Coordinators can only see events assigned to them."""
    event = event_store.repository().get_event(event_id)
    if event is None:
        raise _not_found()
    sees_own = has_permission(user.role, Permission.EVENTS_READ_OWN)
    owns_event = sees_own and event.organiser_id == user.id
    sees_submitted = has_permission(user.role, Permission.EVENTS_READ_SUBMITTED)

    # US8.1: Coordinators can only see events assigned to them
    is_assigned_coordinator = sees_submitted and event.coordinator_id == user.id

    if not owns_event and not (is_assigned_coordinator and event.status != EventStatus.DRAFT):
        raise _not_found()
    return event


def _as_id(raw: str) -> int:
    """Ids are strings on the wire and integers in the table."""
    try:
        return int(raw)
    except ValueError:
        raise _not_found() from None


@router.get("", response_model=list[EventOut])
def list_events(
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> list[EventOut]:
    """US4.1: an Organiser sees their events; a Coordinator sees assigned non-Drafts.

    US8.1: Coordinators now only see events assigned to them."""
    sees_submitted = has_permission(user.role, Permission.EVENTS_READ_SUBMITTED)
    all_events = event_store.repository().list_events(
        organiser_id=None if sees_submitted else user.id,
        include_drafts=not sees_submitted,
    )

    # US8.1: Filter by coordinator assignment
    if sees_submitted:
        all_events = [e for e in all_events if e.coordinator_id == user.id]

    return [_to_out(event) for event in all_events]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: str,
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> EventOut:
    return _to_out(_readable(_as_id(event_id), user))


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    draft: EventDraft,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_CREATE))],
) -> EventOut:
    """US4.2: a new event always begins as a Draft."""
    clean = _validated(draft)
    created = event_store.repository().create_event(
        title=clean.title,
        purpose=clean.purpose,
        description=clean.description,
        starts_at=clean.starts_at,
        ends_at=clean.ends_at,
        expected_attendance=clean.expected_attendance,
        organiser_id=user.id,
    )
    return _to_out(created)


@router.put("/{event_id}", response_model=EventOut)
def save_event(event_id: str, draft: EventDraft, user: CurrentUser) -> EventOut:
    """US4.2 & US5.2: saving edits content and never moves the status.

    Owner (organiser) can save Draft events without logging changes.
    Coordinator can edit Submitted (or later) events with change tracking.
    """
    event = _readable(_as_id(event_id), user)
    is_owner = event.organiser_id == user.id
    is_coordinator = has_permission(user.role, Permission.EVENTS_EDIT)

    # Coordinators can only edit submitted events (not drafts)
    # Owners can only edit their own draft events
    if is_coordinator and event.status == EventStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ErrorCode.FORBIDDEN,
                "message": (
                    "Coordinators can only edit submitted events. Draft events can "
                    "only be edited by their owner."
                ),
            },
        )

    if not is_owner and not is_coordinator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ErrorCode.FORBIDDEN,
                "message": "Only the Organiser who owns this event or a Coordinator can edit it.",
            },
        )

    clean = _validated(draft)

    # If coordinator is editing (not the owner), use change tracking
    if is_coordinator and not is_owner:
        saved = event_store.repository().save_event_with_tracking(
            event.id,
            title=clean.title,
            purpose=clean.purpose,
            description=clean.description,
            starts_at=clean.starts_at,
            ends_at=clean.ends_at,
            expected_attendance=clean.expected_attendance,
            editor_id=user.id,
            previous_event=event,
        )
    else:
        # Owner editing: no change tracking (original US4.2 behavior)
        saved = event_store.repository().save_event(
            event.id,
            title=clean.title,
            purpose=clean.purpose,
            description=clean.description,
            starts_at=clean.starts_at,
            ends_at=clean.ends_at,
            expected_attendance=clean.expected_attendance,
        )
    return _to_out(saved)


@router.post("/{event_id}/submit", response_model=EventOut)
def submit_event(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_SUBMIT))],
) -> EventOut:
    """US4.2: Draft -> Submitted, once, timestamped and attributable.

    A second submit is refused with the reason, not silently ignored.
    """
    event = _readable(_as_id(event_id), user)
    refusal = check_submit(status=event.status, organiser_id=event.organiser_id, actor_id=user.id)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": refusal_message(refusal),
                "reason": str(refusal),
            },
        )
    _require_transition(event.status, EventStatus.SUBMITTED)
    _validate_submission(event)
    submitted = event_store.repository().submit_event(
        event.id, actor_id=user.id, from_status=event.status
    )
    return _to_out(submitted)


class ClarificationRequest(BaseModel):
    """The message a Coordinator attaches when asking for changes (US7.3)."""

    message: str = ""


#: `status_changes.notes` is unbounded TEXT, so this cap is about keeping a
#: request readable rather than about fitting the column.
CLARIFICATION_MAX = 2000


@router.post("/{event_id}/clarification", response_model=EventOut)
def request_clarification(
    event_id: str,
    payload: ClarificationRequest,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
) -> EventOut:
    """US7.3: ask the Organiser for information or changes, and move to Under Review.

    US8.1's readable-event check restricts this action to the assigned
    Coordinator; the status rule here remains independent of assignment.

    The message lands in the event's history, which the owning Organiser already
    reads, so "visible to the Organiser" needs no separate delivery. Their reply
    is US11.1 and is deliberately not modelled here.
    """
    event = _readable(_as_id(event_id), user)

    message = payload.message.strip()
    if not message:
        raise _invalid("Say what you need from the Organiser.")
    if len(message) > CLARIFICATION_MAX:
        raise _invalid(f"Keep the request to {CLARIFICATION_MAX} characters or fewer.")

    refusal = check_clarification(status=event.status)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": clarification_refusal_message(refusal),
                "reason": str(refusal),
            },
        )

    _require_transition(event.status, EventStatus.UNDER_REVIEW)

    try:
        reviewed = event_store.repository().request_clarification(
            event.id, actor_id=user.id, from_status=event.status, message=message
        )
    except StaleEventStatus:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": (
                    "This event changed while you were reviewing it. "
                    "Refresh it and try again."
                ),
                "reason": "invalid-transition",
            },
        ) from None
    return _to_out(reviewed)


class RejectionRequest(BaseModel):
    """Why an Event Coordinator rejected an event (US7.1)."""

    reason: str = ""


DECISION_REASON_MAX = 2000


def _decide_event(
    event_id: str,
    user: User,
    to_status: EventStatus,
    *,
    reason: str = "",
) -> EventOut:
    event = _readable(_as_id(event_id), user)
    if event.status is not EventStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": "Only an event that is Under Review can be decided.",
                "reason": "invalid-transition",
            },
        )
    _require_transition(event.status, to_status)
    try:
        decided = event_store.repository().decide_event(
            event.id,
            actor_id=user.id,
            from_status=event.status,
            to_status=to_status,
            reason=reason,
        )
    except StaleEventStatus:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": "This event was already decided. Refresh it and try again.",
                "reason": "invalid-transition",
            },
        ) from None
    return _to_out(decided)


@router.post("/{event_id}/approve", response_model=EventOut)
def approve_event(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
) -> EventOut:
    """US7.1: move an assigned Under Review event to Approved."""
    return _decide_event(event_id, user, EventStatus.APPROVED)


@router.post("/{event_id}/reject", response_model=EventOut)
def reject_event(
    event_id: str,
    payload: RejectionRequest,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
) -> EventOut:
    """US7.1: reject an assigned Under Review event with an organiser-visible reason."""
    reason = payload.reason.strip()
    if not reason:
        raise _invalid("Give the Organiser a reason for rejecting this event.")
    if len(reason) > DECISION_REASON_MAX:
        raise _invalid(f"Keep the reason to {DECISION_REASON_MAX} characters or fewer.")
    return _decide_event(event_id, user, EventStatus.REJECTED, reason=reason)


# -- US14.1: venue bookings ----------------------------------------------------
#
# A Coordinator asks for one or more venues for an event, such as a main hall
# and its breakout rooms (Week 7 change #3). Each request is its own record and
# its own call, so a venue that is refused never holds up another: the main hall
# is stored before the breakout room is even sent. US15.1 (availability) and
# US18.1 (suitability) add their checks per booking, in `request_booking`.
#
# These routes live here rather than in a module of their own because a booking
# is reached through its event, and the event's visibility rule is what decides
# who may see or request one.


class BookingOut(BaseModel):
    id: str
    event_id: str = Field(serialization_alias="eventId")
    venue_id: str = Field(serialization_alias="venueId")
    venue_name: str = Field(serialization_alias="venueName")
    #: As sent, "YYYY-MM-DDTHH:MM", or with seconds once read back from Postgres.
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    status: BookingStatus
    requested_at: str = Field(serialization_alias="requestedAt")


def _booking_out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=str(booking.id),
        event_id=str(booking.event_id),
        venue_id=str(booking.venue_id),
        venue_name=booking.venue_name,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        status=booking.status,
        requested_at=booking.requested_at,
    )


class BookingInput(BaseModel):
    """What a Coordinator sends to request a venue for an event.

    Every field is optional here so that a missing or malformed one is a
    sentence from `_validated_booking` with this module's 400 rather than
    Pydantic's 422, which is the same reason `UnavailabilityInput` takes its
    dates as text. The venue id may come as a string, the way ids go out, or
    as a number.
    """

    model_config = ConfigDict(populate_by_name=True)

    venue_id: str | int | None = Field(default=None, alias="venueId")
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")


#: What a datetime-local input sends, with or without seconds, in ASCII digits.
#: `datetime.fromisoformat` alone is looser than this, and a time the form did
#: not mean to send should be refused rather than reinterpreted.
_ISO_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?")
_VENUE_ID = re.compile(r"[0-9]+")


def _invalid_booking(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": EventError.INVALID_BOOKING, "message": message},
    )


def _venue_missing() -> HTTPException:
    """400 rather than 404: the event in the path exists; the venue in the body does not."""
    return _invalid_booking("That venue is not in the catalogue.")


def _booking_time(raw: str | None, *, which: str) -> tuple[str, datetime]:
    """The time as it will be stored, and as a datetime to compare with."""
    text = (raw or "").strip()
    if not text:
        article = "an" if which == "end" else "a"
        raise _invalid_booking(f"Give the booking {article} {which} time.")
    if not _ISO_DATETIME.fullmatch(text):
        raise _invalid_booking(f"Give the {which} time as YYYY-MM-DDTHH:MM.")
    try:
        return text, datetime.fromisoformat(text)
    except ValueError:
        # Well-formed but not on any calendar or clock: 2027-02-30, 25:00.
        raise _invalid_booking(f"The {which} time {text} is not a real date and time.") from None


def _validated_booking(payload: BookingInput) -> tuple[int, str, str]:
    """US14.1: a venue, a start, and an end after it.

    One problem is named at a time, in the order the form shows the fields. The
    past is judged by date, as `_validate_submission` judges an event's start:
    the times are naive and local to whoever typed them, so the server's clock
    cannot say whether 09:00 today has passed for them.
    """
    raw_venue = "" if payload.venue_id is None else str(payload.venue_id).strip()
    if not raw_venue:
        raise _invalid_booking("Choose a venue.")
    if not _VENUE_ID.fullmatch(raw_venue):
        raise _venue_missing()

    starts_at, start = _booking_time(payload.starts_at, which="start")
    ends_at, end = _booking_time(payload.ends_at, which="end")
    if end <= start:
        raise _invalid_booking("The booking must end after it starts.")
    if start.date() < date.today():
        raise _invalid_booking("A booking cannot start in the past.")
    return int(raw_venue), starts_at, ends_at


@router.get("/{event_id}/bookings", response_model=list[BookingOut])
def list_bookings(
    event_id: str,
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> list[BookingOut]:
    """US14.1: every venue booking for the event, together, soonest first.

    Whoever may open the event may see its bookings (the owning Organiser and
    the assigned Coordinator) and nobody else, because this goes through the
    same `_readable` check as the event itself.
    """
    event = _readable(_as_id(event_id), user)
    bookings = booking_store.repository().list_for_event(event.id)
    return [_booking_out(booking) for booking in bookings]


@router.post(
    "/{event_id}/bookings",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
)
def request_booking(
    event_id: str,
    payload: BookingInput,
    user: Annotated[User, Depends(require_permission(Permission.BOOKINGS_REQUEST))],
) -> BookingOut:
    """US14.1: ask for one venue for the event. It starts as Requested.

    Only the assigned Coordinator gets this far (US8.6). The permission above
    admits the role, and `_readable` admits the assignment: it answers 404 to a
    Coordinator the event is not assigned to, as US8.1 does for the event itself.

    404, then 409, then 400. A request for an event the caller cannot see is
    wrong whatever it says, and one for a closed event is refused however
    well-formed it is.
    """
    event = _readable(_as_id(event_id), user)

    refusal = check_booking(status=event.status)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": booking_refusal_message(refusal),
                "reason": str(refusal),
            },
        )

    venue_id, starts_at, ends_at = _validated_booking(payload)
    venue = venue_store.repository().get_venue(venue_id)
    if venue is None:
        raise _venue_missing()

    created = booking_store.repository().create(
        event_id=event.id,
        venue_id=venue.id,
        starts_at=starts_at,
        ends_at=ends_at,
        requested_by_id=user.id,
    )
    return _booking_out(created)
