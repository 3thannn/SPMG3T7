"""Shared notification routes for US10.1, US10.2 and US19.

An Organiser is told when one of their events moves to Under Review (a Lead
assigning a Coordinator, or a Coordinator asking a question), Approved or
Rejected, and can mark each notice read or unread so the
list stays manageable. There is no email or push yet; the list is the delivery.

`notify_status_change` is the write side, called by the event routes after a
transition has been stored. It never fails the request that called it: the
status change is the thing the Coordinator asked for and it has already
happened, so a notice that could not be written is logged rather than turned
into an error for a decision that in fact succeeded. US19 applies the same
best-effort rule after an equipment request is stored.

US10.2 tells the Coordinator an event is assigned to about the things that
need their attention: being assigned or unassigned, a tentative hold running
out, a booking hit by venue unavailability or a setup change, and the Safety
Officer asking for changes (US17.2, which also tells them about a rejection).
Each `notify_*` function is called once the change it describes has been
stored. Same best-effort rule. US14.4's
two hold notices are written by the database's scheduled sweep instead, in the
words `notify_hold_expiring` and `notify_hold_expired` set out.

US20.1 adds one more of the same kind of notice, for the Organiser as well as
the Coordinator: the event's registrations have reached capacity.
"""

import logging
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import notification_store, users
from app.auth import require_permission
from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus
from app.event_store import Event
from app.notification_store import Notification
from app.permissions import Permission, Role
from app.users import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

#: The transitions that notify the Organiser, per the US10.1 acceptance
#: criteria. Draft -> Submitted is the Organiser's own action and does not.
NOTIFYING_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.UNDER_REVIEW, EventStatus.APPROVED, EventStatus.REJECTED}
)


def message_for(event: Event, to_status: EventStatus, notes: str = "") -> str:
    """What the Organiser reads. The Coordinator's own words travel with it."""
    title = event.title.strip() or "Your event"
    if to_status is EventStatus.APPROVED:
        return f'"{title}" was approved.'
    if to_status is EventStatus.REJECTED:
        return f'"{title}" was rejected. Reason: {notes}' if notes else f'"{title}" was rejected.'
    if notes:
        return f'A Coordinator asked for more information about "{title}": {notes}'
    return f'"{title}" is under review.'


def notify_status_change(event: Event, to_status: EventStatus, notes: str = "") -> None:
    """Write a notice for the event's Organiser, if this status calls for one."""
    if to_status not in NOTIFYING_STATUSES:
        return
    try:
        notification_store.repository().create(
            user_id=event.organiser_id,
            event_id=event.id,
            status=to_status,
            message=message_for(event, to_status, notes),
        )
    except Exception:
        logger.exception(
            "Could not write the US10.1 notification for event %s -> %s", event.id, to_status
        )


def notify_change_decision(event: Event, *, approved: bool, reason: str = "") -> None:
    """Notify the owner without pretending the event itself changed status."""
    outcome = "accepted" if approved else "rejected"
    message = f'The change request for "{event.title}" was {outcome}.'
    if reason:
        message += f" Reason: {reason}"
    try:
        notification_store.repository().create_notice(
            user_id=event.organiser_id,
            event_id=event.id,
            kind="change-accepted" if approved else "change-rejected",
            message=message,
        )
    except Exception:
        logger.exception("Could not notify change decision for event %s", event.id)


def _notify_equipment(request: EquipmentRequest, message: str) -> None:
    """One best-effort notice per active Tech Support profile."""
    try:
        recipients = users.list_users()
    except Exception:
        logger.exception(
            "Could not look up equipment request notification recipients for %s", request.id
        )
        return
    for recipient in recipients:
        if recipient.role is not Role.TECH_SUPPORT:
            continue
        try:
            notification_store.repository().create_equipment(
                user_id=recipient.id,
                event_id=request.event_id,
                request_id=request.id,
                message=message,
            )
        except Exception:
            logger.exception(
                "Could not write equipment request notification %s for user %s",
                request.id,
                recipient.id,
            )


