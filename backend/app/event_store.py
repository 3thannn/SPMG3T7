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
    "id, name, purpose, description, proposed_date, end_date, expected_attendance, "
    "status, organiser_id, created_at, updated_at, submitted_at, users(name)"
)
CHANGE_COLUMNS = "id, old_status, new_status, changed_at, notes, changed_by_id, users(name)"


@dataclass(frozen=True)
class StatusChange:
    """One entry in an event's audit trail — US4.2 requires who and when.

    `notes` is the `status_changes.notes` column, which the schema has always
    had and nothing wrote until US7.3. A Coordinator asking for clarification
    attaches the message here, so the request travels with the status change
    that caused it rather than in a table of its own.
    """

    from_status: EventStatus | None
    to_status: EventStatus
    at: str
    by_id: int
    by_name: str
    #: Empty for an automatic entry; the Coordinator's message for US7.3.
    notes: str = ""


@dataclass(frozen=True)
class Event:
    id: int
    title: str
    purpose: str
    description: str
    starts_at: str
    #: `events.end_date`, optional for drafts and populated when supplied.
    ends_at: str
    #: `events.expected_attendance` is nullable, so "not estimated yet" is a
    #: real answer and distinct from an estimate of zero.
    expected_attendance: int | None
    status: EventStatus
    organiser_id: int
    organiser_name: str
    created_at: str
    updated_at: str
    #: US8.1: The assigned Event Coordinator's ID, or None if unassigned.
    coordinator_id: int | None = None
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
        notes=row.get("notes") or "",
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
        title=row.get("name") or "",
        purpose=row.get("purpose") or "",
        description=row.get("description") or "",
        starts_at=str(row["proposed_date"]) if row.get("proposed_date") else "",
        ends_at=str(row["end_date"]) if row.get("end_date") else "",
        expected_attendance=row.get("expected_attendance"),
        status=EventStatus(row["status"]),
        organiser_id=row["organiser_id"],
        organiser_name=_embedded_name(row),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        coordinator_id=row.get("coordinator_id"),
    )
    stored = sorted(
        (to_change(change) for change in changes or []),
        key=lambda change: change.at,
    )
    return replace(event, history=(creation_entry(event), *stored))


