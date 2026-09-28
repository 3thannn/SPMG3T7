"""The event status model — the server's half of US4.1 and US4.2.

The values match the `event_status` enum in Postgres exactly, and the frontend's
`status.ts` matches both. Three copies sounds like two too many; what keeps them
honest is that the database rejects a value it does not know, so a drift here
fails loudly on the first write rather than quietly storing nonsense.

US4.2's rules live here rather than in the route, so the check that decides
whether a submit is allowed is the same one that explains why it was not.
"""

from enum import StrEnum


class EventStatus(StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    PLANNING = "Planning"
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

#: US4.3: every status change the current workflow may make. Keeping US4.2's
#: Draft -> Submitted transition here means the older submission flow and the
#: new review decisions share one source of truth.
VALID_TRANSITIONS: frozenset[tuple[EventStatus, EventStatus]] = frozenset(
    {
        (EventStatus.DRAFT, EventStatus.SUBMITTED),
        (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
        (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
        (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
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
