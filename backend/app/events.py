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
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app import (
    arrangement_review,
    availability,
    booking_store,
    change_requests,
    conflict_flags,
    equipment_store,
    event_cancellation,
    event_needs,
    event_store,
    safety_check,
    safety_decision_store,
    safety_decisions,
    safety_review,
    suitability,
    venue_store,
    venue_unavailability_store,
)
from app.auth import CurrentUser, ErrorCode, require_any_permission, require_permission
from app.availability import SlotCheck
from app.booking_store import (
    Booking,
    BookingStatus,
    HoldExpired,
    SlotTaken,
    StaleBookingStatus,
    local_now,
)
from app.event_needs import EventNeeds
from app.event_status import (
    EventStatus,
    booking_refusal_message,
    check_booking,
    check_clarification,
    check_completion,
    check_submit,
    clarification_refusal_message,
    completion_refusal_message,
    refusal_message,
    transition_allowed,
    transition_refusal_message,
)
from app.event_store import Event, StaleEventStatus
from app.notifications import (
    notify_assigned,
    notify_change_decision,
    notify_change_submitted,
    notify_clarification,
    notify_safety_changes,
    notify_safety_rejected,
    notify_status_change,
)
from app.permissions import Permission, Role, has_permission
from app.safety_decision_store import ReviewFlag, SafetyDecision, StaleFlag
from app.safety_decisions import SafetyOutcome
from app.suitability import BookingNeeds, Verdict
from app.users import User
from app.venue_store import Venue

router = APIRouter(prefix="/events", tags=["events"])

READ_ANY = (
    Permission.EVENTS_READ_OWN,
    Permission.EVENTS_READ_SUBMITTED,
    Permission.EVENTS_READ_ALL,
)
#: US4.4: opening one event. The Safety Officer reads only the events waiting
#: for their check (see `_readable`), so they are not on the list routes.
READ_ONE = (*READ_ANY, Permission.SAFETY_REVIEW)


class EventError:
    NOT_FOUND = "event_not_found"
    INVALID = "invalid_event"
    REFUSED = "rule_refused"
    INVALID_BOOKING = "invalid_booking"
    BOOKING_NOT_FOUND = "booking_not_found"
    SAFETY_FLAG_NOT_FOUND = "safety_flag_not_found"


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
    #: US11.1: "change-request" on the entry an Organiser's change request
    #: wrote, so the history can label its note. US4.4: "safety-return" on the
    #: entry the Safety Officer wrote sending an event back to Planning.
    #: US4.6: "cancellation" on the entry that cancelled the event.
    #: Worked out, not stored; empty on every other entry.
    kind: str = ""


class ProposedChangeOut(BaseModel):
    """One field of a pending US11.1 change request, as the Coordinator reviews it."""

    field: str
    label: str
    old_value: str = Field(serialization_alias="oldValue")
    new_value: str = Field(serialization_alias="newValue")
    #: US5.2's rule: date/time, attendance, venue and equipment are important.
    important: bool


class ChangeReviewOut(BaseModel):
    """US11.1: the Coordinator's answer to the most recent change request."""

    outcome: str
    at: str
    #: The rejection reason. Empty for an approval.
    note: str = ""
    request_note: str = Field(default="", serialization_alias="requestNote")


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
    #: US8.4: The assigned Event Coordinator's name, or empty if unassigned.
    coordinator_name: str = Field(default="", serialization_alias="coordinatorName")
    history: list[StatusChangeOut]
    #: US11.1: set while an Organiser's change request awaits review, which is
    #: what puts the event in the Coordinator's review queue.
    change_requested: bool = Field(default=False, serialization_alias="changeRequested")
    pending_changes: list[ProposedChangeOut] = Field(
        default_factory=list, serialization_alias="pendingChanges"
    )
    change_request_note: str = Field(default="", serialization_alias="changeRequestNote")
    review_revision: int = Field(default=0, serialization_alias="reviewRevision")
    clarification_id: int | None = Field(default=None, serialization_alias="clarificationId")
    awaiting_reply: bool = Field(default=False, serialization_alias="awaitingReply")
    review_history: list[dict] = Field(default_factory=list, serialization_alias="reviewHistory")
    arrangement_review_pending: bool = Field(
        default=False, serialization_alias="arrangementReviewPending"
    )
    arrangement_review: list[dict] = Field(
        default_factory=list, serialization_alias="arrangementReview"
    )
    last_change_review: ChangeReviewOut | None = Field(
        default=None, serialization_alias="lastChangeReview"
    )
    #: US2.1 (Sprint 3): what the event needs. Empty until answered.
    venue_requirements: str = Field(default="", serialization_alias="venueRequirements")
    preferred_layout: str = Field(default="", serialization_alias="preferredLayout")
    accessibility_needs: str = Field(default="", serialization_alias="accessibilityNeeds")
    equipment_needs: str = Field(default="", serialization_alias="equipmentNeeds")
    registration_needs: str = Field(default="", serialization_alias="registrationNeeds")


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
    #: US2.1 (Sprint 3): what the event needs, as `app.event_needs` describes.
    #: Optional on a draft; all five are required to submit.
    venue_requirements: str = Field(default="", alias="venueRequirements")
    preferred_layout: str = Field(default="", alias="preferredLayout")
    accessibility_needs: str = Field(default="", alias="accessibilityNeeds")
    equipment_needs: str = Field(default="", alias="equipmentNeeds")
    registration_needs: str = Field(default="", alias="registrationNeeds")

    def needs(self) -> EventNeeds:
        return EventNeeds(
            venue_requirements=self.venue_requirements,
            preferred_layout=self.preferred_layout,
            accessibility_needs=self.accessibility_needs,
            equipment_needs=self.equipment_needs,
            registration_needs=self.registration_needs,
        )


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
        coordinator_name=event.coordinator_name,
        history=[
            StatusChangeOut(
                from_status=change.from_status,
                to=change.to_status,
                at=change.at,
                by_id=str(change.by_id),
                by_name=change.by_name,
                notes=change.notes,
                kind=safety_check.history_kind(
                    from_status=change.from_status, to_status=change.to_status
                )
                or event_cancellation.history_kind(to_status=change.to_status)
                or change_requests.history_kind(
                    by_id=change.by_id,
                    organiser_id=event.organiser_id,
                    to_status=change.to_status,
                ),
            )
            for change in event.history
        ],
        review_revision=event.review_state.get("revision", 0),
        clarification_id=event.review_state.get("clarificationId"),
        awaiting_reply=event.review_state.get("awaitingReply", False),
        review_history=event.review_state.get("messages", []),
        arrangement_review_pending=event.arrangement_review_pending,
        arrangement_review=list(event.arrangement_review),
        change_requested=event.change_requested,
        change_request_note=event.change_request_note,
        pending_changes=[
            ProposedChangeOut(
                field=change.field,
                label=change_requests.label_for(change.field),
                old_value=change.old_value,
                new_value=change.new_value,
                important=change.important,
            )
            for change in event.pending_changes
        ],
        last_change_review=(
            ChangeReviewOut(
                outcome=event.last_change_review.outcome,
                at=event.last_change_review.at,
                note=event.last_change_review.note,
                request_note=event.last_change_review.request_note,
            )
            if event.last_change_review is not None
            else None
        ),
        **event.needs.as_attrs(),
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
            "message": transition_refusal_message(from_status=from_status, to_status=to_status),
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
#: `events.expected_attendance` is INTEGER, so a larger number would fail the
#: write. Refused here with a sentence instead (US2.1 boundary).
ATTENDANCE_MAX = 2_147_483_647
ATTENDANCE_TOO_LARGE = f"Expected attendance must be {ATTENDANCE_MAX:,} or fewer."
DRAFT_CONTENT_ERROR = "Enter at least one letter or number in any field to save a draft."


