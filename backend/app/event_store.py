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
from app.change_requests import (
    ChangeReview,
    FieldChange,
    applied_values,
    change_type,
    is_important,
    ordered,
)
from app.event_needs import NEED_FIELDS, NO_NEEDS, EventNeeds
from app.event_status import EventStatus, check_completion

EVENTS_TABLE = "events"
CHANGES_TABLE = "status_changes"
EVENT_CHANGES_TABLE = "event_changes"
#: US11.1: an Organiser's proposed changes, kept apart from `event_changes` —
#: which records changes that were applied — until a Coordinator approves them.
CHANGE_REQUESTS_TABLE = "event_change_requests"

# US8.1: Two foreign keys to users now exist (organiser_id, coordinator_id),
# so PostgREST requires explicit relationship qualification via constraint name.
EVENT_COLUMNS = (
    "id, name, purpose, description, proposed_date, end_date, expected_attendance, "
    "venue_requirements, preferred_layout, accessibility_needs, equipment_needs, "
    "registration_needs, "
    "status, organiser_id, coordinator_id, created_at, updated_at, submitted_at, "
    "users!events_organiser_id_fkey(name)"
)
CHANGE_COLUMNS = "id, old_status, new_status, changed_at, notes, changed_by_id, users(name)"
#: US11.1: a request's rows. Pending rows are the request awaiting review; the
#: most recently answered ones carry the Coordinator's answer.
REQUEST_COLUMNS = (
    "event_id, changed_field, old_value, new_value, change_type, status, "
    "reviewed_at, review_note, request_note"
)
PENDING = "pending"


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
    #: Empty for an automatic entry; a US7.3 request, a US7.1 rejection
    #: reason, or the note on a US11.1 change request.
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
    #: US11.1: the "change requested" flag. Not a column: it is true exactly
    #: when the event has pending `event_change_requests` rows.
    change_requested: bool = False
    #: US11.1: what the Organiser has asked for, in form order. Empty unless
    #: `change_requested` is set.
    pending_changes: tuple[FieldChange, ...] = ()
    change_request_note: str = ""
    #: US11.1: the Coordinator's answer to the most recent request, if any.
    last_change_review: ChangeReview | None = None
    #: US2.1 (Sprint 3): what the event needs, as `app.event_needs` describes.
    #: Empty means not answered yet, which only a draft may leave.
    venue_requirements: str = ""
    preferred_layout: str = ""
    accessibility_needs: str = ""
    equipment_needs: str = ""
    registration_needs: str = ""

    @property
    def needs(self) -> EventNeeds:
        return EventNeeds(**{name: getattr(self, name) for name in NEED_FIELDS})


class StaleEventStatus(RuntimeError):
    """The event changed after the route checked its current status."""


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


def to_field_change(row: dict) -> FieldChange:
    return FieldChange(
        field=row["changed_field"],
        old_value=row.get("old_value") or "",
        new_value=row.get("new_value") or "",
        important=row.get("change_type") == "important",
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


def latest_review(requests: list[dict]) -> ChangeReview | None:
    """The answer to the most recent answered request, from its rows.

    Every row of one request is answered together, so they share
    `reviewed_at`; the latest of those is the request the Organiser last heard
    back about.
    """
    answered = [row for row in requests if row.get("status") != PENDING and row.get("reviewed_at")]
    if not answered:
        return None
    last = max(answered, key=lambda row: str(row["reviewed_at"]))
    return ChangeReview(
        outcome=last["status"],
        at=str(last["reviewed_at"]),
        note=last.get("review_note") or "",
        request_note=last.get("request_note") or "",
    )


def to_event(
    row: dict, changes: list[dict] | None = None, requests: list[dict] | None = None
) -> Event:
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
        **{name: row.get(name) or "" for name in NEED_FIELDS},
    )
    stored = sorted(
        (to_change(change) for change in changes or []),
        key=lambda change: change.at,
    )
    pending = ordered(
        to_field_change(item) for item in requests or [] if item.get("status") == PENDING
    )
    return replace(
        event,
        history=(creation_entry(event), *stored),
        change_requested=bool(pending),
        pending_changes=pending,
        change_request_note=next(
            (
                item.get("request_note") or ""
                for item in requests or []
                if item.get("status") == PENDING
            ),
            "",
        ),
        last_change_review=latest_review(requests or []),
    )


