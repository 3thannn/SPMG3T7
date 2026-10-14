"""Shared notification routes for US10.1 and US19.

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
"""

import logging
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


def notify_equipment_request(event: Event, request: EquipmentRequest) -> None:
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
                event_id=event.id,
                request_id=request.id,
                message=(
                    f'New {request.equipment_type} request for "{event.title}" '
                    f"({request.quantity} needed)."
                ),
            )
        except Exception:
            logger.exception(
                "Could not write equipment request notification %s for user %s",
                request.id,
                recipient.id,
            )


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