def _has_draft_content(draft: EventDraft) -> bool:
    values = (
        draft.title,
        draft.purpose,
        draft.description,
        draft.starts_at,
        draft.ends_at or "",
        "" if draft.expected_attendance is None else str(draft.expected_attendance),
        *draft.needs().as_attrs().values(),
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
    if draft.expected_attendance is not None and draft.expected_attendance > ATTENDANCE_MAX:
        raise _invalid(ATTENDANCE_TOO_LARGE)
    needs_problem = event_needs.format_error(draft.needs())
    if needs_problem:
        raise _invalid(needs_problem)

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
    if not event.description.strip():
        raise _invalid("Give the event a description.")
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
    # US2.1 (Sprint 3): the customer made the end time and every need
    # mandatory. Checked after the original rules so their messages stand.
    if not event.ends_at.strip():
        raise _invalid("Give the event an end date.")
    missing = event_needs.missing_error(event.needs)
    if missing:
        raise _invalid(missing)


def _readable(event_id: int, user: User) -> Event:
    """Fetch an event the caller is allowed to see, or 404.

    US8.1: Coordinators can only see events assigned to them.
    US8.6: Lead can see all events (not just assigned ones).
    US4.4: the Safety Officer sees an event while it waits for their check."""
    event = event_store.repository().get_event(event_id)
    if event is None:
        raise _not_found()
    if (
        has_permission(user.role, Permission.SAFETY_REVIEW)
        and event.status is EventStatus.PENDING_SAFETY_CHECK
    ):
        return event
    sees_own = has_permission(user.role, Permission.EVENTS_READ_OWN)
    owns_event = sees_own and event.organiser_id == user.id
    sees_submitted = has_permission(user.role, Permission.EVENTS_READ_SUBMITTED)
    sees_all = has_permission(user.role, Permission.EVENTS_READ_ALL)

    # US8.1: Coordinators can only see events assigned to them
    is_assigned_coordinator = sees_submitted and event.coordinator_id == user.id

    # US8.6: Lead can see all events
    if sees_all and event.status != EventStatus.DRAFT:
        return event

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

    US8.1: Coordinators now only see events assigned to them.
    US8.6: Lead sees all events (unassigned and assigned)."""
    sees_submitted = has_permission(user.role, Permission.EVENTS_READ_SUBMITTED)
    sees_all = has_permission(user.role, Permission.EVENTS_READ_ALL)

    all_events = event_store.repository().list_events(
        organiser_id=None if (sees_submitted or sees_all) else user.id,
        include_drafts=not (sees_submitted or sees_all),
    )

    # US8.1: Filter by coordinator assignment (but not for Lead who sees all)
    if sees_submitted and not sees_all:
        all_events = [e for e in all_events if e.coordinator_id == user.id]

    return [_to_out(event) for event in all_events]


@router.get("/unassigned", response_model=list[EventOut])
def list_unassigned(
    user: Annotated[User, Depends(require_permission(Permission.QUEUE_VIEW_UNASSIGNED))],
) -> list[EventOut]:
    """US8.2: List Submitted events with no assigned Coordinator (oldest first).

    Only Coordinator Lead can access this queue."""
    events = event_store.repository().list_unassigned()
    return [_to_out(event) for event in events]


class AssignmentPayload(BaseModel):
    """Payload for assigning a Coordinator to an event (US8.3)."""

    model_config = ConfigDict(populate_by_name=True)

    coordinator_id: str = Field(alias="coordinatorId")


@router.post("/{event_id}/assign", response_model=EventOut)
def assign_coordinator(
    event_id: str,
    payload: AssignmentPayload,
    user: Annotated[User, Depends(require_permission(Permission.COORDINATORS_ASSIGN))],
) -> EventOut:
    """US8.3: Lead assigns a Coordinator to an unassigned event.

    Once assigned, the Coordinator can review, approve/reject, and manage the event."""
    from app import users

    event = event_store.repository().get_event(_as_id(event_id))
    if event is None:
        raise _not_found()

    # Cannot reassign an already-assigned event
    if event.coordinator_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": "This event is already assigned to a Coordinator.",
                "reason": "already-assigned",
            },
        )

    if event.status is not EventStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": "Only a Submitted event can be assigned to a Coordinator.",
                "reason": "invalid-transition",
            },
        )
    _require_transition(event.status, EventStatus.UNDER_REVIEW)

    # Validate the coordinator ID
    try:
        coordinator_id = int(payload.coordinator_id)
    except ValueError:
        raise _invalid("The coordinator ID must be a valid number.") from None

    # Check that the coordinator exists and is a Coordinator
    all_users = users.list_users()
    coordinator = next((u for u in all_users if u.id == coordinator_id), None)
    if coordinator is None:
        raise _invalid("That coordinator does not exist.")
    if coordinator.role != Role.COORDINATOR:
        raise _invalid("That user is not a Coordinator.")

    # Assign the coordinator
    try:
        assigned = event_store.repository().assign_coordinator(
            event.id, coordinator_id, assigned_by_id=user.id
        )
    except StaleEventStatus:
        raise _stale_request() from None
    # US10.1: assignment is what moves an event to Under Review now (US8.3).
    notify_status_change(assigned, EventStatus.UNDER_REVIEW)
    # US10.2: and the Coordinator learns the event is theirs.
    notify_assigned(assigned)
    return _to_out(assigned)


@router.post("/{event_id}/reassign", response_model=EventOut)
def reassign_coordinator(
    event_id: str,
    payload: AssignmentPayload,
    user: Annotated[User, Depends(require_permission(Permission.COORDINATORS_ASSIGN))],
) -> EventOut:
    """US8.4: Lead reassigns an already-assigned event to a different Coordinator.

    The new Coordinator gains access and the previous Coordinator loses access.
    This allows workload redistribution and coverage when coordinators are unavailable."""
    from app import users

    event = event_store.repository().get_event(_as_id(event_id))
    if event is None:
        raise _not_found()

    # Must already be assigned (cannot reassign an unassigned event)
    if event.coordinator_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": "This event is not assigned to any coordinator. Use /assign instead.",
                "reason": "not-assigned",
            },
        )

    # Validate the coordinator ID
    try:
        coordinator_id = int(payload.coordinator_id)
    except ValueError:
        raise _invalid("The coordinator ID must be a valid number.") from None

    # Check that the coordinator exists and is a Coordinator
    all_users = users.list_users()
    coordinator = next((u for u in all_users if u.id == coordinator_id), None)
    if coordinator is None:
        raise _invalid("That coordinator does not exist.")
    if coordinator.role != Role.COORDINATOR:
        raise _invalid("That user is not a Coordinator.")

    # Reassign the coordinator (reuses the same assign_coordinator method)
    reassigned = event_store.repository().assign_coordinator(
        event.id, coordinator_id, assigned_by_id=user.id
    )
    return _to_out(reassigned)


@router.get("/safety-check", response_model=list[EventOut])
def list_pending_safety_check(
    _user: Annotated[User, Depends(require_permission(Permission.SAFETY_REVIEW))],
) -> list[EventOut]:
    """US4.4: the events waiting for the Safety Officer, longest-waiting first.

    The order is by when each event entered Pending Safety Check, so an event
    sent back and sent again joins the end of the queue rather than jumping it.
    US17.1 builds the full review queue on this.
    """
    events = [
        event
        for event in event_store.repository().list_events(organiser_id=None, include_drafts=False)
        if event.status is EventStatus.PENDING_SAFETY_CHECK
    ]
    return [
        _to_out(event)
        for event in sorted(
            events, key=lambda event: (safety_review.entered_safety_check(event), event.id)
        )
    ]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: str,
    user: Annotated[User, Depends(require_any_permission(*READ_ONE))],
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
        needs=clean.needs(),
    )
    return _to_out(created)


SUBMITTED_EDIT_MESSAGE = (
    "This event has been submitted, so it can no longer be edited directly. "
    "Request a change instead and the Coordinator will review it."
)


@router.put("/{event_id}", response_model=EventOut)
def save_event(event_id: str, draft: EventDraft, user: CurrentUser) -> EventOut:
    """US4.2 & US5.2: saving edits content and never moves the status.

    Owner (organiser) can save Draft events without logging changes.
    Coordinator can edit Submitted (or later) events with change tracking.
    """
    event = _readable(_as_id(event_id), user)
    _refuse_if_cancelled(event)
    if event.status in (EventStatus.COMPLETED, EventStatus.REJECTED):
        raise _stale_request()
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

    # US11.1: once submitted, the event is the Coordinator's to review. The
    # Organiser proposes changes instead, so they are reviewed, not applied.
    if is_owner and not is_coordinator and event.status is not EventStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": SUBMITTED_EDIT_MESSAGE,
                "reason": "change-request-required",
            },
        )

    if is_coordinator and event.change_requested:
        raise _stale_request()
    clean = _validated(draft)

    # If coordinator is editing (not the owner), use change tracking
    if is_coordinator and not is_owner:
        try:
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
                needs=clean.needs(),
            )
        except StaleEventStatus:
            raise _stale_request() from None
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
            needs=clean.needs(),
        )
    if saved.arrangement_review_pending:
        saved = arrangement_review.recheck(saved)
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
    reviewRevision: int | None = None


#: `status_changes.notes` is unbounded TEXT, so this cap is about keeping a
#: request readable rather than about fitting the column.
CLARIFICATION_MAX = 2000


@router.post("/{event_id}/clarification", response_model=EventOut)
def request_clarification(
    event_id: str,
    payload: ClarificationRequest,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
) -> EventOut:
    """US7.3/US11.2: request field amendments without changing event status.

    US8.1's readable-event check restricts this action to the assigned
    Coordinator; the status rule here remains independent of assignment.

    Questions are retained in review history and notify the Organiser. Each new
    question opens one amendment response, including replacement of a pending proposal.
    """
    event = _readable(_as_id(event_id), user)

    message = payload.message.strip()
    if not message:
        raise _invalid("Say what you need from the Organiser.")
    if len(message) > CLARIFICATION_MAX:
        raise _invalid(f"Keep the request to {CLARIFICATION_MAX} characters or fewer.")

    refusal = check_clarification(status=event.status)
    if event.change_requested and event.status in change_requests.REQUESTABLE:
        refusal = None
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": clarification_refusal_message(refusal),
                "reason": str(refusal),
            },
        )

    try:
        reviewed = event_store.repository().request_clarification(
            event.id,
            actor_id=user.id,
            from_status=event.status,
            message=message,
            expected_revision=payload.reviewRevision,
        )
    except StaleEventStatus:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": (
                    "This event changed while you were reviewing it. Refresh it and try again."
                ),
                "reason": "invalid-transition",
            },
        ) from None
    # US10.1: a follow-up question on an event already Under Review notifies
    # too — it carries a new request the Organiser has to answer.
    notify_clarification(reviewed, message)
    return _to_out(reviewed)


class RejectionRequest(BaseModel):
    """Why an Event Coordinator rejected an event (US7.1)."""

    reason: str = ""
    reviewRevision: int | None = None


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
    if event.change_requested:
        # US11.1: the Coordinator reviews the proposed changes before deciding,
        # so a decision cannot overtake a request it has not answered.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": (
                    "Approve or reject the Organiser's change request before deciding this event."
                ),
                "reason": "change-pending",
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
    notify_status_change(decided, to_status, reason)
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


@router.post("/{event_id}/complete", response_model=EventOut)
def complete_event(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_COMPLETE))],
) -> EventOut:
    """The assigned Coordinator closes a Confirmed event after its end time."""
    event = _readable(_as_id(event_id), user)
    _require_transition(event.status, EventStatus.COMPLETED)
    refusal = check_completion(event.ends_at)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": completion_refusal_message(refusal),
                "reason": str(refusal),
            },
        )
    try:
        completed = event_store.repository().complete_event(event.id, actor_id=user.id)
    except StaleEventStatus:
        raise _stale_request() from None
    return _to_out(completed)


# -- US4.6: cancelling an event ------------------------------------------------


class EventCancellationIn(BaseModel):
    """Why the event is being cancelled. Required."""

    reason: str = ""


def _refuse_if_cancelled(event: Event) -> None:
    """US4.6: a cancelled event is read-only."""
    if event.status is EventStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": event_cancellation.READ_ONLY_MESSAGE,
                "reason": "event-cancelled",
            },
        )


@router.post("/{event_id}/cancel", response_model=EventOut)
def cancel_event(
    event_id: str,
    payload: EventCancellationIn,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_CANCEL))],
) -> EventOut:
    """US4.6: cancel the event, with a reason, and release everything it held.

    The owning Organiser or the assigned Coordinator: the permission admits
    the role, and `_readable` admits only the events they own or are assigned
    to, answering 404 for any other. Then 409 for an event already Completed,
    Cancelled or Rejected, then 400 for the reason, as for cancelling a booking.

    The store makes the move, its history entry, the cancelled bookings and the
    removed equipment lines one write (`app.event_cancellation` says what each
    covers). What follows it - conflict flags and notices - is best effort.
    """
    event = _readable(_as_id(event_id), user)
    refusal = event_cancellation.check_cancel(status=event.status)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": event_cancellation.cancel_refusal_message(refusal),
                "reason": str(refusal),
            },
        )
    reason = payload.reason.strip()
    if not reason:
        raise _invalid("Give a reason for cancelling this event.")
    if len(reason) > event_cancellation.CANCELLATION_REASON_MAX:
        raise _invalid(
            f"Keep the reason to {event_cancellation.CANCELLATION_REASON_MAX} characters or fewer."
        )
    _require_transition(event.status, EventStatus.CANCELLED)
    try:
        cancelled = event_store.repository().cancel_event(
            event.id, actor_id=user.id, from_status=event.status, reason=reason
        )
    except StaleEventStatus:
        raise _stale_request() from None
    event_cancellation.settle_quietly(cancelled, actor=user, reason=reason)
    return _to_out(cancelled.event)


# -- US4.4: Pending Safety Check -----------------------------------------------
#
# Planning -> Pending Safety Check is the assigned Coordinator's to ask for, and
# only once the event is ready (`app.safety_check`). The Safety Officer then
# signs it off (-> Confirmed) or sends it back to Planning with a note. That is
# the only way into Confirmed; US17.2 (below) separates the request-changes and
# reject outcomes and adds the re-review flags.


class SafetyReadinessOut(BaseModel):
    """Whether the assigned Coordinator can send the event for its check now."""

    ready: bool
    #: A `SafetyCheckRefusal` value, or empty when ready.
    reason: str = ""
    message: str = ""


def _safety_refusal(event: Event) -> safety_check.SafetyCheckRefusal | None:
    return safety_check.check_ready_for_safety_check(
        status=event.status,
        change_requested=event.change_requested,
        arrangement_review_pending=event.arrangement_review_pending,
        bookings=booking_store.repository().list_for_event(event.id),
        equipment=equipment_store.repository().list_for_event(event.id),
        # US17.2: a flag the Coordinator has not marked re-reviewed holds it back.
        flags_open=any(
            flag.is_open
            for decision in safety_decision_store.repository().list_for_event(event.id)
            for flag in decision.flags
        ),
    )


SafetySender = Annotated[User, Depends(require_permission(Permission.SAFETY_SUBMIT))]
SafetyOfficer = Annotated[User, Depends(require_permission(Permission.SAFETY_REVIEW))]


@router.get("/{event_id}/safety-check", response_model=SafetyReadinessOut)
def safety_check_readiness(event_id: str, user: SafetySender) -> SafetyReadinessOut:
    """US4.4: say whether the event is ready, and if not, what is outstanding."""
    event = _readable(_as_id(event_id), user)
    refusal = _safety_refusal(event)
    if refusal is None:
        return SafetyReadinessOut(ready=True)
    return SafetyReadinessOut(
        ready=False,
        reason=str(refusal),
        message=safety_check.safety_check_refusal_message(refusal),
    )


@router.post("/{event_id}/safety-check", response_model=EventOut)
def send_for_safety_check(event_id: str, user: SafetySender) -> EventOut:
    """US4.4: Planning -> Pending Safety Check, timestamped and attributable."""
    event = _readable(_as_id(event_id), user)
    _require_transition(event.status, EventStatus.PENDING_SAFETY_CHECK)
    refusal = _safety_refusal(event)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": safety_check.safety_check_refusal_message(refusal),
                "reason": str(refusal),
            },
        )
    try:
        sent = event_store.repository().send_to_safety_check(event.id, actor_id=user.id)
    except StaleEventStatus:
        raise _stale_request() from None
    return _to_out(sent)


# -- US17.1: what the Safety Officer reviews ------------------------------------


class ClosureOut(BaseModel):
    """A venue unavailability period that has not ended yet (US12.1)."""

    start_date: str = Field(serialization_alias="startDate")
    end_date: str = Field(serialization_alias="endDate")
    reason: str


class ReviewedVenueOut(BaseModel):
    """One booked venue: what the booking asks beside what the venue offers."""

    booking_id: str = Field(serialization_alias="bookingId")
    venue_id: str = Field(serialization_alias="venueId")
    venue_name: str = Field(serialization_alias="venueName")
    location: str
    status: str
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    capacity: int | None
    headcount: int | None
    over_capacity: bool = Field(serialization_alias="overCapacity")
    required_layout: str = Field(serialization_alias="requiredLayout")
    supported_layouts: str = Field(serialization_alias="supportedLayouts")
    facilities: str
    accessibility_features: str = Field(serialization_alias="accessibilityFeatures")
    accessibility_needs: list[str] = Field(serialization_alias="accessibilityNeeds")
    operating_hours: str = Field(serialization_alias="operatingHours")
    setup_minutes: int = Field(serialization_alias="setupMinutes")
    turnaround_minutes: int = Field(serialization_alias="turnaroundMinutes")
    closures: list[ClosureOut]


class ReviewedEquipmentOut(BaseModel):
    id: str
    equipment_type: str = Field(serialization_alias="type")
    quantity: int
    technical_requirements: str = Field(serialization_alias="technicalRequirements")
    support_notes: str = Field(serialization_alias="supportNotes")
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")


class SafetyReviewOut(BaseModel):
    """US17.1: everything the Safety Officer needs to assess one event."""

    event_id: str = Field(serialization_alias="eventId")
    title: str
    status: EventStatus
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    expected_attendance: int | None = Field(serialization_alias="expectedAttendance")
    #: The event's own accessibility requirements, as the Organiser gave them.
    accessibility_needs: str = Field(serialization_alias="accessibilityNeeds")
    preferred_layout: str = Field(serialization_alias="preferredLayout")
    venue_requirements: str = Field(serialization_alias="venueRequirements")
    waiting_since: str = Field(serialization_alias="waitingSince")
    venues: list[ReviewedVenueOut]
    equipment: list[ReviewedEquipmentOut]


def _review_out(review: safety_review.SafetyReview) -> SafetyReviewOut:
    event = review.event
    return SafetyReviewOut(
        event_id=str(event.id),
        title=event.title,
        status=event.status,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        expected_attendance=event.expected_attendance,
        accessibility_needs=event.accessibility_needs,
        preferred_layout=event.preferred_layout,
        venue_requirements=event.venue_requirements,
        waiting_since=review.waiting_since,
        venues=[
            ReviewedVenueOut(
                booking_id=str(venue.booking_id),
                venue_id=str(venue.venue_id),
                venue_name=venue.venue_name,
                location=venue.location,
                status=venue.status,
                starts_at=venue.starts_at,
                ends_at=venue.ends_at,
                capacity=venue.capacity,
                headcount=venue.headcount,
                over_capacity=venue.over_capacity,
                required_layout=venue.required_layout,
                supported_layouts=venue.supported_layouts,
                facilities=venue.facilities,
                accessibility_features=venue.accessibility_features,
                accessibility_needs=list(venue.accessibility_needs),
                operating_hours=venue.operating_hours,
                setup_minutes=venue.setup_minutes,
                turnaround_minutes=venue.turnaround_minutes,
                closures=[
                    ClosureOut(
                        start_date=closure.start_date.isoformat(),
                        end_date=closure.end_date.isoformat(),
                        reason=closure.reason,
                    )
                    for closure in venue.closures
                ],
            )
            for venue in review.venues
        ],
        equipment=[
            ReviewedEquipmentOut(
                id=str(line.id),
                equipment_type=line.equipment_type,
                quantity=line.quantity,
                technical_requirements=line.technical_requirements,
                support_notes=line.support_notes,
                starts_at=line.starts_at,
                ends_at=line.ends_at,
            )
            for line in review.equipment
        ],
    )


@router.get("/{event_id}/safety-review", response_model=SafetyReviewOut)
def get_safety_review(event_id: str, user: SafetyOfficer) -> SafetyReviewOut:
    """US17.1: the detail view behind the queue. Read-only, Safety Officer only.

    `_readable` lets the Safety Officer reach an event only while it is
    Pending Safety Check; anything else is 404, as it is for any event that is
    not the caller's to see.
    """
    event = _readable(_as_id(event_id), user)
    review = safety_review.build_review(
        event,
        bookings=booking_store.repository().list_for_event(event.id),
        venue_for=venue_store.repository().get_venue,
        closures_for=venue_unavailability_store.repository().list_for_venue,
        equipment=equipment_store.repository().list_reserved_for_event(event.id),
        today=local_now().date(),
    )
    return _review_out(review)


# -- US17.2: the Safety Officer records a decision -----------------------------
#
# Approve, request changes, or reject (`app.safety_decisions`). Each decision is
# a `safety_reviews` row written in the same transaction as the event's move and
# its US4.2 audit entry. A request for changes can flag the venue bookings and
# equipment lines it is about; the assigned Coordinator marks each re-reviewed
# before the event can be sent for its check again.


class SafetyDecisionIn(BaseModel):
    """What the Safety Officer decides with. All of it is optional on approval."""

    model_config = ConfigDict(populate_by_name=True)

    #: What must change, or the reason for rejecting. Required for both.
    note: str = ""
    #: `waitingSince` from the review the decision was made on (US17.1), so a
    #: decision is never applied to a later submission. Empty skips the
    #: comparison, which only a client older than US17.2 does.
    check_started_at: str = Field(default="", alias="checkStartedAt")
    flagged_booking_ids: list[int] = Field(default_factory=list, alias="flaggedBookingIds")
    flagged_equipment_ids: list[int] = Field(default_factory=list, alias="flaggedEquipmentIds")


class SafetyFlagOut(BaseModel):
    """One arrangement flagged for re-review, described well enough to find it."""

    id: str
    #: "booking" or "equipment".
    target: str
    target_id: str = Field(serialization_alias="targetId")
    #: The venue's name, or the equipment type and quantity.
    label: str
    #: The arrangement's status now — it may have been cancelled since.
    status: str
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    #: Empty while open.
    resolved_at: str = Field(serialization_alias="resolvedAt")
    resolved_by_name: str = Field(serialization_alias="resolvedByName")


class SafetyDecisionOut(BaseModel):
    """US17.2: one decision, attributable and timestamped."""

    id: str
    outcome: SafetyOutcome
    note: str
    decided_by_name: str = Field(serialization_alias="decidedByName")
    decided_at: str = Field(serialization_alias="decidedAt")
    check_started_at: str = Field(serialization_alias="checkStartedAt")
    flags: list[SafetyFlagOut]


def _flag_out(flag: ReviewFlag, bookings: dict[int, Booking]) -> SafetyFlagOut:
    """Describe a flag by what it points at. Either may have moved on since."""
    resolved = {"resolved_at": flag.resolved_at, "resolved_by_name": flag.resolved_by_name}
    if flag.booking_id is not None:
        booking = bookings.get(flag.booking_id)
        return SafetyFlagOut(
            id=str(flag.id),
            target="booking",
            target_id=str(flag.booking_id),
            label=booking.venue_name if booking else "A venue booking that no longer exists",
            status=str(booking.status) if booking else "",
            starts_at=booking.starts_at if booking else "",
            ends_at=booking.ends_at if booking else "",
            **resolved,
        )
    line = equipment_store.repository().get_request(flag.equipment_request_id or 0)
    return SafetyFlagOut(
        id=str(flag.id),
        target="equipment",
        target_id=str(flag.equipment_request_id),
        label=(
            f"{line.equipment_type} × {line.quantity}"
            if line
            else "An equipment request that no longer exists"
        ),
        status=line.status if line else "",
        starts_at=line.starts_at if line else "",
        ends_at=line.ends_at if line else "",
        **resolved,
    )


def _bookings_by_id(event_id: int) -> dict[int, Booking]:
    return {booking.id: booking for booking in booking_store.repository().list_for_event(event_id)}


def _decision_out(decision: SafetyDecision, bookings: dict[int, Booking]) -> SafetyDecisionOut:
    return SafetyDecisionOut(
        id=str(decision.id),
        outcome=decision.outcome,
        note=decision.note,
        decided_by_name=decision.decided_by_name,
        decided_at=decision.decided_at,
        check_started_at=decision.check_started_at,
        flags=[_flag_out(flag, bookings) for flag in decision.flags],
    )


def _safety_refused(message: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": EventError.REFUSED, "message": message, "reason": reason},
    )


def _record_safety_decision(
    event_id: str, user: User, outcome: SafetyOutcome, payload: SafetyDecisionIn
) -> tuple[Event, SafetyDecision]:
    """Check and record one decision, and return the event as it now is.

    `_readable` only lets the Safety Officer reach an event that is Pending
    Safety Check. The decision is pinned to the stay the server sees now, and
    to the one the Safety Officer reviewed when their page says which; the
    store re-checks the stay in the same write, so a check decided twice, or
    sent back and resubmitted meanwhile, is refused rather than overwritten.
    """
    event = _readable(_as_id(event_id), user)
    _require_transition(event.status, safety_decisions.to_status(outcome))
    note = payload.note.strip()
    error = safety_decisions.note_error(outcome, note)
    if error:
        raise _invalid(error)
    entered = safety_review.entered_safety_check(event)
    started = payload.check_started_at.strip()
    if started:
        try:
            current = safety_decisions.same_check(started, entered)
        except ValueError:
            raise _invalid("checkStartedAt must be a date and time.") from None
        if not current:
            raise _safety_refused(safety_decisions.CHECK_MOVED_ON, "check-moved-on")
    error = safety_decisions.flag_error(
        outcome,
        booking_ids=payload.flagged_booking_ids,
        equipment_ids=payload.flagged_equipment_ids,
        flaggable_bookings=[
            booking.id
            for booking in booking_store.repository().list_for_event(event.id)
            if booking.holds_venue
        ],
        flaggable_equipment=[
            line.id for line in equipment_store.repository().list_reserved_for_event(event.id)
        ],
    )
    if error:
        raise _invalid(error)
    try:
        decision = safety_decision_store.repository().record(
            event.id,
            officer_id=user.id,
            outcome=outcome,
            note=note,
            check_started_at=entered,
            booking_ids=tuple(payload.flagged_booking_ids),
            equipment_ids=tuple(payload.flagged_equipment_ids),
        )
    except StaleEventStatus:
        raise _safety_refused(
            "This safety check was already decided. Refresh it and try again.",
            "invalid-transition",
        ) from None
    decided = event_store.repository().get_event(event.id)
    assert decided is not None  # noqa: S101 - the row was just updated
    return decided, decision


@router.post("/{event_id}/safety-check/approve", response_model=EventOut)
def approve_safety_check(
    event_id: str, user: SafetyOfficer, payload: SafetyDecisionIn | None = None
) -> EventOut:
    """US4.4/US17.2: the Safety Officer signs the event off. -> Confirmed."""
    decided, _ = _record_safety_decision(
        event_id, user, SafetyOutcome.APPROVED, payload or SafetyDecisionIn()
    )
    return _to_out(decided)


# `/return` is US4.4's name for the same move, kept so an older client works.
@router.post("/{event_id}/safety-check/return", response_model=EventOut)
@router.post("/{event_id}/safety-check/request-changes", response_model=EventOut)
def request_safety_changes(
    event_id: str, payload: SafetyDecisionIn, user: SafetyOfficer
) -> EventOut:
    """US17.2: back to Planning with what must change, and the affected
    arrangements flagged for re-review. The Coordinator is told (US10.2)."""
    decided, decision = _record_safety_decision(
        event_id, user, SafetyOutcome.CHANGES_REQUESTED, payload
    )
    # Best effort, like every notice; the decision has already been recorded.
    notify_safety_changes(decided, decision.note, flagged=len(decision.flags))
    return _to_out(decided)


@router.post("/{event_id}/safety-check/reject", response_model=EventOut)
def reject_safety_check(event_id: str, payload: SafetyDecisionIn, user: SafetyOfficer) -> EventOut:
    """US17.2: rejected, with the reason. Back to Planning, per the story's assumption."""
    decided, decision = _record_safety_decision(event_id, user, SafetyOutcome.REJECTED, payload)
    notify_safety_rejected(decided, decision.note)
    return _to_out(decided)


SafetyReader = Annotated[
    User, Depends(require_any_permission(Permission.SAFETY_SUBMIT, Permission.SAFETY_REVIEW))
]


@router.get("/{event_id}/safety-decisions", response_model=list[SafetyDecisionOut])
def list_safety_decisions(event_id: str, user: SafetyReader) -> list[SafetyDecisionOut]:
    """US17.2: every safety decision on the event, newest first, with its flags.

    The assigned Coordinator reads it to see what to re-review; the Safety
    Officer, while the event waits for them, to see what they asked last time.
    `_readable` decides who reaches which event, as everywhere else.
    """
    event = _readable(_as_id(event_id), user)
    bookings = _bookings_by_id(event.id)
    return [
        _decision_out(decision, bookings)
        for decision in safety_decision_store.repository().list_for_event(event.id)
    ]


@router.post("/{event_id}/safety-flags/{flag_id}/resolve", response_model=SafetyFlagOut)
def resolve_safety_flag(event_id: str, flag_id: str, user: SafetySender) -> SafetyFlagOut:
    """US17.2: the assigned Coordinator marks one flagged arrangement re-reviewed.

    Only while the event is back in Planning, which is when there is anything
    to re-review. Once only, so the record keeps who did it first.
    """
    event = _readable(_as_id(event_id), user)
    if event.status is not EventStatus.PLANNING:
        raise _safety_refused(
            "Flagged arrangements are re-reviewed while the event is in Planning.",
            "not-planning",
        )
    store = safety_decision_store.repository()
    flag = store.get_flag(int(flag_id)) if flag_id.isdigit() else None
    if flag is None or flag.event_id != event.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": EventError.SAFETY_FLAG_NOT_FOUND,
                "message": "That flag is not on this event.",
            },
        )
    try:
        resolved = store.resolve_flag(flag.id, event_id=event.id, actor_id=user.id)
    except StaleFlag:
        raise _safety_refused(
            "This arrangement was already marked re-reviewed.", "flag-resolved"
        ) from None
    return _flag_out(resolved, _bookings_by_id(event.id))