def _listed(items: list[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _notify_cancelled(user_id: int, event: Event, message: str) -> None:
    try:
        notification_store.repository().create(
            user_id=user_id, event_id=event.id, status=EventStatus.CANCELLED, message=message
        )
    except Exception:
        logger.exception(
            "Could not write the US4.6 cancellation notice for event %s to user %s",
            event.id,
            user_id,
        )


def notify_event_cancelled(
    event: Event,
    *,
    actor_id: int,
    actor_name: str,
    reason: str,
    venue_names: list[str],
    equipment: list[EquipmentRequest],
    attendee_ids: list[int] | None = None,
) -> None:
    """US4.6: tell everyone a cancellation affects. Not the person who cancelled.

    The Organiser and the assigned Coordinator are told who cancelled and why.
    Venue Staff are told when bookings were released and Tech Support when
    equipment was; there is no per-venue or per-item owner, so, as for new
    equipment requests, every member of the role hears. Each Attendee whose
    registration the cancellation ended is told too, without the reason: it is
    written for the people planning the event, and US20.1 keeps internal
    planning from Attendees. Each notice is a status notice (Cancelled), written
    best effort: the cancellation already happened.
    """
    title = event.title.strip()
    subject = f'"{title}"' if title else "An untitled event"
    because = f" Reason: {reason}"

    for person in dict.fromkeys((event.organiser_id, event.coordinator_id)):
        if person is not None and person != actor_id:
            _notify_cancelled(person, event, f"{subject} was cancelled by {actor_name}.{because}")

    for attendee in dict.fromkeys(attendee_ids or ()):
        if attendee != actor_id:
            _notify_cancelled(
                attendee,
                event,
                f"{subject} has been cancelled, so your registration for it is cancelled too.",
            )

    if not venue_names and not equipment:
        return
    try:
        recipients = users.list_users()
    except Exception:
        logger.exception("Could not look up the US4.6 notice recipients for event %s", event.id)
        return

    def tell(role: Role, message: str) -> None:
        for recipient in recipients:
            if recipient.role is role and recipient.id != actor_id:
                _notify_cancelled(recipient.id, event, message)

    if venue_names:
        venues = _listed(list(dict.fromkeys(venue_names)))
        released = "booking was" if len(venue_names) == 1 else "bookings were"
        tell(
            Role.VENUE_STAFF,
            f"{subject} was cancelled, so its {released} released: {venues}.{because}",
        )

    if equipment:
        lines = _listed([f"{line.quantity} × {line.equipment_type}" for line in equipment])
        released = "request was" if len(equipment) == 1 else "requests were"
        tell(
            Role.TECH_SUPPORT,
            f"{subject} was cancelled, so its equipment {released} released: {lines}.{because}",
        )


def notify_equipment_request(event: Event, request: EquipmentRequest) -> None:
    _notify_equipment(
        request,
        f'New {request.equipment_type} request for "{event.title}" ({request.quantity} needed).',
    )


def notify_equipment_change(request: EquipmentRequest, actor_name: str, action: str) -> None:
    """A Coordinator edit or removal is a fresh unread notice for Tech Support."""
    title = request.event_title or f"event {request.event_id}"
    _notify_equipment(
        request,
        f'Coordinator {actor_name} {action} the {request.equipment_type} request for "{title}".',
    )


class CoordinatorNotice(StrEnum):
    """US10.2: the `kind` of a Coordinator notice, one per acceptance criterion."""

    CHANGE_SUBMITTED = "change-submitted"
    ARRANGEMENT_CONFLICT = "arrangement-conflict"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    HOLD_EXPIRING = "hold-expiring"
    HOLD_EXPIRED = "hold-expired"
    BOOKING_CONFLICT = "booking-conflict"
    SAFETY_CHANGES = "safety-changes"
    #: US17.2: the Safety Officer rejected the safety check. Not one of US10.2's
    #: four, but the event lands back on the Coordinator's desk either way.
    SAFETY_REJECTED = "safety-rejected"
    #: US16.1: Venue Staff decided one of the event's booking requests.
    BOOKING_CONFIRMED = "booking-confirmed"
    BOOKING_REJECTED = "booking-rejected"
    #: US20.1: registrations reached capacity. The Organiser is told too.
    EVENT_FULL = "event-full"


def _event_title(event: Event) -> str:
    return event.title.strip() or "an untitled event"


def _notify_coordinator(
    coordinator_id: int | None, event: Event, kind: CoordinatorNotice, message: str
) -> None:
    """Write one notice for a Coordinator. Nobody to tell is not an error."""
    if coordinator_id is None:
        return
    try:
        notification_store.repository().create_notice(
            user_id=coordinator_id, event_id=event.id, kind=str(kind), message=message
        )
    except Exception:
        logger.exception(
            "Could not write the US10.2 %s notification for event %s to user %s",
            kind,
            event.id,
            coordinator_id,
        )


def notify_assigned(event: Event, coordinator_id: int | None = None) -> None:
    """US8.3/US8.4: tell a Coordinator an event is now theirs.

    Defaults to the event's current Coordinator, which is who an assignment just
    stored.
    """
    recipient = coordinator_id if coordinator_id is not None else event.coordinator_id
    _notify_coordinator(
        recipient,
        event,
        CoordinatorNotice.ASSIGNED,
        f'You were assigned "{_event_title(event)}".',
    )


def notify_unassigned(event: Event, coordinator_id: int) -> None:
    """US8.4: tell the previous Coordinator an event was taken off them."""
    _notify_coordinator(
        coordinator_id,
        event,
        CoordinatorNotice.UNASSIGNED,
        f'"{_event_title(event)}" is no longer assigned to you.',
    )


def notify_reassigned(event: Event, previous_id: int | None, new_id: int | None) -> None:
    """US8.4: both sides of a reassignment, each told only their half."""
    if previous_id == new_id:
        return
    if previous_id is not None:
        notify_unassigned(event, previous_id)
    notify_assigned(event, new_id)


def notify_hold_expiring(event: Event, venue_name: str, expires_at: str) -> None:
    """US14.4: a tentative hold is about to lapse. `expires_at` is shown as given.

    In production the scheduled sweep (`sweep_tentative_holds` in
    SUPABASE_US14_4_HOLD_EXPIRY.sql) writes this notice in SQL, giving the
    expiry as "02 Nov 2027, 09:00". This function is the wording it must match;
    tests/test_hold_expiry_db.py checks the two agree.
    """
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.HOLD_EXPIRING,
        f'The tentative hold on {venue_name} for "{_event_title(event)}" expires {expires_at}.',
    )


def notify_hold_expired(event: Event, venue_name: str) -> None:
    """US14.4: a tentative hold lapsed and the venue is no longer held.

    Written in SQL by the scheduled sweep, in these words; see
    `notify_hold_expiring`.
    """
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.HOLD_EXPIRED,
        f'The tentative hold on {venue_name} for "{_event_title(event)}" has expired.',
    )


