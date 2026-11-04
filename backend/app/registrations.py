"""Registration routes — US20.1: an Attendee registers for a Confirmed event.

Two halves, held by different roles:

* The assigned Coordinator turns registration on for an event and sets its
  capacity, a whole number of at least 1 that starts from the event's expected
  attendance (`PUT /events/{id}/registration`). Anyone who can open the event
  can read the settings and how many places are taken.
* An Attendee sees the Confirmed events taking registrations - the name, when,
  the venues and the places left, and nothing of the planning behind them - and
  registers with a name and an email (`/attendee/events`).

The two rules that must hold when people act at once, one active registration
per Attendee per event and never more than the capacity, are enforced by the
database (`app.registration_store`). This module checks first only so a refusal
comes back as a sentence, and turns what the store answered into the same
sentences.

When a registration takes the last place, the Coordinator and the Organiser are
told (US10.2). Best effort: the registration has already happened.

US20.2 adds the Attendee's own list (`/attendee/registrations`): each event they
registered for, with its current date, time and venues, the registration's
status, and whether they can still withdraw or register again. Withdrawing is
allowed until the event starts and gives the place back; registering again is
US20.1's route, because a withdrawn registration no longer takes a place.

US20.3 lets the owning Organiser and the assigned Coordinator see who registered
(`GET /events/{id}/registrations`): each person's name, email, when they
registered and their status, with the count against the capacity. Nobody else
sees the names, Attendees included.
"""

import logging
import re
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import booking_store, event_store, registration_store
from app.auth import require_any_permission, require_permission
from app.booking_store import BookingStatus, local_now
from app.event_status import EventStatus
from app.event_store import Event
from app.events import (
    READ_ANY,
    EventError,
    _as_id,
    _readable,
    _refuse_if_cancelled,
    _stale_request,
)
from app.notifications import notify_event_full
from app.permissions import Permission
from app.registration_store import (
    SETTABLE,
    BelowRegistered,
    OpenEvent,
    RegisterOutcome,
    Registration,
    RegistrationSettings,
    RegistrationStatus,
    StaleRegistrationSettings,
    WithdrawOutcome,
    withdrawal_refusal,
)
from app.users import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["registrations"])

#: `events.registration_capacity` is INTEGER.
CAPACITY_MAX = 2_147_483_647
#: `registrations.name` and `registrations.email` are VARCHAR(255).
NAME_MAX = 255
EMAIL_MAX = 255
#: Something, an @, and something with a dot in it. Not the full RFC: it catches
#: a typo or a missing @, and the address is shown to people, never mailed.
EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EVENT_FULL_MESSAGE = "Event is full."
ALREADY_REGISTERED_MESSAGE = "You are already registered for this event."
NOT_OPEN_MESSAGE = "That event is not open for registration."


class RegistrationError:
    NOT_OPEN = "event_not_open"
    INVALID = "invalid_registration"


class SettingsRefusal(StrEnum):
    """Why an event's registration settings cannot be changed now."""

    NOT_APPROVED = "not-approved"
    EVENT_CLOSED = "event-closed"


SETTINGS_REFUSAL_MESSAGES: dict[SettingsRefusal, str] = {
    SettingsRefusal.NOT_APPROVED: "Approve this event before opening registration.",
    SettingsRefusal.EVENT_CLOSED: (
        "This event is closed, so its registration can no longer change."
    ),
}


def check_settings(*, status: EventStatus) -> SettingsRefusal | None:
    """US20.1: may this event's registration be turned on or changed now?

    From approval until the event is over: Approved, Planning, Pending Safety
    Check and Confirmed. Before that the event may still be turned down, and
    after it there is nothing left to register for. Attendees see it only once
    it is Confirmed, so a Coordinator can open registration ahead of that.
    Whether it is this Coordinator's event is the route's readable check.
    """
    if status in SETTABLE:
        return None
    if status in (EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW):
        return SettingsRefusal.NOT_APPROVED
    return SettingsRefusal.EVENT_CLOSED


def settings_refusal_message(reason: SettingsRefusal) -> str:
    return SETTINGS_REFUSAL_MESSAGES[reason]


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": RegistrationError.INVALID, "message": message},
    )