class ChangeRequestIn(EventDraft):
    """US11.1: the edit form's values, proposed rather than saved, plus a note.

    It is the same shape as `EventDraft` because it is the same form. The note
    is optional — the changes usually speak for themselves — but it is where an
    Organiser answers a US7.3 question in words.
    """

    note: str = ""
    reviewRevision: int | None = None


#: Same reasoning as `CLARIFICATION_MAX`: a cap for readability, not the column.
CHANGE_NOTE_MAX = 2000


def _stale_request() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": "This event changed while you were working on it. Refresh it and try again.",
            "reason": "invalid-transition",
        },
    )


@router.post("/{event_id}/change-request", response_model=EventOut)
def request_change(
    event_id: str,
    payload: ChangeRequestIn,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_SUBMIT))],
) -> EventOut:
    """US11.1: propose changes for the Coordinator to review.

    Neither the event values nor its status move. Only the pending flag is set.
    Under Review allows amendments only after a Coordinator clarification.
    One pending `event_change_requests` row is written per field
    that differs, each marked important or routine by US5.2's rule. Nothing is
    written to `event_changes` until a Coordinator approves.

    The proposal is validated as a submission, not as a draft: a submitted event
    has to stay complete, so a change cannot be asked for that would leave it
    with no date or no attendance.
    """
    event = _readable(_as_id(event_id), user)

    refusal = change_requests.check_change_request(
        status=event.status,
        organiser_id=event.organiser_id,
        actor_id=user.id,
        change_requested=event.change_requested,
        awaiting_reply=event.review_state.get("awaitingReply", False),
    )
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": change_requests.change_request_refusal_message(refusal),
                "reason": str(refusal),
            },
        )

    note = payload.note.strip()
    if len(note) > CHANGE_NOTE_MAX:
        raise _invalid(f"Keep the note to {CHANGE_NOTE_MAX} characters or fewer.")

    clean = _validated(payload)
    proposed = replace(
        event,
        title=clean.title,
        purpose=clean.purpose,
        description=clean.description,
        starts_at=clean.starts_at,
        ends_at=clean.ends_at or "",
        expected_attendance=clean.expected_attendance,
        **clean.needs().as_attrs(),
    )
    _validate_submission(proposed)

    changes = change_requests.diff(event, proposed)
    if event.change_requested and changes == event.pending_changes:
        raise _invalid("Revise at least one proposed detail to answer the clarification.")
    if not changes:
        raise _invalid("Change at least one detail before requesting a change.")

    try:
        requested = event_store.repository().submit_change_request(
            event.id,
            actor_id=user.id,
            from_status=event.status,
            changes=changes,
            note=note,
            expected_revision=payload.reviewRevision,
        )
    except StaleEventStatus:
        raise _stale_request() from None
    notify_change_submitted(requested)
    return _to_out(requested)


