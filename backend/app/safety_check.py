"""US4.4: when an event is ready for the Operational Safety Check.

The story puts a Pending Safety Check stage between planning and preparation,
entered "once all active venue bookings are Confirmed and equipment is
reserved". This module is that rule, kept apart from the routes for the same
reason `app.event_status` is: the check that decides whether the event may move
is the one that explains why it may not.

What counts as *active* is the rest of the system's answer, not a new one: a
booking is active while it holds its venue (`Booking.holds_venue_at` — Requested,
Confirmed, or Held and not yet expired), and an equipment line is active until
it is removed. Cancelled, Rejected and expired bookings are history and do not
block the check.

Two refusals go slightly beyond the literal wording, because sending the event
on would otherwise hand the Safety Officer something that is about to change:

* a Confirmed booking flagged "Conflict - review needed" (US15.2) is not a venue
  anyone can rely on, so it blocks until it is resolved;
* an Organiser's change request that nobody has answered (US11.1) could move
  the date or the attendance the Safety Officer is about to assess.

US17.2 adds one more: an arrangement the Safety Officer flagged for re-review
when they last asked for changes, and that the Coordinator has not yet marked
re-reviewed, means the event is coming back with that request unanswered.

The database re-checks all of this inside the transaction that moves the
event (`send_event_to_safety_check` in SUPABASE_ADD_SAFETY_CHECK_STATUS.sql),
so a booking or equipment line that changes after this check is caught there.
"""

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from app.booking_store import Booking, BookingStatus, local_now
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_status import EventStatus

#: The equipment line status US19.3 sets when Technical Support reserve stock.
#: Every other active status — Requested today, Unavailable once US19.3 adds
#: it — is an arrangement still outstanding.
EQUIPMENT_RESERVED = RESERVED

#: `status_changes.notes` is unbounded TEXT; like the other notes, this cap is
#: about keeping the Safety Officer's message readable.
SAFETY_NOTE_MAX = 2000


class SafetyCheckRefusal(StrEnum):
    """Why an event cannot be sent for its safety check yet."""

    ARRANGEMENT_REVIEW_PENDING = "arrangement-review-pending"
    EQUIPMENT_CONFLICT = "equipment-conflict"
    NOT_PLANNING = "not-planning"
    CHANGE_PENDING = "change-pending"
    FLAGS_OPEN = "safety-flags-open"
    NO_CONFIRMED_VENUE = "no-confirmed-venue"
    VENUE_NOT_CONFIRMED = "venue-not-confirmed"
    VENUE_CONFLICT = "venue-conflict"
    EQUIPMENT_NOT_RESERVED = "equipment-not-reserved"


SAFETY_CHECK_REFUSAL_MESSAGES: dict[SafetyCheckRefusal, str] = {
    SafetyCheckRefusal.ARRANGEMENT_REVIEW_PENDING: (
        "Complete the arrangement rechecks before the safety check."
    ),
    SafetyCheckRefusal.EQUIPMENT_CONFLICT: (
        "An equipment reservation is flagged for review. Resolve it before the safety check."
    ),
    SafetyCheckRefusal.NOT_PLANNING: ("Only an event in Planning can be sent for a safety check."),
    SafetyCheckRefusal.CHANGE_PENDING: (
        "Approve or reject the Organiser's change request before sending this event "
        "for a safety check."
    ),
    SafetyCheckRefusal.FLAGS_OPEN: (
        "The Safety Officer flagged arrangements for re-review. Mark each one "
        "re-reviewed before sending the event for its safety check again."
    ),
    SafetyCheckRefusal.NO_CONFIRMED_VENUE: (
        "This event needs at least one Confirmed venue booking before its safety check."
    ),
    SafetyCheckRefusal.VENUE_NOT_CONFIRMED: (
        "Every active venue booking must be Confirmed by Venue Staff before the safety "
        "check. Wait for a decision on the rest, or cancel the ones you no longer need."
    ),
    SafetyCheckRefusal.VENUE_CONFLICT: (
        "A Confirmed venue booking is flagged “Conflict – review needed”. "
        "Resolve it before the safety check."
    ),
    SafetyCheckRefusal.EQUIPMENT_NOT_RESERVED: (
        "Every equipment request must be reserved by Technical Support before the "
        "safety check. Remove any line the event no longer needs."
    ),
}


def check_ready_for_safety_check(
    *,
    status: EventStatus,
    change_requested: bool,
    bookings: Iterable[Booking],
    equipment: Iterable[EquipmentRequest],
    now: datetime | None = None,
    flags_open: bool = False,
    arrangement_review_pending: bool = False,
) -> SafetyCheckRefusal | None:
    """US4.4: may this event move Planning -> Pending Safety Check now?

    Returns the first reason it may not, or None when it may. Status comes
    first so an event that is not in Planning is never told about its venues;
    the venue reasons come before equipment because a venue is the thing the
    safety check is mostly about. US17.2's open flags come straight after the
    change request: they are the Safety Officer's last word on this event.
    """
    if status is not EventStatus.PLANNING:
        return SafetyCheckRefusal.NOT_PLANNING
    if change_requested:
        return SafetyCheckRefusal.CHANGE_PENDING
    if flags_open:
        return SafetyCheckRefusal.FLAGS_OPEN
    if arrangement_review_pending:
        return SafetyCheckRefusal.ARRANGEMENT_REVIEW_PENDING
    current = now or local_now()
    active = [booking for booking in bookings if booking.holds_venue_at(current)]
    if not active:
        return SafetyCheckRefusal.NO_CONFIRMED_VENUE
    if any(booking.status is not BookingStatus.CONFIRMED for booking in active):
        return SafetyCheckRefusal.VENUE_NOT_CONFIRMED
    if any(booking.conflict is not None or booking.event_conflict_reason for booking in active):
        return SafetyCheckRefusal.VENUE_CONFLICT
    lines = list(equipment)
    if any(line.status != EQUIPMENT_RESERVED for line in lines):
        return SafetyCheckRefusal.EQUIPMENT_NOT_RESERVED
    if any(line.event_conflict_reason for line in lines):
        return SafetyCheckRefusal.EQUIPMENT_CONFLICT
    return None


def safety_check_refusal_message(reason: SafetyCheckRefusal) -> str:
    return SAFETY_CHECK_REFUSAL_MESSAGES[reason]


#: The `kind` the event history gives an entry the Safety Officer wrote when
#: sending an event back, so its note is labelled as theirs (see
#: `app.change_requests.history_kind` for the same idea on change requests).
KIND_SAFETY_RETURN = "safety-return"


def history_kind(*, from_status: EventStatus | None, to_status: EventStatus) -> str:
    """Pending Safety Check -> Planning is only ever the Safety Officer's doing."""
    if from_status is EventStatus.PENDING_SAFETY_CHECK and to_status is EventStatus.PLANNING:
        return KIND_SAFETY_RETURN
    return ""
