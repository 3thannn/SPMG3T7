"""US4.6: cancelling an event, and giving back what it held.

The owning Organiser or the assigned Coordinator cancels any event that is not
already Completed, Cancelled or Rejected, with a reason. This module is the
rule and what follows it, kept apart from the routes for the reason
`app.safety_check` is: the check that decides is the one that explains.

What a cancellation does, all in one transaction (`cancel_event` in
SUPABASE_US4_6_CANCEL_EVENT.sql, or `InMemoryEvents.cancel_event` in tests):

* the event moves to Cancelled, with a history entry saying who, when and why;
* every venue booking that still holds its venue - Requested, Confirmed, or a
  hold that has not expired - is Cancelled with the same reason, so its slot is
  free. Cancelled, Rejected and expired holds are history and are left alone;
* every equipment line not already removed is Removed, so its quantity is free;
* every registration still Registered is Event Cancelled (US20.1), and
  registration closes. Withdrawn registrations are history and are left alone.

Then, best effort, because the cancellation has already happened: flags at the
freed venues are re-checked (US15.2), and the Organiser, the Coordinator,
Venue Staff, Tech Support and the registered Attendees are told
(`notify_event_cancelled`).

A cancelled event is read-only. The routes that change an event refuse it,
most of them already through their own status rules.
"""

import logging
from enum import StrEnum

from app import booking_store, conflict_flags, equipment_store, registration_store
from app.event_status import EventStatus
from app.event_store import CancelledEvent
from app.notifications import notify_event_cancelled
from app.users import User

logger = logging.getLogger(__name__)

#: `status_changes.notes` is unbounded TEXT; like the other reasons, the cap is
#: about keeping it readable.
CANCELLATION_REASON_MAX = 2000

#: The `kind` the history gives the entry a cancellation wrote, so its note is
#: labelled as the reason for cancelling rather than as a request.
KIND_CANCELLATION = "cancellation"

#: Why a write on a cancelled event was refused.
READ_ONLY_MESSAGE = "This event has been cancelled, so it can no longer be changed."


class CancelRefusal(StrEnum):
    """Why an event cannot be cancelled."""

    ALREADY_CANCELLED = "already-cancelled"
    COMPLETED = "event-completed"
    REJECTED = "event-rejected"


CANCEL_REFUSAL_MESSAGES: dict[CancelRefusal, str] = {
    CancelRefusal.ALREADY_CANCELLED: "This event has already been cancelled.",
    CancelRefusal.COMPLETED: "This event has already been completed, so it cannot be cancelled.",
    CancelRefusal.REJECTED: "This event was rejected, so there is nothing to cancel.",
}

#: One refusal per closed status (`event_status.CLOSED`).
_REFUSAL_FOR: dict[EventStatus, CancelRefusal] = {
    EventStatus.CANCELLED: CancelRefusal.ALREADY_CANCELLED,
    EventStatus.COMPLETED: CancelRefusal.COMPLETED,
    EventStatus.REJECTED: CancelRefusal.REJECTED,
}


def check_cancel(*, status: EventStatus) -> CancelRefusal | None:
    """US4.6: may an event at this status be cancelled?

    Who may cancel is the route's readable-event check: the Organiser sees only
    the events they own and the Coordinator only the ones assigned to them.
    """
    return _REFUSAL_FOR.get(status)


def cancel_refusal_message(reason: CancelRefusal) -> str:
    return CANCEL_REFUSAL_MESSAGES[reason]


def history_kind(*, to_status: EventStatus) -> str:
    """Every move to Cancelled is a cancellation, and its note is the reason."""
    return KIND_CANCELLATION if to_status is EventStatus.CANCELLED else ""


def settle_quietly(cancelled: CancelledEvent, *, actor: User, reason: str) -> None:
    """After a stored cancellation: clear what it resolved and tell who it affects.

    Never raises. The cancellation is the thing that was asked for and it has
    already happened, so a failure here is logged rather than reported as one.
    """
    event = cancelled.event
    try:
        released = set(cancelled.booking_ids)
        bookings = [
            booking
            for booking in booking_store.repository().list_for_event(event.id)
            if booking.id in released
        ]
        lines = [
            line
            for line in map(equipment_store.repository().get_request, cancelled.equipment_ids)
            if line is not None
        ]
    except Exception:
        logger.exception("Could not read what the cancellation of event %s released", event.id)
        bookings, lines = [], []

    # Read on its own, so a failure here loses only the Attendees' notices.
    try:
        ended = set(cancelled.registration_ids)
        attendee_ids = [
            registration.attendee_id
            for registration in registration_store.repository().list_for_event(event.id)
            if registration.id in ended
        ]
    except Exception:
        logger.exception("Could not read the registrations event %s's cancellation ended", event.id)
        attendee_ids = []

    # US15.2: a freed slot may resolve a flagged clash at its venue.
    for venue_id in sorted({booking.venue_id for booking in bookings}):
        conflict_flags.resolve_quietly(venue_id)

    notify_event_cancelled(
        event,
        actor_id=actor.id,
        actor_name=actor.name,
        reason=reason,
        venue_names=[booking.venue_name or "a venue" for booking in bookings],
        equipment=lines,
        attendee_ids=attendee_ids,
    )