def _resolve_change(
    event_id: str, user: User, *, approve: bool, note: str, revision: int | None = None
) -> EventOut:
    event = _readable(_as_id(event_id), user)
    if not change_requests.has_pending_request(
        status=event.status, change_requested=event.change_requested
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": change_requests.NOTHING_PENDING_MESSAGE,
                "reason": "nothing-pending",
            },
        )
    try:
        resolved = event_store.repository().resolve_change_request(
            event.id, actor_id=user.id, approve=approve, note=note, expected_revision=revision
        )
    except StaleEventStatus:
        raise _stale_request() from None
    if resolved.arrangement_review_pending:
        resolved = arrangement_review.recheck(resolved)
    notify_change_decision(resolved, approved=approve, reason=note)
    return _to_out(resolved)


@router.post("/{event_id}/change-request/approve", response_model=EventOut)
def approve_change(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
    review_revision: int | None = None,
) -> EventOut:
    """Apply the proposed changes while preserving the event's lifecycle status."""
    return _resolve_change(event_id, user, approve=True, note="", revision=review_revision)


@router.post("/{event_id}/change-request/reject", response_model=EventOut)
def reject_change(
    event_id: str,
    payload: RejectionRequest,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))],
) -> EventOut:
    """US11.1: decline the proposed changes, with a reason the Organiser can read."""
    reason = payload.reason.strip()
    if not reason:
        raise _invalid("Tell the Organiser why their requested changes were rejected.")
    if len(reason) > DECISION_REASON_MAX:
        raise _invalid(f"Keep the reason to {DECISION_REASON_MAX} characters or fewer.")
    return _resolve_change(
        event_id, user, approve=False, note=reason, revision=payload.reviewRevision
    )


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


