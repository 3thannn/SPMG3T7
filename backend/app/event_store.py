"""Event data access, backed by the Supabase `events` and `status_changes` tables.

This module reads and writes; the rules about who may do what live in
`app.events` (the routes) and `app.event_status`. Keeping them apart means the
store can be swapped for an in-memory one in tests without taking the rules with
it.

Two things the table shapes forced, both worth knowing:

* `status_changes.old_status` is NOT NULL, so there is no row that can represent
  "created". The creation entry in an event's history is therefore derived from
  the event's own `created_at` and organiser rather than stored — which is less
  a workaround than the honest model: creating an event is not a change of
  status, it is the first one.
* Dates are `timestamp without time zone`, and the browser's datetime-local
  input produces a naive local string. They are passed through as strings on
  purpose: converting to an aware datetime here and back in the client would
  shift a date by the server's offset, which is exactly the bug that makes an
  event show up on the wrong day.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from app import supabase_client
from app.event_status import EventStatus

EVENTS_TABLE = "events"
CHANGES_TABLE = "status_changes"
EVENT_CHANGES_TABLE = "event_changes"

# `users(name)` resolves through the one foreign key each table has to users.
EVENT_COLUMNS = (
    "id, name, purpose, description, proposed_date, expected_attendance, status, "
    "organiser_id, created_at, updated_at, submitted_at, users(name)"
)
CHANGE_COLUMNS = (
    "id, old_status, new_status, changed_at, notes, changed_by_id, users(name)"
)


@dataclass(frozen=True)
class StatusChange:
    """One entry in an event's audit trail — US4.2 requires who and when."""

    from_status: EventStatus | None
    to_status: EventStatus
    at: str
    by_id: int
    by_name: str


@dataclass(frozen=True)
class Event:
    id: int
    title: str
    purpose: str
    description: str
    starts_at: str
    #: `events.expected_attendance` is nullable, so "not estimated yet" is a
    #: real answer and distinct from an estimate of zero.
    expected_attendance: int | None
    status: EventStatus
    organiser_id: int
    organiser_name: str
    created_at: str
    updated_at: str
    history: tuple[StatusChange, ...] = ()


