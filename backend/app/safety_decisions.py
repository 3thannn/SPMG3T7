"""US17.2: the Safety Officer's decision on an event Pending Safety Check.

Three outcomes, each a move out of Pending Safety Check (US4.4):

* Approve -> Confirmed.
* Request changes -> back to Planning, with a note saying what must change. The
  venue bookings and equipment lines the note is about are flagged for
  re-review, and the assigned Coordinator is told (US10.2).
* Reject -> back to Planning, with the reason. The story records the
  assumption that a rejection returns the event to Planning rather than ending
  it, so the status alone cannot tell the two apart; the decision record does.

Every decision is a `safety_reviews` row beside the US4.2 audit entry, so it is
timestamped, attributable, and says which of the three it was.

"An event coming back into Pending Safety Check needs a fresh decision." A
decision belongs to one stay in Pending Safety Check, identified by when the
event entered it (`safety_review.entered_safety_check`). The Safety Officer's
page sends that time with the decision, and a decision made on a stay that has
since ended — the event was sent back and sent again — is refused instead of
landing on a submission nobody has looked at.

A flag stays open until the assigned Coordinator marks it re-reviewed, and an
open flag keeps the event from being sent for its check again
(`app.safety_check`). That is what makes a flag more than a label.
"""

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from app.event_status import EventStatus
from app.safety_check import SAFETY_NOTE_MAX


class SafetyOutcome(StrEnum):
    """What the Safety Officer decided. The value is what `safety_reviews` stores."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    REJECTED = "rejected"


#: Where each outcome sends the event. Both refusals go back to Planning.
OUTCOME_STATUS: dict[SafetyOutcome, EventStatus] = {
    SafetyOutcome.APPROVED: EventStatus.CONFIRMED,
    SafetyOutcome.CHANGES_REQUESTED: EventStatus.PLANNING,
    SafetyOutcome.REJECTED: EventStatus.PLANNING,
}

#: The outcomes that need words, and what to say when they are missing.
NOTE_REQUIRED: dict[SafetyOutcome, str] = {
    SafetyOutcome.CHANGES_REQUESTED: (
        "Tell the Coordinator what needs to change before this event is safe."
    ),
    SafetyOutcome.REJECTED: "Give the reason for rejecting this event's safety check.",
}

FLAGS_ONLY_ON_CHANGES = "Only a request for changes flags arrangements for re-review."
UNKNOWN_BOOKING = "Flag only the venue bookings shown in this safety review."
UNKNOWN_EQUIPMENT = "Flag only the equipment shown in this safety review."
CHECK_MOVED_ON = (
    "This event was sent back and submitted again since you opened it. "
    "Reload it and review the current submission."
)


def to_status(outcome: SafetyOutcome) -> EventStatus:
    return OUTCOME_STATUS[outcome]


def note_error(outcome: SafetyOutcome, note: str) -> str | None:
    """Why the note will not do, or None. `note` is already trimmed."""
    if not note and outcome in NOTE_REQUIRED:
        return NOTE_REQUIRED[outcome]
    if len(note) > SAFETY_NOTE_MAX:
        return f"Keep the note to {SAFETY_NOTE_MAX} characters or fewer."
    return None


def flag_error(
    outcome: SafetyOutcome,
    *,
    booking_ids: Iterable[int],
    equipment_ids: Iterable[int],
    flaggable_bookings: Iterable[int],
    flaggable_equipment: Iterable[int],
) -> str | None:
    """Why these flags will not do, or None.

    Only a request for changes flags anything: an approval has nothing to
    re-review, and a rejection is about the event as a whole. What can be
    flagged is what the Safety Officer was shown (US17.1) — the bookings that
    hold their venue and the reserved equipment — so a stale or made-up id is
    refused rather than flagging something they never saw.
    """
    bookings, equipment = set(booking_ids), set(equipment_ids)
    if not bookings and not equipment:
        return None
    if outcome is not SafetyOutcome.CHANGES_REQUESTED:
        return FLAGS_ONLY_ON_CHANGES
    if bookings - set(flaggable_bookings):
        return UNKNOWN_BOOKING
    if equipment - set(flaggable_equipment):
        return UNKNOWN_EQUIPMENT
    return None


def same_check(started_at: str, entered: str) -> bool:
    """Whether a decision made on the stay that began `started_at` is for the current one.

    Compared as times, not text, so "2026-10-27 06:00:00" and
    "2026-10-27T06:00:00" are the same moment. Raises ValueError when
    `started_at` is not a timestamp at all, which is a bad request rather
    than a stale one.
    """
    return datetime.fromisoformat(started_at) == datetime.fromisoformat(entered)
