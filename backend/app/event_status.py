"""The event status model — the server's half of US4.1 and US4.2.

The values match the `event_status` enum in Postgres exactly, and the frontend's
`status.ts` matches both. Three copies sounds like two too many; what keeps them
honest is that the database rejects a value it does not know, so a drift here
fails loudly on the first write rather than quietly storing nonsense.

US4.2's rules live here rather than in the route, so the check that decides
whether a submit is allowed is the same one that explains why it was not.
"""

from datetime import datetime, timedelta, timezone
from enum import StrEnum


class EventStatus(StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    PENDING_SAFETY_CHECK = "Pending Safety Check"
    APPROVED = "Approved"
    PLANNING = "Planning"
    #: US4.4 (Week 7 change #6): between planning and preparation, so that no
    #: event reaches Confirmed without the Safety Officer's sign-off.
    PENDING_SAFETY_CHECK = "Pending Safety Check"
    CONFIRMED = "Confirmed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


#: What Sprint 1 can actually produce. The rest of the label set is displayable
#: but not yet reachable; it becomes reachable with the Review and Booking epics.
#: US7.3 added the first of those — a Coordinator asking for clarification moves
#: an event to Under Review — so that value is now reachable too.
SPRINT_1_REACHABLE: tuple[EventStatus, ...] = (EventStatus.DRAFT, EventStatus.SUBMITTED)

#: Statuses a Coordinator may ask for clarification on (US7.3).
#:
#: Submitted is the case the story describes. Under Review is included because a
#: first answer often raises a second question, and refusing a follow-up would
#: mean a Coordinator had one chance to ask. A Draft is not here — a Coordinator
#: cannot see one — and neither is a decided event: once it is Approved or
#: Rejected, asking for changes is no longer a review, it is a reopening, and
#: that is a different story.
CLARIFIABLE: tuple[EventStatus, ...] = (
    EventStatus.SUBMITTED,
    EventStatus.UNDER_REVIEW,
)

#: US4.6: the statuses an event has finished in. Nothing moves an event on from
#: one of these, cancellation included.
CLOSED: tuple[EventStatus, ...] = (
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
    EventStatus.REJECTED,
)

#: US4.6: "any event that isn't Completed, Cancelled or Rejected" may be
#: cancelled, so the set is worked out from `CLOSED` rather than listed twice.
CANCELLABLE: tuple[EventStatus, ...] = tuple(
    status for status in EventStatus if status not in CLOSED
)

#: US4.3: every status change the current workflow may make. Keeping US4.2's
#: Draft -> Submitted transition here means the older submission flow and the
#: new review decisions share one source of truth.
VALID_TRANSITIONS: frozenset[tuple[EventStatus, EventStatus]] = frozenset(
    {
        (EventStatus.DRAFT, EventStatus.SUBMITTED),
        (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
        (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
        (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
        (EventStatus.APPROVED, EventStatus.PLANNING),
        # US4.4: Planning -> Pending Safety Check once every active venue
        # booking is Confirmed and every equipment line is reserved
        # (`app.safety_check`), then the Safety Officer either signs it off or
        # sends it back to Planning. Pending Safety Check is the only way into
        # Confirmed; the database refuses any other route there as well.
        (EventStatus.PLANNING, EventStatus.PENDING_SAFETY_CHECK),
        (EventStatus.PENDING_SAFETY_CHECK, EventStatus.CONFIRMED),
        (EventStatus.PENDING_SAFETY_CHECK, EventStatus.PLANNING),
        (EventStatus.CONFIRMED, EventStatus.COMPLETED),
        # US4.6: the owning Organiser or the assigned Coordinator cancels
        # (`app.event_cancellation`). Cancelled is final, like the other two.
        *((status, EventStatus.CANCELLED) for status in CANCELLABLE),
    }
)


def transition_allowed(*, from_status: EventStatus, to_status: EventStatus) -> bool:
    """Whether US4.3 permits this status update.

    Writing the same status is not a transition. US7.3 deliberately does that
    when a Coordinator asks a follow-up question on an event already Under
    Review, so no-op updates remain valid while every real move is allowlisted.
    """
    return from_status == to_status or (from_status, to_status) in VALID_TRANSITIONS


def transition_refusal_message(
    *, from_status: EventStatus, to_status: EventStatus
) -> str:
    return f"An event cannot move from {from_status} to {to_status}."


class SubmitRefusal(StrEnum):
    """Why a submit was refused, so the client can explain rather than just deny."""

    NOT_OWNER = "not-owner"
    ALREADY_SUBMITTED = "already-submitted"
    NOT_DRAFT = "not-draft"


REFUSAL_MESSAGES: dict[SubmitRefusal, str] = {
    SubmitRefusal.NOT_OWNER: "Only the Organiser who owns this event can submit it.",
    SubmitRefusal.ALREADY_SUBMITTED: (
        "This event has already been submitted. An event can only be submitted once."
    ),
    SubmitRefusal.NOT_DRAFT: "Only a Draft event can be submitted.",
}


def check_submit(
    *, status: EventStatus, organiser_id: int, actor_id: int
) -> SubmitRefusal | None:
    """US4.2: Draft -> Submitted, exactly once, by the Organiser who owns it.

    Returns the reason it was refused, or None when it is allowed. Ownership is
    checked before status so that someone else's Submitted event reads as "not
    yours" rather than telling them about its state.
    """
    if organiser_id != actor_id:
        return SubmitRefusal.NOT_OWNER
    if status is EventStatus.SUBMITTED:
        return SubmitRefusal.ALREADY_SUBMITTED
    if status is not EventStatus.DRAFT:
        return SubmitRefusal.NOT_DRAFT
    return None


def refusal_message(reason: SubmitRefusal) -> str:
    return REFUSAL_MESSAGES[reason]


class ClarificationRefusal(StrEnum):
    """Why a request for clarification was refused (US7.3)."""

    NOT_YET_SUBMITTED = "not-yet-submitted"
    ALREADY_DECIDED = "already-decided"


CLARIFICATION_REFUSAL_MESSAGES: dict[ClarificationRefusal, str] = {
    ClarificationRefusal.NOT_YET_SUBMITTED: (
        "This event has not been submitted yet, so there is nothing to review."
    ),
    ClarificationRefusal.ALREADY_DECIDED: (
        "This event has already been decided, so it is no longer under review."
    ),
}


def check_clarification(*, status: EventStatus) -> ClarificationRefusal | None:
    """US7.3: a Coordinator may ask for clarification on an event under review.

    Returns the reason it was refused, or None when it is allowed. Assignment
    is enforced by the route's readable-event check; this function decides only
    whether the current status can be reviewed.

    A Draft reads as "not submitted yet" rather than as a missing event, because
    the caller reached this check through an event they were allowed to fetch.
    """
    if status is EventStatus.DRAFT:
        return ClarificationRefusal.NOT_YET_SUBMITTED
    if status not in CLARIFIABLE:
        return ClarificationRefusal.ALREADY_DECIDED
    return None


def clarification_refusal_message(reason: ClarificationRefusal) -> str:
    return CLARIFICATION_REFUSAL_MESSAGES[reason]


#: Statuses an event may have venues requested for (US14.1).
#:
#: Requests start after approval. Further requests leave an event in Planning.
BOOKABLE: tuple[EventStatus, ...] = (
    EventStatus.APPROVED,
    EventStatus.PLANNING,
)


class BookingRefusal(StrEnum):
    """Why venues cannot be requested for an event (US14.1)."""

    NOT_YET_SUBMITTED = "not-yet-submitted"
    NOT_APPROVED = "not-approved"
    EVENT_CLOSED = "event-closed"


BOOKING_REFUSAL_MESSAGES: dict[BookingRefusal, str] = {
    BookingRefusal.NOT_YET_SUBMITTED: (
        "This event has not been submitted yet, so no venues can be requested for it."
    ),
    BookingRefusal.NOT_APPROVED: "Approve this event before requesting a venue.",
    BookingRefusal.EVENT_CLOSED: (
        "This event is closed, so no more venues can be requested for it."
    ),
}


def check_booking(*, status: EventStatus) -> BookingRefusal | None:
    """US14.1: whether venues may be requested for an event at this status.

    Returns the reason it was refused, or None when it is allowed. As with
    `check_clarification`, the assignment rule (US8.6) is the route's
    readable-event check; this decides only whether the status allows it.
    """
    if status is EventStatus.DRAFT:
        return BookingRefusal.NOT_YET_SUBMITTED
    if status in (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW):
        return BookingRefusal.NOT_APPROVED
    if status not in BOOKABLE:
        return BookingRefusal.EVENT_CLOSED
    return None


def booking_refusal_message(reason: BookingRefusal) -> str:
    return BOOKING_REFUSAL_MESSAGES[reason]


class CompletionRefusal(StrEnum):
    MISSING_END_TIME = "missing-end-time"
    INVALID_END_TIME = "invalid-end-time"
    EVENT_NOT_ENDED = "event-not-ended"


COMPLETION_REFUSAL_MESSAGES: dict[CompletionRefusal, str] = {
    CompletionRefusal.MISSING_END_TIME: "Set an end date and time before completing this event.",
    CompletionRefusal.INVALID_END_TIME: "The event end date and time is invalid.",
    CompletionRefusal.EVENT_NOT_ENDED: (
        "This event can be completed only after its end date and time has passed."
    ),
}


def check_completion(ends_at: str, *, now: datetime | None = None) -> CompletionRefusal | None:
    """Event timestamps are naive Singapore local times; equality is too early."""
    if not ends_at:
        return CompletionRefusal.MISSING_END_TIME
    try:
        end = datetime.fromisoformat(ends_at)
    except ValueError:
        return CompletionRefusal.INVALID_END_TIME
    if end.tzinfo is not None:
        return CompletionRefusal.INVALID_END_TIME
    current = now or datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    if current <= end:
        return CompletionRefusal.EVENT_NOT_ENDED
    return None


def completion_refusal_message(reason: CompletionRefusal) -> str:
    return COMPLETION_REFUSAL_MESSAGES[reason]
