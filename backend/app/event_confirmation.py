"""US4.7: the assigned Coordinator confirms the event once every approval is in.

Pending Safety Check -> Confirmed used to be the Safety Officer's approval
(US4.4). It is now the Coordinator's own action, so the Organiser only sees
"Confirmed" when the event is actually ready to go ahead. The Coordinator may
confirm only when all of these hold:

* the Safety Officer approved the current stay in Pending Safety Check (US17.2);
* every active venue booking is Confirmed, and none needs a replacement
  (US12.2) or is flagged "Conflict – review needed" (US15.2, or US11.2's
  re-check);
* every equipment line is Reserved (US19.3);
* no change request is waiting for an answer (US11.1).

When one does not, the refusal names what is missing ("Breakout Room B is still
awaiting Venue Staff approval."), so the Coordinator knows whom to chase. The
check is a plain function, like `app.safety_check`, and the database repeats it
in the transaction that confirms (`confirm_event` in
SUPABASE_US4_7_CONFIRM_EVENT.sql), which is also the only way into Confirmed.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.booking_store import Booking, BookingStatus, local_now
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_status import EventStatus
from app.safety_decision_store import SafetyDecision
from app.safety_decisions import SafetyOutcome, same_check


class ConfirmRefusal(StrEnum):
    """Why an event cannot be confirmed yet."""

    NOT_PENDING = "not-pending-safety-check"
    NOT_APPROVED = "safety-not-approved"
    NO_CONFIRMED_VENUE = "no-confirmed-venue"
    VENUE_NOT_CONFIRMED = "venue-not-confirmed"
    VENUE_NEEDS_REPLACEMENT = "venue-needs-replacement"
    VENUE_CONFLICT = "venue-conflict"
    ARRANGEMENT_REVIEW_PENDING = "arrangement-review-pending"
    EQUIPMENT_NOT_RESERVED = "equipment-not-reserved"
    EQUIPMENT_CONFLICT = "equipment-conflict"
    CHANGE_PENDING = "change-pending"


@dataclass(frozen=True)
class Refused:
    """The first thing missing, and the sentence that names it."""

    reason: ConfirmRefusal
    message: str


NOT_PENDING_MESSAGE = "Only an event Pending Safety Check can be confirmed."
NOT_APPROVED_MESSAGE = "The Safety Officer has not approved this event's safety check yet."
NO_CONFIRMED_VENUE_MESSAGE = (
    "This event needs at least one Confirmed venue booking before it is confirmed."
)
ARRANGEMENT_REVIEW_MESSAGE = "Complete the arrangement rechecks before confirming the event."
CHANGE_PENDING_MESSAGE = (
    "Approve or reject the Organiser's change request before confirming the event."
)


def current_approval(decisions: Iterable[SafetyDecision], entered: str) -> SafetyDecision | None:
    """The Safety Officer's approval of the stay that began at `entered`, if any.

    An approval of an earlier stay does not count: the event has been sent back
    and sent again since, and whatever changed has not been looked at.
    """
    for decision in decisions:
        if decision.outcome is SafetyOutcome.APPROVED and same_check(
            decision.check_started_at, entered
        ):
            return decision
    return None


def check_ready_to_confirm(
    *,
    status: EventStatus,
    approved: bool,
    change_requested: bool,
    bookings: Iterable[Booking],
    equipment: Iterable[EquipmentRequest],
    arrangement_review_pending: bool = False,
    now: datetime | None = None,
) -> Refused | None:
    """US4.7: may the Coordinator confirm this event now? None when it may.

    In the order the story lists them: the safety approval, the venues, the
    equipment, then the change request. Within each, the first item that is
    not ready is the one named.
    """
    if status is not EventStatus.PENDING_SAFETY_CHECK:
        return Refused(ConfirmRefusal.NOT_PENDING, NOT_PENDING_MESSAGE)
    if not approved:
        return Refused(ConfirmRefusal.NOT_APPROVED, NOT_APPROVED_MESSAGE)

    current = now or local_now()
    every = list(bookings)
    for booking in every:
        if booking.status is BookingStatus.NEEDS_REPLACEMENT:
            return Refused(
                ConfirmRefusal.VENUE_NEEDS_REPLACEMENT,
                f"{booking.venue_name} needs a replacement venue.",
            )
    active = [booking for booking in every if booking.holds_venue_at(current)]
    for booking in active:
        if booking.status is BookingStatus.REQUESTED:
            return Refused(
                ConfirmRefusal.VENUE_NOT_CONFIRMED,
                f"{booking.venue_name} is still awaiting Venue Staff approval.",
            )
        if booking.status is not BookingStatus.CONFIRMED:
            return Refused(
                ConfirmRefusal.VENUE_NOT_CONFIRMED,
                f"{booking.venue_name} is only held. Request it, and have Venue Staff "
                "approve it, or cancel the hold.",
            )
        if booking.conflict is not None or booking.event_conflict_reason:
            return Refused(
                ConfirmRefusal.VENUE_CONFLICT,
                f"{booking.venue_name} is flagged “Conflict – review needed”.",
            )
    if not active:
        return Refused(ConfirmRefusal.NO_CONFIRMED_VENUE, NO_CONFIRMED_VENUE_MESSAGE)
    if arrangement_review_pending:
        return Refused(ConfirmRefusal.ARRANGEMENT_REVIEW_PENDING, ARRANGEMENT_REVIEW_MESSAGE)

    for line in equipment:
        if line.status != RESERVED:
            return Refused(
                ConfirmRefusal.EQUIPMENT_NOT_RESERVED,
                f"{line.equipment_type} is not reserved by Technical Support yet.",
            )
        if line.event_conflict_reason:
            return Refused(
                ConfirmRefusal.EQUIPMENT_CONFLICT,
                f"{line.equipment_type} is flagged for review.",
            )

    if change_requested:
        return Refused(ConfirmRefusal.CHANGE_PENDING, CHANGE_PENDING_MESSAGE)
    return None