class CancellationOut(BaseModel):
    """Who cancelled a booking, when, and why (US14.2)."""

    at: str
    #: Null once the user who cancelled has been removed; the record stays.
    by_id: str | None = Field(serialization_alias="byId")
    by_name: str = Field(serialization_alias="byName")
    reason: str


class BookingOut(BaseModel):
    replacement_reason: str = Field(default="", serialization_alias="replacementReason")
    flagged_by_unavailability_id: int | None = Field(
        default=None, serialization_alias="flaggedByUnavailabilityId"
    )
    id: str
    event_id: str = Field(serialization_alias="eventId")
    venue_id: str = Field(serialization_alias="venueId")
    venue_name: str = Field(serialization_alias="venueName")
    #: As sent, "YYYY-MM-DDTHH:MM", or with seconds once read back from Postgres.
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    status: BookingStatus
    requested_at: str = Field(serialization_alias="requestedAt")
    #: US18.1: how many people this booking is for. Null only on a booking made
    #: before US18.1 for an event that had no attendance to copy.
    headcount: int | None = None
    required_layout: str = Field(default="", serialization_alias="requiredLayout")
    required_facilities: list[str] = Field(
        default_factory=list, serialization_alias="requiredFacilities"
    )
    accessibility_needs: list[str] = Field(
        default_factory=list, serialization_alias="accessibilityNeeds"
    )
    #: Null unless the booking is Cancelled, so "not cancelled" is one state
    #: rather than three empty fields.
    cancellation: CancellationOut | None = None
    #: US14.3: when a hold lapses. Empty for a booking that was never a hold.
    hold_expires_at: str = Field(default="", serialization_alias="holdExpiresAt")
    #: US14.3: Held and past its expiry, so it no longer keeps the slot.
    hold_expired: bool = Field(default=False, serialization_alias="holdExpired")
    held_by_name: str = Field(default="", serialization_alias="heldByName")
    #: US16.1: who approved or rejected it, when, and for a rejection why.
    decision: "DecisionOut | None" = None
    #: US15.2: set while the booking is flagged "Conflict – review needed".
    conflict: "ConflictFlagOut | None" = None