def notify_booking_conflict(event: Event, venue_name: str, reason: str) -> None:
    """US12.2/US15.2: a booking is hit by venue unavailability or a setup change."""
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.BOOKING_CONFLICT,
        f'The booking of {venue_name} for "{_event_title(event)}" needs attention: {reason}',
    )


def notify_safety_changes(event: Event, notes: str = "", flagged: int = 0) -> None:
    """US17.2: the Safety Officer asked for changes. Their words travel with it,
    and so does how many arrangements they flagged for re-review."""
    title = _event_title(event)
    message = (
        f'The Safety Officer requested changes to "{title}": {notes}'
        if notes
        else f'The Safety Officer requested changes to "{title}".'
    )
    if flagged:
        noun = "arrangement" if flagged == 1 else "arrangements"
        message += f" {flagged} {noun} flagged for re-review."
    _notify_coordinator(event.coordinator_id, event, CoordinatorNotice.SAFETY_CHANGES, message)


def notify_safety_rejected(event: Event, reason: str) -> None:
    """US17.2: the Safety Officer rejected the safety check, and why."""
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.SAFETY_REJECTED,
        f'The Safety Officer rejected the safety check for "{_event_title(event)}": {reason}',
    )


def notify_booking_decision(
    event: Event,
    venue_name: str,
    *,
    confirmed: bool,
    reason: str = "",
    suggestion: str = "",
) -> None:
    """US16.1: tell the assigned Coordinator Venue Staff decided a booking, and why."""
    title = _event_title(event)
    venue = venue_name or "a venue"
    if confirmed:
        message = f'Venue Staff confirmed {venue} for "{title}".'
    else:
        message = f'Venue Staff rejected {venue} for "{title}". Reason: {reason}'
        if suggestion:
            message += f" Suggested instead: {suggestion}"
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.BOOKING_CONFIRMED if confirmed else CoordinatorNotice.BOOKING_REJECTED,
        message,
    )


