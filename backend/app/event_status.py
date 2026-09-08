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
SPRINT_1_REACHABLE: tuple[EventStatus, ...] = (EventStatus.DRAFT, EventStatus.SUBMITTED)


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