def _refused(reason: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": EventError.REFUSED, "message": message, "reason": reason},
    )


# -- The Coordinator's half: settings ------------------------------------------


class RegistrationSettingsOut(BaseModel):
    event_id: str = Field(serialization_alias="eventId")
    open: bool
    #: None until one was first set.
    capacity: int | None
    #: Places taken.
    registered: int
    places_left: int | None = Field(serialization_alias="placesLeft")
    #: Where the capacity starts before one is set: the expected attendance.
    default_capacity: int | None = Field(serialization_alias="defaultCapacity")


class RegistrationSettingsIn(BaseModel):
    """Turn registration on or off. Without a capacity, the stored one is kept,
    or, the first time it is turned on, the expected attendance is used.

    The capacity is typed loosely so a value that is not a whole number is
    refused with a sentence rather than a validation error.
    """

    open: bool
    capacity: bool | int | float | str | None = None


def _capacity(raw: bool | int | float | str | None) -> int | None:
    """A whole number of places, at least 1, or None when none was given."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    value: int | None = None
    if isinstance(raw, bool):
        value = None
    elif isinstance(raw, int):
        value = raw
    elif isinstance(raw, float) and raw.is_integer():
        value = int(raw)
    elif isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
    if value is None or value < 1:
        raise _invalid("Give the capacity as a whole number of places, at least 1.")
    if value > CAPACITY_MAX:
        raise _invalid("That capacity is larger than this system can hold.")
    return value


def _settings_out(settings: RegistrationSettings, event: Event) -> RegistrationSettingsOut:
    return RegistrationSettingsOut(
        event_id=str(settings.event_id),
        open=settings.is_open,
        capacity=settings.capacity,
        registered=settings.registered,
        places_left=settings.places_left,
        default_capacity=event.expected_attendance or None,
    )


def _below_registered(registered: int) -> HTTPException:
    """Always plural: a capacity is at least 1, so it is only ever below two or more."""
    return _refused(
        "below-registered",
        f"{registered} people have already registered, "
        f"so the capacity cannot be less than {registered}.",
    )


@router.get("/events/{event_id}/registration", response_model=RegistrationSettingsOut)
def get_registration_settings(
    event_id: str,
    user: Annotated[User, Depends(require_any_permission(*READ_ANY))],
) -> RegistrationSettingsOut:
    """Whether the event takes registrations, its capacity and the places taken.

    For anyone who can open the event: its Organiser, its assigned Coordinator
    and the Coordinator Lead. Everyone else gets the event's own 404.
    """
    event = _readable(_as_id(event_id), user)
    return _settings_out(registration_store.repository().settings_for(event.id), event)


@router.put("/events/{event_id}/registration", response_model=RegistrationSettingsOut)
def save_registration_settings(
    event_id: str,
    payload: RegistrationSettingsIn,
    user: Annotated[User, Depends(require_permission(Permission.REGISTRATION_MANAGE))],
) -> RegistrationSettingsOut:
    """US20.1 AC1: the assigned Coordinator turns registration on or off.

    D3: so can the owning Organiser (Week 4 answers: the Organiser controls
    timing and closing). The permission admits the role and `_readable` the
    ownership or assignment, answering 404 for anyone else. Then 409 for a status
    that takes no settings, then 400 for the capacity. The capacity may not go
    below the places already taken; the database re-checks that under the lock
    registrations take, so one arriving meanwhile is counted.
    """
    event = _readable(_as_id(event_id), user)
    _refuse_if_cancelled(event)
    refusal = check_settings(status=event.status)
    if refusal is not None:
        raise _refused(str(refusal), settings_refusal_message(refusal))
    capacity = _capacity(payload.capacity)

    store = registration_store.repository()
    if payload.open and capacity is None:
        stored = store.settings_for(event.id).capacity
        capacity = stored if stored is not None else (event.expected_attendance or None)
        if capacity is None:
            raise _invalid("Give a capacity: this event has no expected attendance to start from.")
    try:
        saved = store.set_settings(
            event.id, actor_id=user.id, is_open=payload.open, capacity=capacity
        )
    except BelowRegistered as error:
        raise _below_registered(error.registered) from None
    except StaleRegistrationSettings:
        raise _stale_request() from None
    return _settings_out(saved, event)


# -- The Attendee's half: open events and registering ---------------------------


class OpenEventOut(BaseModel):
    """What an Attendee is shown. Nothing of the planning: no bookings, equipment,
    notes, history or people."""

    id: str
    title: str
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    #: The venues of its Confirmed bookings, in time order.
    venues: list[str]
    places_left: int = Field(serialization_alias="placesLeft")
    #: The caller already has a place here, so no second one is offered.
    registered: bool


class RegistrationIn(BaseModel):
    name: str = ""
    email: str = ""


class RegistrationOut(BaseModel):
    id: str
    event_id: str = Field(serialization_alias="eventId")
    name: str
    email: str
    status: str
    created_at: str = Field(serialization_alias="createdAt")


Attendee = Annotated[User, Depends(require_permission(Permission.REGISTRATIONS_CREATE))]


def _not_open() -> HTTPException:
    """The same answer for a missing event, one that is not Confirmed, and one
    not taking registrations: none of them is the Attendee's to know about."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": RegistrationError.NOT_OPEN, "message": NOT_OPEN_MESSAGE},
    )