def notify_event_full(event: Event, capacity: int) -> None:
    """US20.1: the last place was taken. The assigned Coordinator and the Organiser hear.

    Called once, by the registration that filled the event: the database lets
    only one registration take the last place, so only one call can say so.
    """
    places = "its one place is" if capacity == 1 else f"all {capacity} places are"
    message = f'"{_event_title(event)}" is full: {places} taken.'
    for person in dict.fromkeys((event.coordinator_id, event.organiser_id)):
        _notify_coordinator(person, event, CoordinatorNotice.EVENT_FULL, message)


class NotificationOut(BaseModel):
    id: str
    event_id: str = Field(serialization_alias="eventId")
    event_title: str = Field(serialization_alias="eventTitle")
    status: EventStatus | None
    kind: str = "event-status"
    equipment_request_id: str | None = Field(default=None, serialization_alias="equipmentRequestId")
    message: str
    read: bool
    created_at: str = Field(serialization_alias="createdAt")
    read_at: str = Field(serialization_alias="readAt")


class ReadState(BaseModel):
    read: bool


def _to_out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=str(notification.id),
        event_id=str(notification.event_id),
        event_title=notification.event_title,
        status=notification.status,
        kind=notification.kind,
        equipment_request_id=(
            str(notification.equipment_request_id)
            if notification.equipment_request_id is not None
            else None
        ),
        message=notification.message,
        read=notification.is_read,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def _not_found() -> HTTPException:
    """The same answer whether the notice is missing or someone else's."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "notification_not_found", "message": "That notification no longer exists."},
    )


ReadsNotifications = Annotated[User, Depends(require_permission(Permission.NOTIFICATIONS_READ))]


@router.get("", response_model=list[NotificationOut])
def list_notifications(user: ReadsNotifications) -> list[NotificationOut]:
    """The caller's notices, unread first, newest first within each group."""
    return [_to_out(item) for item in notification_store.repository().list_for_user(user.id)]


@router.patch("/{notification_id}", response_model=NotificationOut)
def set_read_state(
    notification_id: str, payload: ReadState, user: ReadsNotifications
) -> NotificationOut:
    """Mark one notice read or unread. Only its recipient may."""
    try:
        numeric_id = int(notification_id)
    except ValueError:
        raise _not_found() from None
    store = notification_store.repository()
    existing = store.get(numeric_id)
    if existing is None or existing.user_id != user.id:
        raise _not_found()
    return _to_out(store.set_read(numeric_id, is_read=payload.read))


def notify_change_submitted(event: Event) -> None:
    _notify_coordinator(
        event.coordinator_id,
        event,
        CoordinatorNotice.CHANGE_SUBMITTED,
        f'New or revised change request for "{event.title}" needs review.',
    )


def notify_arrangement_conflicts(event: Event, failures: list[str]) -> None:
    if failures:
        _notify_coordinator(
            event.coordinator_id,
            event,
            CoordinatorNotice.ARRANGEMENT_CONFLICT,
            f'Arrangements for "{event.title}" need review: ' + "; ".join(failures),
        )


def notify_clarification(event: Event, message: str) -> None:
    if event.status in (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW):
        notify_status_change(event, EventStatus.UNDER_REVIEW, message)
        return
    try:
        notification_store.repository().create_notice(
            user_id=event.organiser_id,
            event_id=event.id,
            kind="clarification-requested",
            message=f'A Coordinator asked for more information about "{event.title}": {message}',
        )
    except Exception:
        logger.exception("Could not notify clarification for event %s", event.id)
