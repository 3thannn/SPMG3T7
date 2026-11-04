"""Event registration, backed by two `events` columns and the `registrations` table — US20.1.

The assigned Coordinator turns registration on for an event and sets how many
places it has; Attendees then register for it, once it is Confirmed, until the
places run out. This module is only the access. Who may do which, and the
sentences that explain a refusal, are the business of `app.registrations`.

Four choices worth knowing:

* The settings are two columns on `events` (`registration_open`,
  `registration_capacity`), read here rather than through `app.event_store`, so
  an event read elsewhere never depends on them.
* "Active" is status Registered. A Withdrawn registration (US20.2) stays as
  history and no longer takes a place, so registering again is a new row; US4.6
  will add "Event Cancelled" the same way.
* The capacity is enforced in the database. `register_for_event` locks the
  event before it counts, so two Attendees after the last place queue on that
  lock and the second finds the event full; a trigger re-checks any other
  write the same way (SUPABASE_US20_1_REGISTRATION.sql). The in-memory store
  holds one lock for the same reason.
* Registering answers with an outcome rather than an exception. Full, already
  registered and closed are ordinary answers, and the route needs to know
  which one it got.
"""

import threading
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app import event_store, supabase_client
from app.booking_store import local_now
from app.event_status import EventStatus
from app.event_store import _now

EVENTS_TABLE = "events"
TABLE = "registrations"
COLUMNS = "id, event_id, attendee_id, name, email, status, created_at, withdrawn_at"
#: US20.2: an Attendee's own list carries each event's current details with it.
WITH_EVENT_COLUMNS = f"{COLUMNS}, events(name, proposed_date, end_date, status)"
SETTINGS_COLUMNS = "id, registration_open, registration_capacity"
OPEN_EVENT_COLUMNS = "id, name, proposed_date, end_date, registration_capacity"


class RegistrationStatus(StrEnum):
    """Matches the `registration_status` enum in Postgres."""

    REGISTERED = "Registered"
    #: US20.2: given back before the event started. Final for this row.
    WITHDRAWN = "Withdrawn"
    #: US4.6: the event was cancelled while this registration held a place. Final.
    EVENT_CANCELLED = "Event Cancelled"


#: Statuses that take a place.
ACTIVE: frozenset[RegistrationStatus] = frozenset({RegistrationStatus.REGISTERED})


@dataclass(frozen=True)
class RegistrationSettings:
    """Whether an event takes registrations, how many, and how many it has."""

    event_id: int
    is_open: bool
    #: None until a capacity was first set.
    capacity: int | None
    #: Active registrations: places taken.
    registered: int

    @property
    def places_left(self) -> int | None:
        if self.capacity is None:
            return None
        return max(self.capacity - self.registered, 0)


@dataclass(frozen=True)
class OpenEvent:
    """A Confirmed event taking registrations: what an Attendee may know of it.

    Deliberately not an `Event`. Nothing here carries bookings, equipment,
    notes or history, so the Attendee's view cannot leak them by accident.
    """

    event_id: int
    title: str
    starts_at: str
    ends_at: str
    capacity: int
    registered: int

    @property
    def places_left(self) -> int:
        return max(self.capacity - self.registered, 0)


@dataclass(frozen=True)
class RegisteredEvent:
    """US20.2: the event a registration is for, as it stands now."""

    title: str
    starts_at: str
    ends_at: str
    status: EventStatus


@dataclass(frozen=True)
class Registration:
    id: int
    event_id: int
    attendee_id: int
    name: str
    email: str
    status: RegistrationStatus
    #: Naive UTC, as the other recorded times are.
    created_at: str
    #: US20.2: naive UTC. Empty unless Withdrawn.
    withdrawn_at: str = ""
    #: US20.2: filled in by the reads that list or fetch registrations.
    event: RegisteredEvent | None = None