class Repository(Protocol):
    def list_events(self, *, organiser_id: int | None, include_drafts: bool) -> list[Event]: ...

    def get_event(self, event_id: int) -> Event | None: ...

    def create_event(
        self,
        *,
        title: str,
        purpose: str,
        description: str,
        starts_at: str,
        ends_at: str | None,
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
        ends_at: str | None,
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
        ends_at: str | None,
        expected_attendance: int | None,
        editor_id: int,
        previous_event: Event,
    ) -> Event: ...

    def create_event_request(
        self,
        *,
        name: str,
        purpose: str,
        description: str,
        starts_at: str,
        ends_at: str,
        expected_attendance: int,
        organiser_id: int,
    ) -> Event: ...

    def submit_event(self, event_id: int, *, actor_id: int, from_status: EventStatus) -> Event: ...

    def request_clarification(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, message: str
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

    def list_events(self, *, organiser_id: int | None, include_drafts: bool) -> list[Event]:
        """Filter visibility in the database before event data leaves it."""
        query = supabase_client.admin().table(EVENTS_TABLE).select(EVENT_COLUMNS)
        if organiser_id is not None:
            query = query.eq("organiser_id", organiser_id)
        if not include_drafts:
            query = query.neq("status", str(EventStatus.DRAFT))
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
        ends_at: str | None,
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
                    "proposed_date": starts_at if starts_at.strip() else None,
                    "end_date": ends_at if ends_at and ends_at.strip() else None,
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
        ends_at: str | None,
        expected_attendance: int | None,
    ) -> Event:
        """US4.2: saving edits content and never moves the status."""
        supabase_client.admin().table(EVENTS_TABLE).update(
            {
                "name": title,
                "purpose": purpose or None,
                "description": description,
                "proposed_date": starts_at if starts_at.strip() else None,
                "end_date": ends_at if ends_at and ends_at.strip() else None,
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
        ends_at: str | None,
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
            changes_to_log.append(
                {
                    "event_id": event_id,
                    "changed_field": "proposed_date",
                    "old_value": previous_event.starts_at,
                    "new_value": starts_at,
                    "change_type": "important",
                    "changed_by_user_id": editor_id,
                    "changed_at": at,
                }
            )

        if expected_attendance != previous_event.expected_attendance:
            changes_to_log.append(
                {
                    "event_id": event_id,
                    "changed_field": "expected_attendance",
                    "old_value": (
                        str(previous_event.expected_attendance)
                        if previous_event.expected_attendance is not None
                        else None
                    ),
                    "new_value": (
                        str(expected_attendance) if expected_attendance is not None else None
                    ),
                    "change_type": "important",
                    "changed_by_user_id": editor_id,
                    "changed_at": at,
                }
            )

        # Routine changes: name (title), purpose, description
        if title != previous_event.title:
            changes_to_log.append(
                {
                    "event_id": event_id,
                    "changed_field": "name",
                    "old_value": previous_event.title,
                    "new_value": title,
                    "change_type": "routine",
                    "changed_by_user_id": editor_id,
                    "changed_at": at,
                }
            )

        if purpose != previous_event.purpose:
            changes_to_log.append(
                {
                    "event_id": event_id,
                    "changed_field": "purpose",
                    "old_value": previous_event.purpose,
                    "new_value": purpose,
                    "change_type": "routine",
                    "changed_by_user_id": editor_id,
                    "changed_at": at,
                }
            )

        if description != previous_event.description:
            changes_to_log.append(
                {
                    "event_id": event_id,
                    "changed_field": "description",
                    "old_value": previous_event.description,
                    "new_value": description,
                    "change_type": "routine",
                    "changed_by_user_id": editor_id,
                    "changed_at": at,
                }
            )

        # Update the event
        supabase_client.admin().table(EVENTS_TABLE).update(
            {
                "name": title,
                "purpose": purpose or None,
                "description": description,
                "proposed_date": starts_at,
                "end_date": ends_at,
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

    def create_event_request(
        self,
        *,
        name: str,
        purpose: str,
        description: str,
        starts_at: str,
        ends_at: str,
        expected_attendance: int,
        organiser_id: int,
    ) -> Event:
        """Event Request Creation: the row lands already Submitted.

        The audit row is written in the same breath, for the reason the module
        docstring gives: `status_changes.old_status` is NOT NULL, so there is no
        entry that can mean "created straight into Submitted". Recording
        Draft -> Submitted at the creation timestamp keeps the trail honest
        about what happened — the event did exist as a draft, for no time at
        all — and keeps the derived creation entry meaning what it always meant.
        """
        at = _now()
        created = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .insert(
                {
                    "name": name,
                    "purpose": purpose,
                    "description": description,
                    "proposed_date": starts_at,
                    "end_date": ends_at,
                    "expected_attendance": expected_attendance,
                    "status": str(EventStatus.SUBMITTED),
                    "organiser_id": organiser_id,
                    "created_at": at,
                    "updated_at": at,
                    "submitted_at": at,
                }
            )
            .execute()
        )
        event_id = created.data[0]["id"]
        supabase_client.admin().table(CHANGES_TABLE).insert(
            {
                "event_id": event_id,
                "old_status": str(EventStatus.DRAFT),
                "new_status": str(EventStatus.SUBMITTED),
                "changed_by_id": organiser_id,
                "changed_at": at,
            }
        ).execute()
        # Read back rather than assembled here: the insert response carries no
        # embedded organiser name, exactly as in `create_event`.
        event = self.get_event(event_id)
        assert event is not None  # noqa: S101 — the row was just inserted
        return event

    def submit_event(self, event_id: int, *, actor_id: int, from_status: EventStatus) -> Event:
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

    def request_clarification(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, message: str
    ) -> Event:
        """US7.3: attach a Coordinator's message and move the event under review.

        The message goes in `status_changes.notes`, on the row that records the
        move. That is why there is no new table: the request and the status
        change it caused are one event in the event's history, and storing them
        apart would let them disagree about when it happened or who asked.

        The status is written even when it is already Under Review — a second
        question is still a question — so the audit trail gains an entry either
        way and `updated_at` moves, which is what puts the event back at the top
        of the Organiser's list.
        """
        at = _now()
        supabase_client.admin().table(EVENTS_TABLE).update(
            {"status": str(EventStatus.UNDER_REVIEW), "updated_at": at}
        ).eq("id", event_id).execute()
        supabase_client.admin().table(CHANGES_TABLE).insert(
            {
                "event_id": event_id,
                "old_status": str(from_status),
                "new_status": str(EventStatus.UNDER_REVIEW),
                "changed_by_id": actor_id,
                "changed_at": at,
                "notes": message,
            }
        ).execute()
        reviewed = self.get_event(event_id)
        assert reviewed is not None  # noqa: S101 — the row was just updated
        return reviewed


@dataclass
class InMemoryEvents:
    """A stand-in for tests, with the same visibility and audit behaviour."""

    events: list[Event] = field(default_factory=list)
    #: user id -> display name, standing in for the joined `users(name)`.
    names: dict[int, str] = field(default_factory=dict)
    next_id: int = 100
    #: US8.1 AC2: Track the last assigned coordinator ID for round-robin.
    last_assigned_coordinator_id: int | None = None

    def _replace(self, event: Event) -> Event:
        self.events = [event if item.id == event.id else item for item in self.events]
        return event

    def _pick_coordinator(self) -> int | None:
        """US8.1 AC2: Select a Coordinator via round-robin. Returns None if none exist."""
        from app import users
        from app.permissions import Role

        # Get all coordinators from the user store, sorted by ID for consistency
        all_users = users.list_users()
        coordinators = sorted(
            [u for u in all_users if u.role == Role.COORDINATOR],
            key=lambda u: u.id
        )

        if not coordinators:
            return None

        # Round-robin: find the next coordinator after the last assigned one
        if self.last_assigned_coordinator_id is None:
            # First assignment: pick the first coordinator
            next_coordinator = coordinators[0]
        else:
            # Find the last assigned coordinator's index
            try:
                last_index = next(
                    i for i, c in enumerate(coordinators)
                    if c.id == self.last_assigned_coordinator_id
                )
                # Pick the next one, wrapping around if needed
                next_coordinator = coordinators[(last_index + 1) % len(coordinators)]
            except StopIteration:
                # Last assigned coordinator no longer exists, start from beginning
                next_coordinator = coordinators[0]

        # Remember this assignment for next time
        self.last_assigned_coordinator_id = next_coordinator.id
        return next_coordinator.id

    def list_events(self, *, organiser_id: int | None, include_drafts: bool) -> list[Event]:
        visible = [
            event
            for event in self.events
            if (organiser_id is None or event.organiser_id == organiser_id)
            and (include_drafts or event.status != EventStatus.DRAFT)
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
        ends_at: str | None,
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
            ends_at=ends_at or "",
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
        ends_at: str | None,
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
                ends_at=ends_at or "",
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
        ends_at: str | None,
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
            ends_at=ends_at,
            expected_attendance=expected_attendance,
        )

    def create_event_request(
        self,
        *,
        name: str,
        purpose: str,
        description: str,
        starts_at: str,
        ends_at: str,
        expected_attendance: int,
        organiser_id: int,
    ) -> Event:
        """The same two writes as the Supabase store, and the same history.

        US8.1: Events created already Submitted get assigned a Coordinator."""
        at = _now()
        self.next_id += 1
        coordinator_id = self._pick_coordinator()
        event = Event(
            id=self.next_id,
            title=name,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            expected_attendance=expected_attendance,
            status=EventStatus.SUBMITTED,
            organiser_id=organiser_id,
            organiser_name=self.names.get(organiser_id, ""),
            created_at=at,
            updated_at=at,
            coordinator_id=coordinator_id,
        )
        submission = StatusChange(
            from_status=EventStatus.DRAFT,
            to_status=EventStatus.SUBMITTED,
            at=at,
            by_id=organiser_id,
            by_name=self.names.get(organiser_id, ""),
        )
        event = replace(event, history=(creation_entry(event), submission))
        self.events.insert(0, event)
        return event

    def submit_event(self, event_id: int, *, actor_id: int, from_status: EventStatus) -> Event:
        """US8.1: Moving to Submitted assigns a Coordinator."""
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        at = _now()

        # US8.1: Assign a Coordinator when transitioning to Submitted
        coordinator_id = self._pick_coordinator()

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
                coordinator_id=coordinator_id,
                history=(*existing.history, entry),
            )
        )

    def request_clarification(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, message: str
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        at = _now()
        entry = StatusChange(
            from_status=from_status,
            to_status=EventStatus.UNDER_REVIEW,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
            notes=message,
        )
        return self._replace(
            replace(
                existing,
                status=EventStatus.UNDER_REVIEW,
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