def _now() -> str:
    """A naive UTC timestamp, matching the column type. See the module docstring."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _embedded_name(row: dict) -> str:
    """The joined `users(name)`, which PostgREST returns as an object or a list."""
    joined = row.get("users")
    if isinstance(joined, list):
        joined = joined[0] if joined else None
    return joined.get("name", "") if isinstance(joined, dict) else ""


def to_change(row: dict) -> StatusChange:
    return StatusChange(
        from_status=EventStatus(row["old_status"]) if row.get("old_status") else None,
        to_status=EventStatus(row["new_status"]),
        at=str(row["changed_at"]),
        by_id=row["changed_by_id"],
        by_name=_embedded_name(row),
    )


def creation_entry(event: "Event") -> StatusChange:
    """The "Created as Draft" entry, derived rather than stored."""
    return StatusChange(
        from_status=None,
        to_status=EventStatus.DRAFT,
        at=event.created_at,
        by_id=event.organiser_id,
        by_name=event.organiser_name,
    )


def to_event(row: dict, changes: list[dict] | None = None) -> Event:
    event = Event(
        id=row["id"],
        title=row["name"],
        purpose=row.get("purpose") or "",
        description=row.get("description") or "",
        starts_at=str(row["proposed_date"]) if row.get("proposed_date") else "",
        expected_attendance=row.get("expected_attendance"),
        status=EventStatus(row["status"]),
        organiser_id=row["organiser_id"],
        organiser_name=_embedded_name(row),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
    stored = sorted(
        (to_change(change) for change in changes or []),
        key=lambda change: change.at,
    )
    return replace(event, history=(creation_entry(event), *stored))


class Repository(Protocol):
    def list_events(self, organiser_id: int | None) -> list[Event]: ...

    def get_event(self, event_id: int) -> Event | None: ...

    def create_event(
        self,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        organiser_id: int,
    ) -> Event: ...

    def save_event(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
    ) -> Event: ...

    def save_event_with_tracking(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        editor_id: int,
        previous_event: Event,
    ) -> Event: ...

    def submit_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus
    ) -> Event: ...


class SupabaseEvents:
    """The real store. Goes through the service role client, like the user store."""

    def _changes_for(self, event_ids: list[int]) -> dict[int, list[dict]]:
        """Every audit row for a page of events, in one query rather than one each."""
        if not event_ids:
            return {}
        response = (
            supabase_client.admin()
            .table(CHANGES_TABLE)
            .select(f"event_id, {CHANGE_COLUMNS}")
            .in_("event_id", event_ids)
            .execute()
        )
        grouped: dict[int, list[dict]] = {}
        for row in response.data or []:
            grouped.setdefault(row["event_id"], []).append(row)
        return grouped

    def list_events(self, organiser_id: int | None) -> list[Event]:
        """US4.1: an Organiser sees their own events, a Coordinator sees every one."""
        query = supabase_client.admin().table(EVENTS_TABLE).select(EVENT_COLUMNS)
        if organiser_id is not None:
            query = query.eq("organiser_id", organiser_id)
        rows = query.order("updated_at", desc=True).execute().data or []
        changes = self._changes_for([row["id"] for row in rows])
        return [to_event(row, changes.get(row["id"])) for row in rows]

    def get_event(self, event_id: int) -> Event | None:
        response = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .select(EVENT_COLUMNS)
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return to_event(response.data[0], self._changes_for([event_id]).get(event_id))

    def create_event(
        self,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        organiser_id: int,
    ) -> Event:
        """US4.2: a new event always begins as a Draft."""
        at = _now()
        created = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .insert(
                {
                    "name": title,
                    "purpose": purpose or None,
                    "description": description,
                    "proposed_date": starts_at,
                    "expected_attendance": expected_attendance,
                    "status": str(EventStatus.DRAFT),
                    "organiser_id": organiser_id,
                    "created_at": at,
                    "updated_at": at,
                }
            )
            .execute()
        )
        # The insert response carries no embedded organiser name, so the row is
        # read back rather than assembled from what we happen to have here.
        event = self.get_event(created.data[0]["id"])
        assert event is not None  # noqa: S101 — the row was just inserted
        return event

    def save_event(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
    ) -> Event:
        """US4.2: saving edits content and never moves the status."""
        supabase_client.admin().table(EVENTS_TABLE).update(
            {
                "name": title,
                "purpose": purpose or None,
                "description": description,
                "proposed_date": starts_at,
                "expected_attendance": expected_attendance,
                "updated_at": _now(),
            }
        ).eq("id", event_id).execute()
        saved = self.get_event(event_id)
        assert saved is not None  # noqa: S101 — the row was just updated
        return saved

    def save_event_with_tracking(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        editor_id: int,
        previous_event: Event,
    ) -> Event:
        """US5.2: coordinator edits with change tracking (important vs routine)."""
        at = _now()

        # Track changes and classify them as important or routine
        changes_to_log: list[dict] = []

        # Important changes: proposed_date, expected_attendance
        if starts_at != previous_event.starts_at:
            changes_to_log.append({
                "event_id": event_id,
                "changed_field": "proposed_date",
                "old_value": previous_event.starts_at,
                "new_value": starts_at,
                "change_type": "important",
                "changed_by_user_id": editor_id,
                "changed_at": at,
            })

        if expected_attendance != previous_event.expected_attendance:
            changes_to_log.append({
                "event_id": event_id,
                "changed_field": "expected_attendance",
                "old_value": str(previous_event.expected_attendance) if previous_event.expected_attendance is not None else None,
                "new_value": str(expected_attendance) if expected_attendance is not None else None,
                "change_type": "important",
                "changed_by_user_id": editor_id,
                "changed_at": at,
            })

        # Routine changes: name (title), purpose, description
        if title != previous_event.title:
            changes_to_log.append({
                "event_id": event_id,
                "changed_field": "name",
                "old_value": previous_event.title,
                "new_value": title,
                "change_type": "routine",
                "changed_by_user_id": editor_id,
                "changed_at": at,
            })

        if purpose != previous_event.purpose:
            changes_to_log.append({
                "event_id": event_id,
                "changed_field": "purpose",
                "old_value": previous_event.purpose,
                "new_value": purpose,
                "change_type": "routine",
                "changed_by_user_id": editor_id,
                "changed_at": at,
            })

        if description != previous_event.description:
            changes_to_log.append({
                "event_id": event_id,
                "changed_field": "description",
                "old_value": previous_event.description,
                "new_value": description,
                "change_type": "routine",
                "changed_by_user_id": editor_id,
                "changed_at": at,
            })

        # Update the event
        supabase_client.admin().table(EVENTS_TABLE).update(
            {
                "name": title,
                "purpose": purpose or None,
                "description": description,
                "proposed_date": starts_at,
                "expected_attendance": expected_attendance,
                "updated_at": at,
            }
        ).eq("id", event_id).execute()

        # Log changes to event_changes table
        if changes_to_log:
            supabase_client.admin().table(EVENT_CHANGES_TABLE).insert(changes_to_log).execute()

        saved = self.get_event(event_id)
        assert saved is not None  # noqa: S101 — the row was just updated
        return saved

    def submit_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus
    ) -> Event:
        """Move the event and write the audit entry US4.2 requires."""
        at = _now()
        supabase_client.admin().table(EVENTS_TABLE).update(
            {"status": str(EventStatus.SUBMITTED), "submitted_at": at, "updated_at": at}
        ).eq("id", event_id).execute()
        supabase_client.admin().table(CHANGES_TABLE).insert(
            {
                "event_id": event_id,
                "old_status": str(from_status),
                "new_status": str(EventStatus.SUBMITTED),
                "changed_by_id": actor_id,
                "changed_at": at,
            }
        ).execute()
        submitted = self.get_event(event_id)
        assert submitted is not None  # noqa: S101 — the row was just updated
        return submitted


@dataclass
class InMemoryEvents:
    """A stand-in for tests, with the same visibility and audit behaviour."""

    events: list[Event] = field(default_factory=list)
    #: user id -> display name, standing in for the joined `users(name)`.
    names: dict[int, str] = field(default_factory=dict)
    next_id: int = 100

    def _replace(self, event: Event) -> Event:
        self.events = [event if item.id == event.id else item for item in self.events]
        return event

    def list_events(self, organiser_id: int | None) -> list[Event]:
        visible = [
            event
            for event in self.events
            if organiser_id is None or event.organiser_id == organiser_id
        ]
        return sorted(visible, key=lambda event: event.updated_at, reverse=True)

    def get_event(self, event_id: int) -> Event | None:
        return next((event for event in self.events if event.id == event_id), None)

    def create_event(
        self,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        organiser_id: int,
    ) -> Event:
        at = _now()
        self.next_id += 1
        event = Event(
            id=self.next_id,
            title=title,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            expected_attendance=expected_attendance,
            status=EventStatus.DRAFT,
            organiser_id=organiser_id,
            organiser_name=self.names.get(organiser_id, ""),
            created_at=at,
            updated_at=at,
        )
        event = replace(event, history=(creation_entry(event),))
        self.events.insert(0, event)
        return event

    def save_event(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        return self._replace(
            replace(
                existing,
                title=title,
                purpose=purpose,
                description=description,
                starts_at=starts_at,
                expected_attendance=expected_attendance,
                updated_at=_now(),
            )
        )

    def save_event_with_tracking(
        self,
        event_id: int,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        expected_attendance: int | None,
        editor_id: int,
        previous_event: Event,
    ) -> Event:
        """In-memory version of coordinator edits. Change tracking is not implemented in memory."""
        return self.save_event(
            event_id,
            title=title,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            expected_attendance=expected_attendance,
        )

    def submit_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        at = _now()
        entry = StatusChange(
            from_status=from_status,
            to_status=EventStatus.SUBMITTED,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
        )
        return self._replace(
            replace(
                existing,
                status=EventStatus.SUBMITTED,
                updated_at=at,
                history=(*existing.history, entry),
            )
        )


_repository: Repository = SupabaseEvents()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