def to_registration(row: dict) -> Registration:
    embedded = row.get("events")
    if isinstance(embedded, list):
        embedded = embedded[0] if embedded else None
    event = None
    if isinstance(embedded, dict):
        event = RegisteredEvent(
            title=embedded.get("name") or "",
            starts_at=str(embedded["proposed_date"]) if embedded.get("proposed_date") else "",
            ends_at=str(embedded["end_date"]) if embedded.get("end_date") else "",
            status=EventStatus(embedded["status"]),
        )
    return Registration(
        id=row["id"],
        event_id=row["event_id"],
        attendee_id=row["attendee_id"],
        name=row["name"],
        email=row["email"],
        status=RegistrationStatus(row["status"]),
        created_at=str(row["created_at"]),
        withdrawn_at=str(row["withdrawn_at"]) if row.get("withdrawn_at") else "",
        event=event,
    )


class WithdrawOutcome(StrEnum):
    """What `withdraw` answered. The values are the database function's."""

    WITHDRAWN = "withdrawn"
    #: No such registration, or not this Attendee's.
    NOT_FOUND = "not-found"
    ALREADY_WITHDRAWN = "already-withdrawn"
    #: The event is no longer Confirmed.
    CLOSED = "closed"
    #: The event has started: too late to give the place back.
    STARTED = "started"


@dataclass(frozen=True)
class WithdrawResult:
    outcome: WithdrawOutcome
    #: Set only when `outcome` is WITHDRAWN.
    registration: Registration | None = None


def withdrawal_refusal(
    registration: Registration, event: RegisteredEvent | None, now: datetime
) -> WithdrawOutcome | None:
    """US20.2: may this registration be withdrawn now? None when it may.

    Before the event starts, while it is Confirmed. `now` and the start are
    naive Singapore local times, as every event time is. The database function
    asks the same three questions in the same order. A registration the event's
    cancellation ended (US4.6) is closed, not "already withdrawn": its Attendee
    did not withdraw it.
    """
    if registration.status is RegistrationStatus.WITHDRAWN:
        return WithdrawOutcome.ALREADY_WITHDRAWN
    if (
        registration.status not in ACTIVE
        or event is None
        or event.status is not EventStatus.CONFIRMED
    ):
        return WithdrawOutcome.CLOSED
    if event.starts_at and datetime.fromisoformat(event.starts_at) <= now:
        return WithdrawOutcome.STARTED
    return None


class RegisterOutcome(StrEnum):
    """What `register` answered. The values are the database function's."""

    REGISTERED = "registered"
    ALREADY_REGISTERED = "already-registered"
    FULL = "full"
    #: No such event, not Confirmed, or registration is off.
    CLOSED = "closed"


@dataclass(frozen=True)
class RegisterResult:
    outcome: RegisterOutcome
    #: Set only when `outcome` is REGISTERED.
    registration: Registration | None = None
    #: This registration took the last place, so someone should be told.
    became_full: bool = False


class BelowRegistered(Exception):
    """The capacity asked for is less than the places already taken."""

    def __init__(self, registered: int) -> None:
        super().__init__(registered)
        self.registered = registered


class StaleRegistrationSettings(Exception):
    """The event changed between the route's checks and the write: no longer
    the actor's, or no longer at a status that takes settings."""


class Repository(Protocol):
    def settings_for(self, event_id: int) -> RegistrationSettings: ...

    def set_settings(
        self, event_id: int, *, actor_id: int, is_open: bool, capacity: int | None
    ) -> RegistrationSettings: ...

    def list_open(self) -> list[OpenEvent]: ...

    def get_open(self, event_id: int) -> OpenEvent | None: ...

    def registered_event_ids(self, attendee_id: int) -> frozenset[int]: ...

    def register(
        self, event_id: int, *, attendee_id: int, name: str, email: str
    ) -> RegisterResult: ...

    def list_for_attendee(self, attendee_id: int) -> list[Registration]: ...

    def list_for_event(self, event_id: int) -> list[Registration]: ...

    def get_registration(self, registration_id: int) -> Registration | None: ...

    def withdraw(self, registration_id: int, *, attendee_id: int) -> WithdrawResult: ...