class ConflictFlagOut(BaseModel):
    """US15.2: why a booking clashes since its venue's setup or turnaround changed."""

    #: Always "Conflict – review needed": the label the acceptance criteria name.
    label: str = conflict_flags.LABEL
    flagged_at: str = Field(serialization_alias="flaggedAt")
    reason: str


class DecisionOut(BaseModel):
    """Venue Staff's decision on a booking request (US16.1)."""

    at: str
    #: Null once the user who decided has been removed; the record stays.
    by_id: str | None = Field(serialization_alias="byId")
    by_name: str = Field(serialization_alias="byName")
    #: Empty for an approval.
    reason: str = ""
    #: An alternative venue or time Venue Staff suggest. Empty when none.
    suggestion: str = ""


BookingOut.model_rebuild()


def _booking_out(booking: Booking) -> BookingOut:
    cancellation = booking.cancellation
    return BookingOut(
        replacement_reason=booking.replacement_reason,
        flagged_by_unavailability_id=booking.flagged_by_unavailability_id,
        id=str(booking.id),
        event_id=str(booking.event_id),
        venue_id=str(booking.venue_id),
        venue_name=booking.venue_name,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        status=booking.status,
        requested_at=booking.requested_at,
        headcount=booking.headcount,
        required_layout=booking.required_layout,
        required_facilities=list(booking.required_facilities),
        accessibility_needs=list(booking.accessibility_needs),
        cancellation=(
            CancellationOut(
                at=cancellation.at,
                by_id=str(cancellation.by_id) if cancellation.by_id is not None else None,
                by_name=cancellation.by_name,
                reason=cancellation.reason,
            )
            if cancellation
            else None
        ),
        hold_expires_at=booking.hold_expires_at,
        hold_expired=booking.hold_expired,
        held_by_name=booking.held_by_name,
        decision=(
            DecisionOut(
                at=booking.decision.at,
                by_id=str(booking.decision.by_id) if booking.decision.by_id is not None else None,
                by_name=booking.decision.by_name,
                reason=booking.decision.reason,
                suggestion=booking.decision.suggestion,
            )
            if booking.decision
            else None
        ),
        conflict=(
            ConflictFlagOut(
                flagged_at=booking.event_conflict_at
                or (booking.conflict.flagged_at if booking.conflict else ""),
                reason="; ".join(
                    filter(
                        None,
                        [
                            booking.event_conflict_reason,
                            booking.conflict.reason if booking.conflict else "",
                        ],
                    )
                ),
            )
            if booking.conflict or booking.event_conflict_reason
            else None
        ),
    )


class BookingInput(BaseModel):
    """What a Coordinator sends to request a venue for an event, or to check one.

    Every field is optional here so that a missing or malformed one is a
    sentence from `_validated_booking` with this module's 400 rather than
    Pydantic's 422, which is the same reason `UnavailabilityInput` takes its
    dates as text. The venue id may come as a string, the way ids go out, or
    as a number.

    US18.1 added what the booking needs. The headcount defaults to the event's
    expected attendance when it is left out. The layout, facilities and
    accessibility needs are optional; each list may be sent as an array or as
    one comma-separated string.
    """

    model_config = ConfigDict(populate_by_name=True)

    venue_id: str | int | None = Field(default=None, alias="venueId")
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")
    headcount: int | str | None = None
    layout: str | None = None
    facilities: list[str] | str | None = None
    accessibility_needs: list[str] | str | None = Field(default=None, alias="accessibilityNeeds")


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


