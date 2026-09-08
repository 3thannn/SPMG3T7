"""Event routes — US4.1 (see your events and their status) and US4.2 (draft and submit).

These are the endpoints the frontend's event store used to fake in localStorage.
Two rules moved with them, and this is now their enforcement point rather than
their second opinion:

* An Organiser sees the events they own; a Coordinator sees every event (US4.1).
* An event goes Draft -> Submitted exactly once, by the Organiser who owns it,
  and the change is timestamped and attributable (US4.2).

The client still checks both so it can disable a button and explain why. That
stays a courtesy. A browser store was trivially editable and a request is not,
which is the whole reason this file exists.

Ids go out as strings for the same reason they do in `auth.Identity`: the client
only ever compares them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app import event_store
from app.auth import CurrentUser, ErrorCode, require_any_permission, require_permission
from app.event_status import EventStatus, check_submit, refusal_message
from app.event_store import Event
from app.permissions import Permission, has_permission
from app.users import User

router = APIRouter(prefix="/events", tags=["events"])

READ_ANY = (Permission.EVENTS_READ_OWN, Permission.EVENTS_READ_ALL)


class EventError:
    NOT_FOUND = "event_not_found"
    INVALID = "invalid_event"
    REFUSED = "rule_refused"


class StatusChangeOut(BaseModel):
    """One audit entry. `from` is null on the entry that records creation."""

    from_status: EventStatus | None = Field(serialization_alias="from")
    to: EventStatus
    at: str
    by_id: str = Field(serialization_alias="byId")
    by_name: str = Field(serialization_alias="byName")


class EventOut(BaseModel):
    id: str
    title: str
    description: str
    starts_at: str = Field(serialization_alias="startsAt")
    status: EventStatus
    organiser_id: str = Field(serialization_alias="organiserId")
    organiser_name: str = Field(serialization_alias="organiserName")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")
    history: list[StatusChangeOut]


class EventDraft(BaseModel):
    """What the client sends to create or save an event.

    `startsAt` is required and must be non-empty: `events.proposed_date` is NOT
    NULL, so an event with no date is not a thing the database can hold. The
    form asks for one up front rather than accepting a draft it cannot store.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: str = ""
    starts_at: str = Field(alias="startsAt")


def _to_out(event: Event) -> EventOut:
    return EventOut(
        id=str(event.id),
        title=event.title,
        description=event.description,
        starts_at=event.starts_at,
        status=event.status,
        organiser_id=str(event.organiser_id),
        organiser_name=event.organiser_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        history=[
            StatusChangeOut(
                from_status=change.from_status,
                to=change.to_status,
                at=change.at,
                by_id=str(change.by_id),
                by_name=change.by_name,
            )
            for change in event.history
        ],
    )


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": EventError.INVALID, "message": message},
    )


def _not_found() -> HTTPException:
    """The same answer whether the event is missing or simply not the caller's.

    Telling someone an event exists but is not theirs is telling them something
    about another Organiser's work that they had no way to know.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": EventError.NOT_FOUND, "message": "That event no longer exists."},
    )


def _validated(draft: EventDraft) -> EventDraft:
    title = draft.title.strip()
    starts_at = draft.starts_at.strip()
    if not title:
        raise _invalid("Give the event a title.")
    if not starts_at:
        raise _invalid("Give the event a date.")
    return EventDraft(
        title=title, description=draft.description.strip(), starts_at=starts_at
    )


def _readable(event_id: int, user: User) -> Event:
    """Fetch an event the caller is allowed to see, or 404."""
    event = event_store.repository().get_event(event_id)
    if event is None:
        raise _not_found()
    sees_all = has_permission(user.role, Permission.EVENTS_READ_ALL)
    if not sees_all and event.organiser_id != user.id:
        raise _not_found()
    return event


def _as_id(raw: str) -> int:
    """Ids are strings on the wire and integers in the table."""
    try:
        return int(raw)
    except ValueError:
        raise _not_found() from None


@router.get("", response_model=list[EventOut])
def list_events(
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> list[EventOut]:
    """US4.1: an Organiser sees their own events, a Coordinator sees every one."""
    organiser_id = (
        None if has_permission(user.role, Permission.EVENTS_READ_ALL) else user.id
    )
    return [_to_out(event) for event in event_store.repository().list_events(organiser_id)]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: str,
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> EventOut:
    return _to_out(_readable(_as_id(event_id), user))


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    draft: EventDraft,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_CREATE))],
) -> EventOut:
    """US4.2: a new event always begins as a Draft."""
    clean = _validated(draft)
    created = event_store.repository().create_event(
        title=clean.title,
        description=clean.description,
        starts_at=clean.starts_at,
        organiser_id=user.id,
    )
    return _to_out(created)


@router.put("/{event_id}", response_model=EventOut)
def save_event(event_id: str, draft: EventDraft, user: CurrentUser) -> EventOut:
    """US4.2: saving edits content and never moves the status.

    No history entry is written, because a save is not a status change.
    """
    event = _readable(_as_id(event_id), user)
    if event.organiser_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ErrorCode.FORBIDDEN,
                "message": "Only the Organiser who owns this event can edit it.",
            },
        )
    clean = _validated(draft)
    saved = event_store.repository().save_event(
        event.id,
        title=clean.title,
        description=clean.description,
        starts_at=clean.starts_at,
    )
    return _to_out(saved)


@router.post("/{event_id}/submit", response_model=EventOut)
def submit_event(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_SUBMIT))],
) -> EventOut:
    """US4.2: Draft -> Submitted, once, timestamped and attributable.

    A second submit is refused with the reason, not silently ignored.
    """
    event = _readable(_as_id(event_id), user)
    refusal = check_submit(
        status=event.status, organiser_id=event.organiser_id, actor_id=user.id
    )
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": EventError.REFUSED,
                "message": refusal_message(refusal),
                "reason": str(refusal),
            },
        )
    submitted = event_store.repository().submit_event(
        event.id, actor_id=user.id, from_status=event.status
    )
    return _to_out(submitted)