class Repository(Protocol):
    def list_events(self, *, organiser_id: int | None, include_drafts: bool) -> list[Event]: ...

    def list_unassigned(self) -> list[Event]: ...

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
        needs: EventNeeds = NO_NEEDS,
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
        needs: EventNeeds = NO_NEEDS,
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
        needs: EventNeeds = NO_NEEDS,
    ) -> Event: ...

    def submit_event(self, event_id: int, *, actor_id: int, from_status: EventStatus) -> Event: ...

    def request_clarification(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, message: str
    ) -> Event: ...

    def decide_event(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        to_status: EventStatus,
        reason: str,
    ) -> Event: ...
     
    def submit_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        changes: tuple[FieldChange, ...],
        note: str,
    ) -> Event: ...

    def resolve_change_request(
        self, event_id: int, *, actor_id: int, approve: bool, note: str
    ) -> Event: ...

    def assign_coordinator(
        self, event_id: int, coordinator_id: int, assigned_by_id: int
    ) -> Event: ...

    def complete_event(self, event_id: int, *, actor_id: int) -> Event: ...

    def plan_event(self, event_id: int, *, actor_id: int) -> Event: ...

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event: ...

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
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

    def _requests_for(self, event_ids: list[int]) -> dict[int, list[dict]]:
        """US11.1: change request rows for a page of events, in one query.

        Pending and answered rows both come back: pending ones are the request
        to review, and answered ones carry the Coordinator's last answer.
        """
        if not event_ids:
            return {}
        response = (
            supabase_client.admin()
            .table(CHANGE_REQUESTS_TABLE)
            .select(REQUEST_COLUMNS)
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
        event_ids = [row["id"] for row in rows]
        changes = self._changes_for(event_ids)
        requests = self._requests_for(event_ids)
        return [to_event(row, changes.get(row["id"]), requests.get(row["id"])) for row in rows]

    def list_unassigned(self) -> list[Event]:
        """US8.2: List events that are Submitted but have no assigned Coordinator."""
        rows = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .select(EVENT_COLUMNS)
            .eq("status", str(EventStatus.SUBMITTED))
            .is_("coordinator_id", "null")
            .order("submitted_at", desc=False)  # oldest first
            .execute()
            .data or []
        )
        changes = self._changes_for([row["id"] for row in rows])
        requests = self._requests_for([row["id"] for row in rows])
        return [to_event(row, changes.get(row["id"]), requests.get(row["id"])) for row in rows]

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
        return to_event(
            response.data[0],
            self._changes_for([event_id]).get(event_id),
            self._requests_for([event_id]).get(event_id),
        )

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
        needs: EventNeeds = NO_NEEDS,
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
                    **needs.as_columns(),
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
        needs: EventNeeds = NO_NEEDS,
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
                **needs.as_columns(),
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
        needs: EventNeeds = NO_NEEDS,
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

        # US2.1 (Sprint 3): each need is its own column, classified by the same
        # rule a change request uses.
        for name, value in needs.as_attrs().items():
            old_value = getattr(previous_event, name)
            if value != old_value:
                changes_to_log.append(
                    {
                        "event_id": event_id,
                        "changed_field": name,
                        "old_value": old_value,
                        "new_value": value,
                        "change_type": "important" if is_important(name) else "routine",
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
                **needs.as_columns(),
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

        Direct creation leaves the event unassigned for the Lead's queue.
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
                    "coordinator_id": None,
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
        """Move the event and write the audit entry US4.2 requires.

        US8.2: Auto-assignment is now OFF. Events remain unassigned on submit."""
        at = _now()
        supabase_client.admin().table(EVENTS_TABLE).update(
            {
                "status": str(EventStatus.SUBMITTED),
                "submitted_at": at,
                "updated_at": at,
            }
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
        updated = (
            supabase_client.admin()
            .table(EVENTS_TABLE)
            .update({"status": str(EventStatus.UNDER_REVIEW), "updated_at": at})
            .eq("id", event_id)
            .eq("status", str(from_status))
            .execute()
        )
        if not updated.data:
            raise StaleEventStatus
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

    def decide_event(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        to_status: EventStatus,
        reason: str,
    ) -> Event:
        """US7.1: atomically record one Coordinator decision and its audit entry.

        Transition validation remains in Python. The RPC is only the transaction
        boundary needed to prevent a final status without its required US4.2
        audit row.
        """
        result = supabase_client.admin().rpc(
            "decide_event_status",
            {
                "p_event_id": event_id,
                "p_expected_status": str(from_status),
                "p_new_status": str(to_status),
                "p_changed_by_id": actor_id,
                "p_notes": reason or None,
            },
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        decided = self.get_event(event_id)
        assert decided is not None  # noqa: S101 - the row was just updated
        return decided

    def submit_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        changes: tuple[FieldChange, ...],
        note: str,
    ) -> Event:
        """Store the proposal and flag; only assigned Submitted events move status.

        The proposal goes to event_change_requests, not event_changes:
        nothing has changed yet. The status move, the request rows and the
        history entry must not come apart, so the RPC is the transaction
        boundary, as it is for US7.1. It locks the event and re-checks the
        status and that nothing is pending, so a concurrent request or decision
        is reported as stale rather than overwritten.
        """
        result = supabase_client.admin().rpc(
            "submit_change_request",
            {
                "p_event_id": event_id,
                "p_expected_status": str(from_status),
                "p_changed_by_id": actor_id,
                "p_changes": [
                    {
                        "changed_field": change.field,
                        "old_value": change.old_value,
                        "new_value": change.new_value,
                        "change_type": change_type(change),
                    }
                    for change in changes
                ],
                "p_notes": note or None,
            },
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        requested = self.get_event(event_id)
        assert requested is not None  # noqa: S101 - the row was just updated
        return requested

    def resolve_change_request(
        self, event_id: int, *, actor_id: int, approve: bool, note: str
    ) -> Event:
        """US11.1: approve (apply) or reject the pending proposal, and clear the flag.

        Approving applies each field and only then logs it to event_changes,
        as the US5.2 change it now is; rejecting logs nothing there. The request
        rows are kept, marked approved or rejected, with who answered, when,
        and the reason. No status-history entry is added: the status does not
        move.

        Answering a request never changes the event's current status.
        """
        result = supabase_client.admin().rpc(
            "resolve_change_request",
            {
                "p_event_id": event_id,
                "p_approve": approve,
                "p_changed_by_id": actor_id,
                "p_notes": note or None,
            },
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        resolved = self.get_event(event_id)
        assert resolved is not None  # noqa: S101 - the row was just updated
        return resolved

    def assign_coordinator(self, event_id: int, coordinator_id: int, assigned_by_id: int) -> Event:
        """Assign and audit Submitted -> Under Review in one transaction."""
        result = supabase_client.admin().rpc(
            "assign_event_coordinator",
            {
                "p_event_id": event_id,
                "p_coordinator_id": coordinator_id,
                "p_assigned_by_id": assigned_by_id,
            },
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        assigned = self.get_event(event_id)
        assert assigned is not None  # noqa: S101 - the row was just updated
        return assigned

    def complete_event(self, event_id: int, *, actor_id: int) -> Event:
        """Complete only an ended Confirmed event, with its audit entry."""
        result = supabase_client.admin().rpc(
            "complete_event_status",
            {"p_event_id": event_id, "p_coordinator_id": actor_id},
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        completed = self.get_event(event_id)
        assert completed is not None  # noqa: S101 - the row was just updated
        return completed

    def plan_event(self, event_id: int, *, actor_id: int) -> Event:
        return self.decide_event(
            event_id, actor_id=actor_id, from_status=EventStatus.APPROVED,
            to_status=EventStatus.PLANNING, reason="",
        )

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event:
        """US4.4: Planning -> Pending Safety Check, with its audit entry.

        The RPC locks the event and re-checks readiness — every active booking
        Confirmed and unflagged, no outstanding equipment line, no pending
        change request — so a booking or line that changed after the route's
        check is reported as stale rather than slipping through.
        """
        result = supabase_client.admin().rpc(
            "send_event_to_safety_check",
            {"p_event_id": event_id, "p_coordinator_id": actor_id},
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        sent = self.get_event(event_id)
        assert sent is not None  # noqa: S101 - the row was just updated
        return sent

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
    ) -> Event:
        """US4.4: Pending Safety Check -> Confirmed or back to Planning, audited.

        The RPC only moves an event that is still Pending Safety Check, and
        only for a Safety Officer, so a second decision on the same check
        fails rather than overwriting the first.
        """
        result = supabase_client.admin().rpc(
            "decide_safety_check",
            {
                "p_event_id": event_id,
                "p_new_status": str(to_status),
                "p_officer_id": actor_id,
                "p_notes": note or None,
            },
        ).execute()
        if result.data is not True:
            raise StaleEventStatus
        decided = self.get_event(event_id)
        assert decided is not None  # noqa: S101 - the row was just updated
        return decided

@dataclass
class InMemoryEvents:
    """A stand-in for tests, with the same visibility and audit behaviour."""

    events: list[Event] = field(default_factory=list)
    #: user id -> display name, standing in for the joined `users(name)`.
    names: dict[int, str] = field(default_factory=dict)
    next_id: int = 100
    #: US11.1: `event_change_requests` rows as `(event_id, change, status)`.
    #: Pending rows are also on the event as `pending_changes`; this keeps
    #: every request, including the ones answered.
    change_requests: list[tuple[int, FieldChange, str]] = field(default_factory=list)
    #: `event_changes` rows as `(event_id, change)` — changes that were applied.
    #: Only an approved request adds to it.
    change_log: list[tuple[int, FieldChange]] = field(default_factory=list)

    def _replace(self, event: Event) -> Event:
        self.events = [event if item.id == event.id else item for item in self.events]
        return event

    def list_events(self, *, organiser_id: int | None, include_drafts: bool) -> list[Event]:
        visible = [
            event
            for event in self.events
            if (organiser_id is None or event.organiser_id == organiser_id)
            and (include_drafts or event.status != EventStatus.DRAFT)
        ]
        return sorted(visible, key=lambda event: event.updated_at, reverse=True)

    def list_unassigned(self) -> list[Event]:
        """US8.2: List events that are Submitted but have no assigned Coordinator."""
        unassigned = [
            event
            for event in self.events
            if event.status == EventStatus.SUBMITTED and event.coordinator_id is None
        ]
        # Sort by created_at oldest first (in-memory doesn't have submitted_at tracked separately)
        return sorted(unassigned, key=lambda event: event.created_at)

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
        needs: EventNeeds = NO_NEEDS,
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
            **needs.as_attrs(),
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
        needs: EventNeeds = NO_NEEDS,
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
                **needs.as_attrs(),
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
        needs: EventNeeds = NO_NEEDS,
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
            needs=needs,
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

        Direct creation leaves the event unassigned for the Lead's queue."""
        at = _now()
        self.next_id += 1
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
            coordinator_id=None,
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
        """US8.2: Moving to Submitted leaves coordinator_id as NULL (auto-assignment OFF)."""
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

    def request_clarification(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, message: str
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        if existing.status is not from_status:
            raise StaleEventStatus
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

    def decide_event(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        to_status: EventStatus,
        reason: str,
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not from_status:
            raise StaleEventStatus
        at = _now()
        entry = StatusChange(
            from_status=from_status,
            to_status=to_status,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
            notes=reason,
        )
        return self._replace(
            replace(
                existing,
                status=to_status,
                updated_at=at,
                history=(*existing.history, entry),
            )
        )

    def submit_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        changes: tuple[FieldChange, ...],
        note: str,
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not from_status or existing.change_requested:
            raise StaleEventStatus
        at = _now()
        move_to_review = (
            from_status is EventStatus.SUBMITTED and existing.coordinator_id is not None
        )
        new_status = EventStatus.UNDER_REVIEW if move_to_review else from_status
        entry = StatusChange(
            from_status=from_status,
            to_status=new_status,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
            notes=note,
        ) if move_to_review else None
        self.change_requests.extend((event_id, change, "pending") for change in changes)
        return self._replace(
            replace(
                existing,
                status=new_status,
                updated_at=at,
                change_requested=True,
                pending_changes=ordered(changes),
                change_request_note=note,
                history=(*existing.history, entry) if entry else existing.history,
            )
        )

    def resolve_change_request(
        self, event_id: int, *, actor_id: int, approve: bool, note: str
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if not existing.change_requested or existing.status not in (
            EventStatus.UNDER_REVIEW, EventStatus.APPROVED, EventStatus.PLANNING
        ):
            raise StaleEventStatus
        at = _now()
        outcome = "approved" if approve else "rejected"

        def answered(row_event: int, status: str) -> str:
            return outcome if row_event == event_id and status == "pending" else status

        self.change_requests = [
            (row_event, change, answered(row_event, status))
            for row_event, change, status in self.change_requests
        ]
        if approve:
            self.change_log.extend((event_id, change) for change in existing.pending_changes)
        applied = applied_values(existing.pending_changes) if approve else {}
        return self._replace(
            replace(
                existing,
                **applied,
                updated_at=at,
                change_requested=False,
                pending_changes=(),
                change_request_note="",
                last_change_review=ChangeReview(
                    outcome=outcome, at=at, note=note,
                    request_note=existing.change_request_note,
                ),
            )
        )

    def assign_coordinator(self, event_id: int, coordinator_id: int, assigned_by_id: int) -> Event:
        """US8.3: Manually assign a Coordinator to an event."""
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not EventStatus.SUBMITTED or existing.coordinator_id is not None:
            raise StaleEventStatus
        at = _now()
        entry = StatusChange(
            from_status=EventStatus.SUBMITTED,
            to_status=EventStatus.UNDER_REVIEW,
            at=at,
            by_id=assigned_by_id,
            by_name=self.names.get(assigned_by_id, ""),
        )
        return self._replace(
            replace(
                existing,
                coordinator_id=coordinator_id,
                status=EventStatus.UNDER_REVIEW,
                updated_at=at,
                history=(*existing.history, entry),
            )
        )

    def complete_event(self, event_id: int, *, actor_id: int) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not EventStatus.CONFIRMED or existing.coordinator_id != actor_id:
            raise StaleEventStatus
        if check_completion(existing.ends_at) is not None:
            raise StaleEventStatus
        at = _now()
        entry = StatusChange(
            from_status=EventStatus.CONFIRMED,
            to_status=EventStatus.COMPLETED,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
        )
        return self._replace(
            replace(
                existing, status=EventStatus.COMPLETED, updated_at=at,
                history=(*existing.history, entry),
            )
        )

    def plan_event(self, event_id: int, *, actor_id: int) -> Event:
        return self.decide_event(
            event_id, actor_id=actor_id, from_status=EventStatus.APPROVED,
            to_status=EventStatus.PLANNING, reason="",
        )

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event:
        """Readiness is the route's check here; the real store's RPC repeats it."""
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not EventStatus.PLANNING or existing.coordinator_id != actor_id:
            raise StaleEventStatus
        return self.decide_event(
            event_id, actor_id=actor_id, from_status=EventStatus.PLANNING,
            to_status=EventStatus.PENDING_SAFETY_CHECK, reason="",
        )

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
    ) -> Event:
        return self.decide_event(
            event_id, actor_id=actor_id, from_status=EventStatus.PENDING_SAFETY_CHECK,
            to_status=to_status, reason=note,
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