#: Postgres `integer`, as for a venue's capacity (US9.1a).
HEADCOUNT_MAX = 2_147_483_647
#: Per layout, facility or accessibility need. About keeping a need a need.
NEED_MAX = 100
#: Per list. A booking needing more than this is a venue description, not a need.
NEEDS_MAX = 20
_WHOLE_NUMBER = re.compile(r"[0-9]+")


def _headcount(raw: int | str | None, event: Event) -> int:
    """US18.1: the booking's own headcount, or the event's attendance by default."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        attendance = event.expected_attendance
        if attendance is None or attendance < 1:
            raise _invalid_booking(
                "Give the headcount for this booking. The event has no expected "
                "attendance to start from."
            )
        return attendance
    text = str(raw).strip()
    if isinstance(raw, bool) or not _WHOLE_NUMBER.fullmatch(text):
        raise _invalid_booking("Give the headcount as a whole number of people.")
    headcount = int(text)
    if headcount < 1:
        raise _invalid_booking("The headcount must be at least 1.")
    if headcount > HEADCOUNT_MAX:
        raise _invalid_booking("That headcount is larger than any venue this system can hold.")
    return headcount


def _need(text: str, *, what: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) > NEED_MAX:
        raise _invalid_booking(f"Keep each {what} to {NEED_MAX} characters or fewer.")
    return cleaned


def _needs(raw: list[str] | str | None, *, what: str, plural: str) -> tuple[str, ...]:
    """A list of needs, trimmed, blanks dropped, and each named once."""
    if raw is None:
        return ()
    items = raw.split(",") if isinstance(raw, str) else raw
    kept: list[str] = []
    seen: set[str] = set()
    for item in items:
        need = _need(str(item), what=what)
        if need and need.casefold() not in seen:
            seen.add(need.casefold())
            kept.append(need)
    if len(kept) > NEEDS_MAX:
        raise _invalid_booking(f"List at most {NEEDS_MAX} {plural}.")
    return tuple(kept)


@dataclass(frozen=True)
class _ValidBooking:
    venue_id: int
    #: As they will be stored, which is as they were sent.
    starts_at: str
    ends_at: str
    needs: BookingNeeds


def _validated_booking(payload: BookingInput, event: Event) -> _ValidBooking:
    """US14.1: a venue, a start, and an end after it. US18.1: what it needs.

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

    needs = BookingNeeds(
        headcount=_headcount(payload.headcount, event),
        starts_at=start,
        ends_at=end,
        layout=_need(payload.layout or "", what="layout"),
        facilities=_needs(payload.facilities, what="facility", plural="facilities"),
        accessibility=_needs(
            payload.accessibility_needs,
            what="accessibility need",
            plural="accessibility needs",
        ),
    )
    return _ValidBooking(int(raw_venue), starts_at, ends_at, needs)


def _prepared_booking(
    event_id: str, payload: BookingInput, user: User
) -> tuple[Event, Venue, _ValidBooking]:
    """Everything a request and a suitability check both need, refused the same way.

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

    valid = _validated_booking(payload, event)
    venue = venue_store.repository().get_venue(valid.venue_id)
    if venue is None:
        raise _venue_missing()
    return event, venue, valid


# -- US15.1: is the slot free? ---------------------------------------------------
#
# A request is checked against the full time the venue is occupied, setup and
# turnaround included, and against the venue's unavailability periods. The rule
# is `availability.check_slot`; these helpers read what it needs and say what it
# found in a 409 the form can show.


def _iso_minutes(moment: datetime) -> str:
    return moment.isoformat(timespec="minutes")


def slot_check(
    venue_id: int,
    starts_at: str,
    ends_at: str,
    *,
    venue: Venue | None = None,
    exclude_id: int | None = None,
) -> SlotCheck:
    """US15.1's rule for one slot at one venue, counting Held, Requested and Confirmed."""
    return availability.check_slot(
        venue if venue is not None else venue_store.repository().get_venue(venue_id),
        starts_at,
        ends_at,
        bookings_at_venue=booking_store.repository().list_for_venue(venue_id),
        unavailability=venue_unavailability_store.repository().list_for_venue(venue_id),
        exclude_id=exclude_id,
    )


def coordinator_titles(found: SlotCheck, user: User) -> dict[int, str]:
    """Titles of the clashing bookings' events that this user is assigned to, by booking id.

    A Coordinator sees only the events assigned to them (US8.6), so a clash with
    someone else's event is named by its booking number, status and times alone.
    """
    titles: dict[int, str] = {}
    for item in found.bookings:
        event = event_store.repository().get_event(item.booking.event_id)
        if event is not None and event.coordinator_id == user.id:
            titles[item.booking.id] = event.title
    return titles


def not_available(venue_name: str, found: SlotCheck, titles: dict[int, str]) -> HTTPException:
    """US15.1: 409 saying which bookings and periods the slot clashes with."""
    # Empty only when another write took the slot and has gone again since.
    phrases = availability.describe(found, titles=titles) or ["a booking made a moment ago"]
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": availability.unavailable_message(venue_name, found, phrases),
            "reason": "not-available",
            "clashes": phrases,
            "occupiedFrom": _iso_minutes(found.occupied_from),
            "occupiedTo": _iso_minutes(found.occupied_to),
        },
    )


class SuitabilityOut(BaseModel):
    """US18.1: Suitable or Not suitable, with every reason. US15.1: and whether it is free."""

    venue_id: str = Field(serialization_alias="venueId")
    suitable: bool
    #: Why it is not suitable, one sentence each. Empty when it is.
    reasons: list[str]
    #: What could not be checked, such as hours nobody has recorded.
    notes: list[str]
    #: US15.1: whether the slot is free, setup and turnaround included.
    available: bool = True
    #: US15.1: each booking or unavailability period it clashes with, as a phrase.
    clashes: list[str] = Field(default_factory=list)
    #: US15.1: the full window the booking would occupy.
    occupied_from: str = Field(default="", serialization_alias="occupiedFrom")
    occupied_to: str = Field(default="", serialization_alias="occupiedTo")


