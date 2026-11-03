"""US8.4: the Coordinator Lead moves an assigned event to a different Coordinator.

The move itself is `reassign_event_coordinator`
(SUPABASE_US8_4_REASSIGN_COORDINATOR.sql), in one transaction: it changes the
Coordinator, logs it in the event's history and notifies both Coordinators
(US10.2). This module holds the rules the route and the history read.

* Only an active event: Completed, Cancelled and Rejected ones are finished.
* The log is a status_changes row whose status does not change, carrying who
  did it (the Lead), when, and a note naming the previous Coordinator. Like
  the other kinds of note, it is recognised rather than stored: no other entry
  keeps its status with a note that starts this way.
"""

from app.event_status import CLOSED, EventStatus

#: How the history labels a reassignment's note.
KIND_REASSIGNMENT = "reassignment"
NOTE_PREFIX = "Coordinator reassigned from "


def note(previous: str, new: str) -> str:
    """ "Coordinator reassigned from Priya to Alex." The SQL writes the same words."""
    return f"{NOTE_PREFIX}{previous} to {new}."


def history_kind(*, from_status: EventStatus | None, to_status: EventStatus, notes: str) -> str:
    if from_status is to_status and notes.startswith(NOTE_PREFIX):
        return KIND_REASSIGNMENT
    return ""


def closed_message(status: EventStatus) -> str | None:
    """Why a finished event cannot be reassigned, or None while it is active."""
    if status in CLOSED:
        return f"This event is {status}, so it can no longer be reassigned."
    return None