def _open_id(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise _not_open() from None


def _venues(event_id: int) -> list[str]:
    """A Confirmed event's venues are its Confirmed bookings (US4.4 makes them so)."""
    names = [
        booking.venue_name or "Venue to be announced"
        for booking in booking_store.repository().list_for_event(event_id)
        if booking.status is BookingStatus.CONFIRMED
    ]
    return list(dict.fromkeys(names))


def _open_out(item: OpenEvent, mine: frozenset[int]) -> OpenEventOut:
    return OpenEventOut(
        id=str(item.event_id),
        title=item.title,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        venues=_venues(item.event_id),
        places_left=item.places_left,
        registered=item.event_id in mine,
    )


def _registration_out(registration: Registration) -> RegistrationOut:
    return RegistrationOut(
        id=str(registration.id),
        event_id=str(registration.event_id),
        name=registration.name,
        email=registration.email,
        status=str(registration.status),
        created_at=registration.created_at,
    )


def _validated(payload: RegistrationIn) -> tuple[str, str]:
    """US20.1 AC3: a name and an email, both required. One problem at a time."""
    name = payload.name.strip()
    email = payload.email.strip()
    if not name:
        raise _invalid("Give your name.")
    if len(name) > NAME_MAX:
        raise _invalid(f"Keep your name to {NAME_MAX} characters or fewer.")
    if not email:
        raise _invalid("Give your email address.")
    if len(email) > EMAIL_MAX:
        raise _invalid(f"Keep your email address to {EMAIL_MAX} characters or fewer.")
    if not EMAIL_SHAPE.match(email):
        raise _invalid("Give a valid email address, such as name@example.com.")
    return name, email


def _tell_full(event_id: int) -> None:
    """US20.1 AC5, best effort: the registration that filled the event is stored."""
    try:
        event = event_store.repository().get_event(event_id)
        capacity = registration_store.repository().settings_for(event_id).capacity
    except Exception:
        logger.exception("Could not read event %s to say it is full", event_id)
        return
    if event is not None and capacity is not None:
        notify_event_full(event, capacity)


@router.get("/attendee/events", response_model=list[OpenEventOut])
def list_open_events(user: Attendee) -> list[OpenEventOut]:
    """US20.1 AC2: Confirmed events taking registrations, soonest first."""
    store = registration_store.repository()
    mine = store.registered_event_ids(user.id)
    return [_open_out(item, mine) for item in store.list_open()]


@router.get("/attendee/events/{event_id}", response_model=OpenEventOut)
def get_open_event(event_id: str, user: Attendee) -> OpenEventOut:
    store = registration_store.repository()
    item = store.get_open(_open_id(event_id))
    if item is None:
        raise _not_open()
    return _open_out(item, store.registered_event_ids(user.id))


@router.post(
    "/attendee/events/{event_id}/registrations",
    response_model=RegistrationOut,
    status_code=status.HTTP_201_CREATED,
)
def register(event_id: str, payload: RegistrationIn, user: Attendee) -> RegistrationOut:
    """US20.1 AC3 and AC4: register, once, while there are places.

    404 for an event the Attendee cannot see, then 400 for the name and email,
    then whatever the store answered: 409 when already registered or full, or
    404 if registration closed meanwhile.
    """
    numeric_id = _open_id(event_id)
    store = registration_store.repository()
    if store.get_open(numeric_id) is None:
        raise _not_open()
    name, email = _validated(payload)

    result = store.register(numeric_id, attendee_id=user.id, name=name, email=email)
    if result.outcome is RegisterOutcome.CLOSED:
        raise _not_open()
    if result.outcome is RegisterOutcome.ALREADY_REGISTERED:
        raise _refused(str(result.outcome), ALREADY_REGISTERED_MESSAGE)
    if result.outcome is RegisterOutcome.FULL:
        raise _refused("event-full", EVENT_FULL_MESSAGE)
    assert result.registration is not None  # noqa: S101 - REGISTERED carries it
    if result.became_full:
        _tell_full(numeric_id)
    return _registration_out(result.registration)


# -- US20.2: the Attendee's own registrations, and withdrawing ------------------

REGISTRATION_NOT_FOUND_MESSAGE = "That registration no longer exists."

WITHDRAW_REFUSALS: dict[WithdrawOutcome, tuple[str, str]] = {
    WithdrawOutcome.ALREADY_WITHDRAWN: (
        "already-withdrawn",
        "You have already withdrawn from this event.",
    ),
    WithdrawOutcome.STARTED: (
        "event-started",
        "This event has already started, so you can no longer withdraw.",
    ),
    WithdrawOutcome.CLOSED: (
        "event-closed",
        "This event is over or no longer going ahead, so there is nothing to withdraw from.",
    ),
}


class MyRegistrationOut(BaseModel):
    """One event the Attendee registered for, as it stands now (US20.2 AC1)."""

    id: str
    event_id: str = Field(serialization_alias="eventId")
    #: The event's current details, read now rather than when they registered.
    title: str
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    venues: list[str]
    #: Registered or Withdrawn.
    status: str
    name: str
    email: str
    registered_at: str = Field(serialization_alias="registeredAt")
    #: Empty unless Withdrawn.
    withdrawn_at: str = Field(serialization_alias="withdrawnAt")
    can_withdraw: bool = Field(serialization_alias="canWithdraw")
    #: Withdrawn, and the event still takes registrations and has a place.
    can_register_again: bool = Field(serialization_alias="canRegisterAgain")
    #: Null when the event is not taking registrations.
    places_left: int | None = Field(serialization_alias="placesLeft")


def _my_out(registration: Registration, open_event: OpenEvent | None) -> MyRegistrationOut:
    event = registration.event
    places_left = open_event.places_left if open_event is not None else None
    return MyRegistrationOut(
        id=str(registration.id),
        event_id=str(registration.event_id),
        title=event.title if event else "",
        starts_at=event.starts_at if event else "",
        ends_at=event.ends_at if event else "",
        venues=_venues(registration.event_id),
        status=str(registration.status),
        name=registration.name,
        email=registration.email,
        registered_at=registration.created_at,
        withdrawn_at=registration.withdrawn_at,
        can_withdraw=withdrawal_refusal(registration, event, local_now()) is None,
        can_register_again=(
            registration.status is RegistrationStatus.WITHDRAWN and bool(places_left)
        ),
        places_left=places_left,
    )


def _newest_by(
    registrations: list[Registration], key: Callable[[Registration], int]
) -> list[Registration]:
    """One registration per key (an event, or an Attendee): the newest.

    Someone who withdrew and registered again has two rows for the event; the
    newer one is where they stand now. The older stays in the table as history.
    """
    latest: dict[int, Registration] = {}
    for item in sorted(registrations, key=lambda item: item.id, reverse=True):
        latest.setdefault(key(item), item)
    return list(latest.values())


@router.get("/attendee/registrations", response_model=list[MyRegistrationOut])
def list_my_registrations(user: Attendee) -> list[MyRegistrationOut]:
    """US20.2 AC1: the Attendee's registrations, soonest event first."""
    store = registration_store.repository()
    latest = _newest_by(store.list_for_attendee(user.id), key=lambda item: item.event_id)
    open_events = {item.event_id: item for item in store.list_open()}
    ordered = sorted(
        latest,
        key=lambda item: ((item.event.starts_at if item.event else "") or "9999", item.id),
    )
    return [_my_out(item, open_events.get(item.event_id)) for item in ordered]


def _registration_not_found() -> HTTPException:
    """The same answer for a missing registration and someone else's."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "registration_not_found", "message": REGISTRATION_NOT_FOUND_MESSAGE},
    )


@router.post(
    "/attendee/registrations/{registration_id}/withdraw", response_model=MyRegistrationOut
)
def withdraw(registration_id: str, user: Attendee) -> MyRegistrationOut:
    """US20.2 AC2: give the place back, before the event starts.

    404 for a registration that is not the caller's, then 409 when it is
    already withdrawn, the event has started, or it is no longer Confirmed. The
    database decides under the event's lock, so a registration for the freed
    place waits for the withdrawal and then finds the place.
    """
    try:
        numeric_id = int(registration_id)
    except ValueError:
        raise _registration_not_found() from None
    store = registration_store.repository()
    result = store.withdraw(numeric_id, attendee_id=user.id)
    if result.outcome is WithdrawOutcome.NOT_FOUND:
        raise _registration_not_found()
    if result.outcome in WITHDRAW_REFUSALS:
        reason, message = WITHDRAW_REFUSALS[result.outcome]
        raise _refused(reason, message)
    assert result.registration is not None  # noqa: S101 - WITHDRAWN carries it
    return _my_out(result.registration, store.get_open(result.registration.event_id))


# -- US20.3: who registered, for the Organiser and the Coordinator --------------


class RegistrantOut(BaseModel):
    """One person on an event's registration list."""

    id: str
    name: str
    email: str
    #: Registered or Withdrawn.
    status: str
    #: Recorded times: naive UTC.
    registered_at: str = Field(serialization_alias="registeredAt")
    withdrawn_at: str = Field(serialization_alias="withdrawnAt")


class EventRegistrationsOut(BaseModel):
    """US20.3 AC1: the list, and the count against the capacity."""

    event_id: str = Field(serialization_alias="eventId")
    open: bool
    capacity: int | None
    #: Places taken: Registered only.
    registered: int
    places_left: int | None = Field(serialization_alias="placesLeft")
    registrations: list[RegistrantOut]


@router.get("/events/{event_id}/registrations", response_model=EventRegistrationsOut)
def list_event_registrations(
    event_id: str,
    user: Annotated[User, Depends(require_permission(Permission.REGISTRATIONS_READ))],
) -> EventRegistrationsOut:
    """US20.3: who registered, for the owning Organiser and the assigned Coordinator.

    The permission admits the two roles (and not the Lead, the Safety Officer,
    Venue Staff, Tech Support or an Attendee: 403). `_readable` then admits
    only the Organiser's own events and the Coordinator's assigned ones,
    answering 404 for any other, as US3.1 and US8.6 do for the event itself.

    One entry per person, their newest registration, ordered by when it was
    made (the time shown): someone who withdrew and registered again is listed
    once, as Registered, at the time they registered again.
    """
    event = _readable(_as_id(event_id), user)
    store = registration_store.repository()
    settings = store.settings_for(event.id)
    people = sorted(
        _newest_by(store.list_for_event(event.id), key=lambda item: item.attendee_id),
        key=lambda item: item.id,
    )
    return EventRegistrationsOut(
        event_id=str(event.id),
        open=settings.is_open,
        capacity=settings.capacity,
        registered=settings.registered,
        places_left=settings.places_left,
        registrations=[
            RegistrantOut(
                id=str(item.id),
                name=item.name,
                email=item.email,
                status=str(item.status),
                registered_at=item.created_at,
                withdrawn_at=item.withdrawn_at,
            )
            for item in people
        ],
    )