def _suitability_out(
    venue: Venue, verdict: Verdict, found: SlotCheck, titles: dict[int, str]
) -> SuitabilityOut:
    return SuitabilityOut(
        venue_id=str(venue.id),
        suitable=verdict.suitable,
        reasons=list(verdict.reasons),
        notes=list(verdict.notes),
        available=found.available,
        clashes=availability.describe(found, titles=titles),
        occupied_from=_iso_minutes(found.occupied_from),
        occupied_to=_iso_minutes(found.occupied_to),
    )


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

    US18.1: a venue that is not suitable cannot be requested. The refusal is a
    409 with `not-suitable` and every reason, from the same `assess` the
    suitability check shows, so the form and the rule agree.

    US15.1: nor can a slot that is not free, setup and turnaround included. The
    refusal is a 409 with `not-available`, naming each booking and period it
    clashes with. The store checks again under a lock on the venue, so two
    requests for one slot at once cannot both be stored.
    """
    event, venue, valid = _prepared_booking(event_id, payload, user)

    verdict = suitability.assess(venue, valid.needs)
    if not verdict.suitable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": f"{venue.name} is not suitable for this booking. "
                + " ".join(verdict.reasons),
                "reason": "not-suitable",
                "reasons": list(verdict.reasons),
            },
        )

    found = slot_check(venue.id, valid.starts_at, valid.ends_at, venue=venue)
    if not found.available:
        raise not_available(venue.name, found, coordinator_titles(found, user))

    try:
        created = booking_store.repository().create(
            event_id=event.id,
            venue_id=venue.id,
            starts_at=valid.starts_at,
            ends_at=valid.ends_at,
            requested_by_id=user.id,
            headcount=valid.needs.headcount,
            required_layout=valid.needs.layout,
            required_facilities=valid.needs.facilities,
            accessibility_needs=valid.needs.accessibility,
            expected_status=event.status,
        )
    except StaleEventStatus:
        raise _stale_request() from None
    except SlotTaken:
        # Another request took the slot between the check above and the write.
        found = slot_check(venue.id, valid.starts_at, valid.ends_at, venue=venue)
        raise not_available(venue.name, found, coordinator_titles(found, user)) from None
    return _booking_out(created)


@router.post("/{event_id}/bookings/suitability", response_model=SuitabilityOut)
def check_suitability(
    event_id: str,
    payload: BookingInput,
    user: Annotated[User, Depends(require_permission(Permission.BOOKINGS_REQUEST))],
) -> SuitabilityOut:
    """US18.1: whether the chosen venue suits this booking, before it is requested.

    Takes exactly what a request takes and stores nothing, so the form can show
    Suitable or Not suitable as the Coordinator picks a venue and fills in what
    the booking needs. Refused the way a request is: the same people, the same
    events and the same validation.
    """
    _, venue, valid = _prepared_booking(event_id, payload, user)
    found = slot_check(venue.id, valid.starts_at, valid.ends_at, venue=venue)
    return _suitability_out(
        venue, suitability.assess(venue, valid.needs), found, coordinator_titles(found, user)
    )


# -- US14.2: cancelling one booking ----------------------------------------------


class BookingCancellation(BaseModel):
    """Why a Coordinator is cancelling a venue booking (US14.2)."""

    reason: str = ""


#: `venue_bookings.cancellation_reason` is TEXT. The cap is about a reason
#: staying readable, as US7.1's is.
CANCELLATION_REASON_MAX = 2000


def _booking_not_found() -> HTTPException:
    """The same answer for a booking that is missing and one on another event."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": EventError.BOOKING_NOT_FOUND,
            "message": "That booking is not on this event.",
        },
    )


def _already_cancelled() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": "This booking has already been cancelled.",
            "reason": "already-cancelled",
        },
    )


@router.post("/{event_id}/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    event_id: str,
    booking_id: str,
    payload: BookingCancellation,
    user: Annotated[User, Depends(require_permission(Permission.BOOKINGS_REQUEST))],
) -> BookingOut:
    """US14.2: cancel one venue booking, with a reason, and change nothing else.

    Only this booking's row is written. The event's status and its other
    bookings are not touched at all, so changing one room never means redoing
    the plan. The cancelled booking stays on the event's list with who, when
    and why, and stops holding its venue for the slot (`HOLDS_VENUE`).

    The same Coordinator who may request may cancel (US8.6), and on an event at
    any status they can see: cancelling the hall for a Rejected event is how
    the venue is given back.

    404, then 409, then 400, as for a request. A booking on another event is
    404 rather than 403, for the reason `_not_found` gives for events.

    US4.6: except a Cancelled event, which is read-only. Its cancellation
    already released every booking that held a venue.

    US14.4: an expired hold is history and its slot is already free, so there
    is nothing to cancel, whether or not the sweep has marked it Expired yet.
    """
    event = _readable(_as_id(event_id), user)
    _refuse_if_cancelled(event)
    try:
        booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        booking = None
    if booking is None or booking.event_id != event.id:
        raise _booking_not_found()

    if booking.status is BookingStatus.CANCELLED:
        raise _already_cancelled()
    if booking.hold_expired:
        raise _nothing_to_cancel(booking)

    reason = payload.reason.strip()
    if not reason:
        raise _invalid_booking("Give a reason for cancelling this booking.")
    if len(reason) > CANCELLATION_REASON_MAX:
        raise _invalid_booking(f"Keep the reason to {CANCELLATION_REASON_MAX} characters or fewer.")

    try:
        cancelled = booking_store.repository().cancel(booking.id, actor_id=user.id, reason=reason)
    except StaleBookingStatus:
        # Someone else cancelled it between the read above and this write, or
        # (US14.4) the sweep expired it.
        current = booking_store.repository().get_booking(booking.id)
        if current is not None and current.hold_expired:
            raise _nothing_to_cancel(current) from None
        raise _already_cancelled() from None
    # US15.2: a cancelled booking frees its slot, which may resolve a flagged
    # clash at this venue, its own included.
    conflict_flags.resolve_quietly(cancelled.venue_id)
    arrangement_review.refresh_if_reviewed(cancelled.event_id)
    if cancelled.conflict is not None or cancelled.event_conflict_reason:
        cancelled = booking_store.repository().get_booking(cancelled.id) or cancelled
    return _booking_out(cancelled)


# -- US14.3: turning a tentative hold into a request -----------------------------


@router.post("/{event_id}/bookings/{booking_id}/request", response_model=BookingOut)
def request_held_booking(
    event_id: str,
    booking_id: str,
    user: Annotated[User, Depends(require_permission(Permission.BOOKINGS_REQUEST))],
) -> BookingOut:
    """US14.3: the Coordinator asks for a venue Venue Staff held for them.

    Held -> Requested, before the hold expires, and on the same terms as a new
    request (US14.1): the assigned Coordinator, on an Approved or Planning
    event, which a first request moves to Planning (US4.5). The times are the
    ones held. 404, then 409, as for cancelling.

    US15.1: the hold's own slot is left out of the check, but a hold that has
    clashed since it was placed (a setup or turnaround change, US15.2) cannot
    become a request until the clash is resolved.
    """
    event = _readable(_as_id(event_id), user)
    try:
        booking = booking_store.repository().get_booking(int(booking_id))
    except ValueError:
        booking = None
    if booking is None or booking.event_id != event.id:
        raise _booking_not_found()
    # US14.4: expired first, so a swept (Expired) hold is refused as expired
    # rather than as "not a hold".
    if booking.hold_expired:
        raise _hold_expired(booking)
    if booking.status is not BookingStatus.HELD:
        raise _not_held(booking.status)
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
    found = slot_check(booking.venue_id, booking.starts_at, booking.ends_at, exclude_id=booking.id)
    if not found.available:
        raise not_available(booking.venue_name, found, coordinator_titles(found, user))
    try:
        requested = booking_store.repository().request_hold(
            booking.id, actor_id=user.id, expected_status=event.status
        )
    except HoldExpired:
        raise _hold_expired(booking) from None
    except StaleBookingStatus:
        current = booking_store.repository().get_booking(booking.id)
        if current is not None and current.hold_expired:
            # US14.4: the sweep expired it between the check above and the write.
            raise _hold_expired(current) from None
        raise _not_held(current.status if current else BookingStatus.CANCELLED) from None
    except StaleEventStatus:
        raise _stale_request() from None
    return _booking_out(requested)


def _not_held(current: BookingStatus) -> HTTPException:
    message = (
        "This hold has already been turned into a booking request."
        if current is BookingStatus.REQUESTED
        else "This hold has been cancelled."
        if current is BookingStatus.CANCELLED
        else "Only a hold can be turned into a booking request."
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": EventError.REFUSED, "message": message, "reason": "not-held"},
    )


def _nothing_to_cancel(booking: Booking) -> HTTPException:
    """US14.4: an expired hold already gave its slot back."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": (
                f"The hold on {booking.venue_name or 'this venue'} expired at "
                f"{booking.hold_expires_at.replace('T', ' ')[:16]}, so its slot is already "
                "free. There is nothing to cancel."
            ),
            "reason": "hold-expired",
        },
    )


def _hold_expired(booking: Booking) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": EventError.REFUSED,
            "message": (
                f"The hold on {booking.venue_name or 'this venue'} expired at "
                f"{booking.hold_expires_at.replace('T', ' ')[:16]}. Ask Venue Staff to "
                "hold it again, "
                "or request the venue as a new booking."
            ),
            "reason": "hold-expired",
        },
    )


@router.post("/{event_id}/arrangements/recheck", response_model=EventOut)
def recheck_arrangements(
    event_id: str, user: Annotated[User, Depends(require_permission(Permission.EVENTS_REVIEW))]
) -> EventOut:
    event = _readable(_as_id(event_id), user)
    _refuse_if_cancelled(event)
    return _to_out(arrangement_review.recheck(event))