def _open_event(row: dict, registered: int) -> OpenEvent:
    return OpenEvent(
        event_id=row["id"],
        title=row.get("name") or "",
        starts_at=str(row["proposed_date"]) if row.get("proposed_date") else "",
        ends_at=str(row["end_date"]) if row.get("end_date") else "",
        capacity=row["registration_capacity"],
        registered=registered,
    )


class SupabaseRegistrations:
    """The real store. Every write goes through a database function."""

    def _registered(self, event_id: int) -> int:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select("id")
            .eq("event_id", event_id)
            .eq("status", str(RegistrationStatus.REGISTERED))
            .execute()
        )
        return len(response.data or [])

    def settings_for(self, event_id: int) -> RegistrationSettings:
        response = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .select(SETTINGS_COLUMNS)
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
        row = (response.data or [{}])[0]
        return RegistrationSettings(
            event_id=event_id,
            is_open=bool(row.get("registration_open")),
            capacity=row.get("registration_capacity"),
            registered=self._registered(event_id),
        )

    def set_settings(
        self, event_id: int, *, actor_id: int, is_open: bool, capacity: int | None
    ) -> RegistrationSettings:
        result = supabase_client.admin().rpc(
            "set_event_registration",
            {
                "p_event_id": event_id,
                "p_actor_id": actor_id,
                "p_open": is_open,
                "p_capacity": capacity,
            },
        ).execute()
        answer = result.data if isinstance(result.data, dict) else {}
        outcome = answer.get("outcome")
        if outcome == "below-registered":
            raise BelowRegistered(int(answer.get("registered") or 0))
        if outcome != "saved":
            raise StaleRegistrationSettings(outcome)
        return self.settings_for(event_id)

    def _counts(self, event_ids: list[int]) -> Counter[int]:
        if not event_ids:
            return Counter()
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select("event_id")
            .in_("event_id", event_ids)
            .eq("status", str(RegistrationStatus.REGISTERED))
            .execute()
        )
        return Counter(row["event_id"] for row in response.data or [])

    def _open_query(self):
        return (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .select(OPEN_EVENT_COLUMNS)
            .eq("status", str(EventStatus.CONFIRMED))
            .eq("registration_open", True)
        )

    def list_open(self) -> list[OpenEvent]:
        response = self._open_query().order("proposed_date").order("id").execute()
        rows = response.data or []
        counts = self._counts([row["id"] for row in rows])
        return [_open_event(row, counts[row["id"]]) for row in rows]

    def get_open(self, event_id: int) -> OpenEvent | None:
        response = self._open_query().eq("id", event_id).limit(1).execute()
        rows = response.data or []
        if not rows:
            return None
        return _open_event(rows[0], self._registered(event_id))

    def registered_event_ids(self, attendee_id: int) -> frozenset[int]:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select("event_id")
            .eq("attendee_id", attendee_id)
            .eq("status", str(RegistrationStatus.REGISTERED))
            .execute()
        )
        return frozenset(row["event_id"] for row in response.data or [])

    def register(
        self, event_id: int, *, attendee_id: int, name: str, email: str
    ) -> RegisterResult:
        result = supabase_client.admin().rpc(
            "register_for_event",
            {
                "p_event_id": event_id,
                "p_attendee_id": attendee_id,
                "p_name": name,
                "p_email": email,
            },
        ).execute()
        answer = result.data if isinstance(result.data, dict) else {}
        try:
            outcome = RegisterOutcome(answer.get("outcome"))
        except ValueError:
            # "invalid" and "not-attendee" are refused by the route first, so
            # reaching the database with either is a bug, not an answer.
            raise RuntimeError(f"register_for_event answered {answer!r}") from None
        if outcome is not RegisterOutcome.REGISTERED:
            return RegisterResult(outcome=outcome)
        return RegisterResult(
            outcome=outcome,
            registration=Registration(
                id=answer["id"],
                event_id=event_id,
                attendee_id=attendee_id,
                name=name.strip(),
                email=email.strip(),
                status=RegistrationStatus.REGISTERED,
                created_at=str(answer.get("createdAt") or ""),
            ),
            became_full=bool(answer.get("becameFull")),
        )

    def list_for_attendee(self, attendee_id: int) -> list[Registration]:
        """US20.2: every registration the Attendee has made, newest first."""
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(WITH_EVENT_COLUMNS)
            .eq("attendee_id", attendee_id)
            .order("id", desc=True)
            .execute()
        )
        return [to_registration(row) for row in response.data or []]

    def list_for_event(self, event_id: int) -> list[Registration]:
        """US20.3: every registration for one event, in the order they were made."""
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("event_id", event_id)
            .order("id")
            .execute()
        )
        return [to_registration(row) for row in response.data or []]

    def get_registration(self, registration_id: int) -> Registration | None:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(WITH_EVENT_COLUMNS)
            .eq("id", registration_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return to_registration(rows[0]) if rows else None

    def withdraw(self, registration_id: int, *, attendee_id: int) -> WithdrawResult:
        result = supabase_client.admin().rpc(
            "withdraw_registration",
            {"p_registration_id": registration_id, "p_attendee_id": attendee_id},
        ).execute()
        answer = result.data if isinstance(result.data, dict) else {}
        try:
            outcome = WithdrawOutcome(answer.get("outcome"))
        except ValueError:
            raise RuntimeError(f"withdraw_registration answered {answer!r}") from None
        if outcome is not WithdrawOutcome.WITHDRAWN:
            return WithdrawResult(outcome=outcome)
        return WithdrawResult(outcome=outcome, registration=self.get_registration(registration_id))


#: The statuses `set_event_registration` takes settings at.
SETTABLE: frozenset[EventStatus] = frozenset(
    {
        EventStatus.APPROVED,
        EventStatus.PLANNING,
        EventStatus.PENDING_SAFETY_CHECK,
        EventStatus.CONFIRMED,
    }
)


@dataclass
class InMemoryRegistrations:
    """A stand-in for tests, with the database's rules and its one lock.

    Events are read from `event_store` at the time of each call, standing in
    for the columns the real store reads off the same row.
    """

    #: event id -> (is_open, capacity)
    settings: dict[int, tuple[bool, int | None]] = field(default_factory=dict)
    registrations: list[Registration] = field(default_factory=list)
    next_id: int = 100
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def _registered(self, event_id: int) -> int:
        return sum(
            1 for item in self.registrations if item.event_id == event_id and item.status in ACTIVE
        )

    def settings_for(self, event_id: int) -> RegistrationSettings:
        is_open, capacity = self.settings.get(event_id, (False, None))
        return RegistrationSettings(
            event_id=event_id,
            is_open=is_open,
            capacity=capacity,
            registered=self._registered(event_id),
        )

    def set_settings(
        self, event_id: int, *, actor_id: int, is_open: bool, capacity: int | None
    ) -> RegistrationSettings:
        with self.lock:
            event = event_store.repository().get_event(event_id)
            # D3: the owning Organiser may change the settings as well.
            allowed = event is not None and actor_id in (event.coordinator_id, event.organiser_id)
            if not allowed or event.status not in SETTABLE:
                raise StaleRegistrationSettings
            stored = self.settings.get(event_id, (False, None))[1]
            kept = capacity if capacity is not None else stored
            taken = self._registered(event_id)
            if kept is not None and kept < taken:
                raise BelowRegistered(taken)
            self.settings[event_id] = (is_open, kept)
        return self.settings_for(event_id)

    def _open(self, event_id: int) -> OpenEvent | None:
        is_open, capacity = self.settings.get(event_id, (False, None))
        event = event_store.repository().get_event(event_id)
        if not is_open or capacity is None or event is None:
            return None
        if event.status is not EventStatus.CONFIRMED:
            return None
        return OpenEvent(
            event_id=event.id,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            capacity=capacity,
            registered=self._registered(event.id),
        )

    def list_open(self) -> list[OpenEvent]:
        found = (self._open(event_id) for event_id in self.settings)
        return sorted(
            (item for item in found if item is not None),
            key=lambda item: (item.starts_at, item.event_id),
        )

    def get_open(self, event_id: int) -> OpenEvent | None:
        return self._open(event_id)

    def registered_event_ids(self, attendee_id: int) -> frozenset[int]:
        return frozenset(
            item.event_id
            for item in self.registrations
            if item.attendee_id == attendee_id and item.status in ACTIVE
        )

    def register(
        self, event_id: int, *, attendee_id: int, name: str, email: str
    ) -> RegisterResult:
        with self.lock:
            event = self._open(event_id)
            if event is None:
                return RegisterResult(outcome=RegisterOutcome.CLOSED)
            if event_id in self.registered_event_ids(attendee_id):
                return RegisterResult(outcome=RegisterOutcome.ALREADY_REGISTERED)
            if event.registered >= event.capacity:
                return RegisterResult(outcome=RegisterOutcome.FULL)
            registration = Registration(
                id=self.next_id,
                event_id=event_id,
                attendee_id=attendee_id,
                name=name.strip(),
                email=email.strip(),
                status=RegistrationStatus.REGISTERED,
                created_at=_now(),
            )
            self.next_id += 1
            self.registrations.append(registration)
            return RegisterResult(
                outcome=RegisterOutcome.REGISTERED,
                registration=registration,
                became_full=event.registered + 1 >= event.capacity,
            )

    def _with_event(self, registration: Registration) -> Registration:
        """Stands in for the embedded `events(...)` the real store reads."""
        event = event_store.repository().get_event(registration.event_id)
        if event is None:
            return replace(registration, event=None)
        return replace(
            registration,
            event=RegisteredEvent(
                title=event.title,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                status=event.status,
            ),
        )

    def list_for_attendee(self, attendee_id: int) -> list[Registration]:
        mine = (item for item in self.registrations if item.attendee_id == attendee_id)
        return [self._with_event(item) for item in sorted(mine, key=lambda item: -item.id)]

    def list_for_event(self, event_id: int) -> list[Registration]:
        return sorted(
            (item for item in self.registrations if item.event_id == event_id),
            key=lambda item: item.id,
        )

    def cancel_for_event(self, event_id: int) -> tuple[int, ...]:
        """US4.6: `cancel_event`'s registration half, for InMemoryEvents to call.

        Every Registered registration becomes Event Cancelled, registration
        closes (the capacity is kept), and the ids moved are returned.
        """
        with self.lock:
            moved = tuple(
                item.id
                for item in self.registrations
                if item.event_id == event_id and item.status in ACTIVE
            )
            self.registrations = [
                replace(item, status=RegistrationStatus.EVENT_CANCELLED)
                if item.id in moved
                else item
                for item in self.registrations
            ]
            if event_id in self.settings:
                self.settings[event_id] = (False, self.settings[event_id][1])
        return moved

    def get_registration(self, registration_id: int) -> Registration | None:
        found = next((item for item in self.registrations if item.id == registration_id), None)
        return self._with_event(found) if found is not None else None

    def withdraw(self, registration_id: int, *, attendee_id: int) -> WithdrawResult:
        with self.lock:
            found = self.get_registration(registration_id)
            if found is None or found.attendee_id != attendee_id:
                return WithdrawResult(outcome=WithdrawOutcome.NOT_FOUND)
            refusal = withdrawal_refusal(found, found.event, local_now())
            if refusal is not None:
                return WithdrawResult(outcome=refusal)
            withdrawn = replace(
                found, status=RegistrationStatus.WITHDRAWN, withdrawn_at=_now(), event=None
            )
            self.registrations = [
                withdrawn if item.id == registration_id else item for item in self.registrations
            ]
        return WithdrawResult(
            outcome=WithdrawOutcome.WITHDRAWN, registration=self.get_registration(registration_id)
        )


_repository: Repository = SupabaseRegistrations()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
