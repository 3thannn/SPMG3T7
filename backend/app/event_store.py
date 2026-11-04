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
    REQUESTABLE,
    ChangeReview,
    FieldChange,
    applied_values,
    change_type,
    diff,
    edit_reopen_reason,
    ordered,
    reopen_reason,
    reopens_planning,
)
from app.event_needs import NEED_FIELDS, NO_NEEDS, EventNeeds
from app.event_status import CLOSED, EventStatus, check_completion

EVENTS_TABLE = "events"
CHANGES_TABLE = "status_changes"
EVENT_CHANGES_TABLE = "event_changes"
#: US11.1: an Organiser's proposed changes, kept apart from `event_changes` —
#: which records changes that were applied — until a Coordinator approves them.
CHANGE_REQUESTS_TABLE = "event_change_requests"

# US8.1: Two foreign keys to users now exist (organiser_id, coordinator_id),
# so PostgREST requires explicit relationship qualification via constraint name.
# US8.4: Fetch both organiser and coordinator names via separate joins.
EVENT_COLUMNS = (
    "id, name, purpose, description, proposed_date, end_date, expected_attendance, "
    "venue_requirements, preferred_layout, accessibility_needs, equipment_needs, "
    "registration_needs, "
    "status, organiser_id, coordinator_id, created_at, updated_at, submitted_at, "
    "review_state, arrangement_review_pending, arrangement_review, "
    "organiser:users!events_organiser_id_fkey(name), "
    "coordinator:users!events_coordinator_id_fkey(name)"
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
    #: US8.4: The assigned Event Coordinator's name, or empty if unassigned.
    coordinator_name: str = ""
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

    review_state: dict = field(default_factory=dict)
    arrangement_review_pending: bool = False
    arrangement_review: tuple[dict, ...] = ()

    @property
    def needs(self) -> EventNeeds:
        return EventNeeds(**{name: getattr(self, name) for name in NEED_FIELDS})


class StaleEventStatus(RuntimeError):
    """The event changed after the route checked its current status."""


@dataclass(frozen=True)
class CancelledEvent:
    """US4.6: the event as cancelled, and what the cancellation gave back.

    The ids are the ones this cancellation moved, so a booking cancelled or a
    line removed earlier is not reported as released again.
    """

    event: Event
    #: Venue bookings moved to Cancelled: every one that still held its venue.
    booking_ids: tuple[int, ...] = ()
    #: Equipment lines moved to Removed: every one not already removed.
    equipment_ids: tuple[int, ...] = ()
    #: Registrations moved to Event Cancelled: every one still Registered (US20.1).
    registration_ids: tuple[int, ...] = ()


def _now() -> str:
    """A naive UTC timestamp, to the microsecond as Postgres records it. See the module docstring.

    Seconds were not enough: a safety check sent back and resubmitted within one
    second looked like the same check, so its approval was refused as already
    decided (seen in the e2e safety journey).
    """
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")


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
    answered = [
        row
        for row in requests
        if row.get("status") in ("approved", "rejected") and row.get("reviewed_at")
    ]
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
    # US8.4: Extract both organiser and coordinator names from aliased joins
    organiser_joined = row.get("organiser")
    organiser_name = organiser_joined.get("name", "") if isinstance(organiser_joined, dict) else ""

    coordinator_joined = row.get("coordinator")
    coordinator_name = (
        coordinator_joined.get("name", "") if isinstance(coordinator_joined, dict) else ""
    )

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
        organiser_name=organiser_name,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        review_state=row.get("review_state") or {},
        arrangement_review_pending=row.get("arrangement_review_pending", False),
        arrangement_review=tuple(row.get("arrangement_review") or []),
        coordinator_id=row.get("coordinator_id"),
        coordinator_name=coordinator_name,
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
    def set_arrangement_review(
        self,
        event_id: int,
        report: list[dict],
        pending: bool,
        expected_updated_at: str | None = None,
        booking_flags: list[dict] | None = None,
        equipment_flags: list[dict] | None = None,
    ) -> Event: ...

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
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        message: str,
        expected_revision: int | None = None,
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
        expected_revision: int | None = None,
    ) -> Event: ...

    def resolve_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        approve: bool,
        note: str,
        expected_revision: int | None = None,
    ) -> Event: ...

    def assign_coordinator(
        self, event_id: int, coordinator_id: int, assigned_by_id: int
    ) -> Event: ...

    def reassign_coordinator(
        self,
        event_id: int,
        coordinator_id: int,
        *,
        reassigned_by_id: int,
        expected_updated_at: str,
    ) -> Event: ...

    def complete_event(self, event_id: int, *, actor_id: int) -> Event: ...

    def plan_event(self, event_id: int, *, actor_id: int) -> Event: ...

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event: ...

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
    ) -> Event: ...

    def confirm_event(self, event_id: int, *, actor_id: int) -> Event: ...

    def cancel_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, reason: str
    ) -> CancelledEvent: ...


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
            .data
            or []
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
        proposed = replace(
            previous_event,
            title=title,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at or "",
            expected_attendance=expected_attendance,
            **needs.as_attrs(),
        )
        changes = diff(previous_event, proposed)
        result = (
            supabase_client.admin()
            .rpc(
                "us11_edit",
                {
                    "p_event_id": event_id,
                    "p_actor_id": editor_id,
                    "p_updated_at": previous_event.updated_at,
                    "p_changes": [
                        {
                            "changed_field": c.field,
                            "old_value": c.old_value,
                            "new_value": c.new_value,
                            "change_type": change_type(c),
                        }
                        for c in changes
                    ],
                    # D1: the database decides whether the edit reopens Planning;
                    # this is only the words its history entry carries.
                    "p_reason": edit_reopen_reason(changes),
                },
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        saved = self.get_event(event_id)
        assert saved is not None  # noqa: S101
        return saved

    def submit_event(self, event_id: int, *, actor_id: int, from_status: EventStatus) -> Event:
        """Move the event and write the audit entry US4.2 requires.

        US8.2: Auto-assignment is now OFF. Events remain unassigned on submit.
        D2: a resubmitted Rejected event returns to the unassigned queue, so its
        earlier Coordinator is cleared and the Lead assigns it again."""
        at = _now()
        values = {
            "status": str(EventStatus.SUBMITTED),
            "submitted_at": at,
            "updated_at": at,
        }
        if from_status is EventStatus.REJECTED:
            values["coordinator_id"] = None
        supabase_client.admin().table(EVENTS_TABLE).update(values).eq("id", event_id).execute()
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

    def _workflow(
        self,
        event_id: int,
        actor_id: int,
        action: str,
        payload: dict,
        expected_revision: int | None,
    ) -> Event:
        event = self.get_event(event_id)
        if event is None:
            raise StaleEventStatus
        revision = event.review_state.get("revision", 0)
        params = {
            "p_event_id": event_id,
            "p_actor_id": actor_id,
            "p_action": action,
            "p_revision": revision if expected_revision is None else expected_revision,
            "p_payload": payload,
        }
        rpc = "us11_review"
        if action == "approve":
            # US11.3: one call applies the changes and, on a Confirmed event with
            # an important one, moves it back to Planning, so neither lands
            # without the other. The database decides whether it moves; the
            # reason is only the words its history entry carries.
            rpc = "us11_approve_change"
            del params["p_action"]
            params["p_reason"] = reopen_reason(event.pending_changes)
        result = supabase_client.admin().rpc(rpc, params).execute()
        if result.data is not True:
            raise StaleEventStatus
        updated = self.get_event(event_id)
        assert updated is not None  # noqa: S101
        return updated

    def request_clarification(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        message: str,
        expected_revision: int | None = None,
    ) -> Event:
        return self._workflow(
            event_id, actor_id, "clarify", {"message": message}, expected_revision
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
        """US7.1: atomically record one Coordinator decision and its audit entry.

        Transition validation remains in Python. The RPC is only the transaction
        boundary needed to prevent a final status without its required US4.2
        audit row.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "decide_event_status",
                {
                    "p_event_id": event_id,
                    "p_expected_status": str(from_status),
                    "p_new_status": str(to_status),
                    "p_changed_by_id": actor_id,
                    "p_notes": reason or None,
                },
            )
            .execute()
        )
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
        expected_revision: int | None = None,
    ) -> Event:
        return self._workflow(
            event_id,
            actor_id,
            "submit",
            {
                "note": note,
                "changes": [
                    {
                        "changed_field": c.field,
                        "old_value": c.old_value,
                        "new_value": c.new_value,
                        "change_type": change_type(c),
                    }
                    for c in changes
                ],
            },
            expected_revision,
        )

    def resolve_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        approve: bool,
        note: str,
        expected_revision: int | None = None,
    ) -> Event:
        return self._workflow(
            event_id,
            actor_id,
            "approve" if approve else "reject",
            {"note": note},
            expected_revision,
        )

    def set_arrangement_review(
        self,
        event_id: int,
        report: list[dict],
        pending: bool,
        expected_updated_at: str | None = None,
        booking_flags: list[dict] | None = None,
        equipment_flags: list[dict] | None = None,
    ) -> Event:
        # The RPC checks the event version before writing any flags or report.
        if expected_updated_at is None:
            current = self.get_event(event_id)
            assert current is not None  # noqa: S101
            expected_updated_at = current.updated_at
        supabase_client.admin().rpc(
            "us11_commit_arrangement_review",
            {
                "p_event_id": event_id,
                "p_updated_at": expected_updated_at,
                "p_report": report,
                "p_pending": pending,
                "p_booking_flags": booking_flags or [],
                "p_equipment_flags": equipment_flags or [],
            },
        ).execute()
        event = self.get_event(event_id)
        assert event is not None  # noqa: S101
        return event

    def assign_coordinator(self, event_id: int, coordinator_id: int, assigned_by_id: int) -> Event:
        """Assign and audit Submitted -> Under Review in one transaction."""
        result = (
            supabase_client.admin()
            .rpc(
                "assign_event_coordinator",
                {
                    "p_event_id": event_id,
                    "p_coordinator_id": coordinator_id,
                    "p_assigned_by_id": assigned_by_id,
                },
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        assigned = self.get_event(event_id)
        assert assigned is not None  # noqa: S101 - the row was just updated
        return assigned

    def reassign_coordinator(
        self,
        event_id: int,
        coordinator_id: int,
        *,
        reassigned_by_id: int,
        expected_updated_at: str,
    ) -> Event:
        """US8.4: reassign_event_coordinator, in one transaction.

        It re-checks what the route checked (a Lead reassigning an assigned,
        active event to a Coordinator) and that the event has not changed since
        `expected_updated_at`, then moves it, logs it and notifies both
        Coordinators. Anything else is reported as stale.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "reassign_event_coordinator",
                {
                    "p_event_id": event_id,
                    "p_coordinator_id": coordinator_id,
                    "p_assigned_by_id": reassigned_by_id,
                    "p_expected_updated_at": expected_updated_at,
                },
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        reassigned = self.get_event(event_id)
        assert reassigned is not None  # noqa: S101 - the row was just updated
        return reassigned

    def complete_event(self, event_id: int, *, actor_id: int) -> Event:
        """Complete only an ended Confirmed event, with its audit entry."""
        result = (
            supabase_client.admin()
            .rpc(
                "complete_event_status",
                {"p_event_id": event_id, "p_coordinator_id": actor_id},
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        completed = self.get_event(event_id)
        assert completed is not None  # noqa: S101 - the row was just updated
        return completed

    def plan_event(self, event_id: int, *, actor_id: int) -> Event:
        return self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=EventStatus.APPROVED,
            to_status=EventStatus.PLANNING,
            reason="",
        )

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event:
        """US4.4: Planning -> Pending Safety Check, with its audit entry.

        The RPC locks the event and re-checks readiness — every active booking
        Confirmed and unflagged, no outstanding equipment line, no pending
        change request — so a booking or line that changed after the route's
        check is reported as stale rather than slipping through.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "send_event_to_safety_check",
                {"p_event_id": event_id, "p_coordinator_id": actor_id},
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        sent = self.get_event(event_id)
        assert sent is not None  # noqa: S101 - the row was just updated
        return sent

    def confirm_event(self, event_id: int, *, actor_id: int) -> Event:
        """US4.7: Pending Safety Check -> Confirmed, by the assigned Coordinator.

        The RPC locks the event and repeats every check the route made — the
        safety approval of this stay, the venues, the equipment, the change
        request — so something that changed after the route's check is
        reported as stale rather than confirmed. It is the only way into
        Confirmed: the database refuses every other route there.
        """
        result = (
            supabase_client.admin()
            .rpc("confirm_event", {"p_event_id": event_id, "p_coordinator_id": actor_id})
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        confirmed = self.get_event(event_id)
        assert confirmed is not None  # noqa: S101 - the row was just updated
        return confirmed

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
    ) -> Event:
        """US4.4: Pending Safety Check -> back to Planning, audited. US4.7 took
        Confirmed away from it: only `confirm_event` gets there now.

        The RPC only moves an event that is still Pending Safety Check, and
        only for a Safety Officer, so a second decision on the same check
        fails rather than overwriting the first.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "decide_safety_check",
                {
                    "p_event_id": event_id,
                    "p_new_status": str(to_status),
                    "p_officer_id": actor_id,
                    "p_notes": note or None,
                },
            )
            .execute()
        )
        if result.data is not True:
            raise StaleEventStatus
        decided = self.get_event(event_id)
        assert decided is not None  # noqa: S101 - the row was just updated
        return decided

    def cancel_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, reason: str
    ) -> CancelledEvent:
        """US4.6: Cancelled, with its audit entry, and everything it held released.

        One RPC, so the status, the history row, the cancelled bookings and the
        removed equipment lines land together or not at all. It locks the
        event, re-checks the status and that the actor owns it or is assigned
        to it, and answers null - changing nothing - when any of that fails.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "cancel_event",
                {
                    "p_event_id": event_id,
                    "p_expected_status": str(from_status),
                    "p_actor_id": actor_id,
                    "p_reason": reason,
                },
            )
            .execute()
        )
        released = result.data
        if not isinstance(released, dict):
            raise StaleEventStatus
        cancelled = self.get_event(event_id)
        assert cancelled is not None  # noqa: S101 - the row was just updated
        return CancelledEvent(
            event=cancelled,
            booking_ids=tuple(released.get("bookings") or ()),
            equipment_ids=tuple(released.get("equipment") or ()),
            # Absent until SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql is applied.
            registration_ids=tuple(released.get("registrations") or ()),
        )


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

    def reopen_for_replacement(self, event_id: int, *, actor_id: int, reason: str) -> None:
        """US12.4: what us12_4_request_replacement does to the event in the real store.

        Called by `InMemoryBookings.request_replacement` once the booking is
        replaced, as the real function does it in the same transaction.
        """
        existing = self.get_event(event_id)
        if existing is None or existing.status is not EventStatus.CONFIRMED:
            return
        at = _now()
        self._replace(
            replace(
                existing,
                status=EventStatus.PLANNING,
                updated_at=at,
                history=(
                    *existing.history,
                    StatusChange(
                        from_status=EventStatus.CONFIRMED,
                        to_status=EventStatus.PLANNING,
                        at=at,
                        by_id=actor_id,
                        by_name=self.names.get(actor_id, ""),
                        notes=reason,
                    ),
                ),
            )
        )

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
        current = self.get_event(event_id)
        if (
            current is None
            or current.change_requested
            or current.updated_at != previous_event.updated_at
        ):
            raise StaleEventStatus
        proposed = replace(
            current,
            title=title,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at or "",
            expected_attendance=expected_attendance,
            **needs.as_attrs(),
        )
        changes = diff(current, proposed)
        self.change_log.extend((event_id, c) for c in changes)
        pending = any(
            c.field in ("proposed_date", "end_date", "expected_attendance") for c in changes
        )
        saved = self.save_event(
            event_id,
            title=title,
            purpose=purpose,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            expected_attendance=expected_attendance,
            needs=needs,
        )
        saved = replace(
            saved, arrangement_review_pending=pending or current.arrangement_review_pending
        )
        # D1: what us11_edit does in the real store. An important edit during the
        # safety check sends the event back to Planning, so no decision made
        # about the old details can confirm it.
        if reopens_planning(status=current.status, changes=changes):
            at = _now()
            saved = replace(
                saved,
                status=EventStatus.PLANNING,
                updated_at=at,
                history=(
                    *saved.history,
                    StatusChange(
                        from_status=current.status,
                        to_status=EventStatus.PLANNING,
                        at=at,
                        by_id=editor_id,
                        by_name=self.names.get(editor_id, ""),
                        notes=edit_reopen_reason(changes),
                    ),
                ),
            )
        return self._replace(saved)

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
                # D2: a resubmitted Rejected event goes back to the Lead's queue.
                coordinator_id=(
                    None if from_status is EventStatus.REJECTED else existing.coordinator_id
                ),
            )
        )

    def _review_state(self, event: Event, actor_id: int, kind: str, **payload) -> dict:
        state = dict(event.review_state)
        revision = state.get("revision", 0) + 1
        entry = {
            "revision": revision,
            "kind": kind,
            "byId": str(actor_id),
            "clarificationId": revision
            if kind == "clarification"
            else state.get("clarificationId"),
            "byName": self.names.get(actor_id, ""),
            "at": _now(),
            **payload,
        }
        return {**state, "revision": revision, "messages": [*state.get("messages", []), entry]}

    def request_clarification(
        self,
        event_id: int,
        *,
        actor_id: int,
        from_status: EventStatus,
        message: str,
        expected_revision: int | None = None,
    ) -> Event:
        event = self.get_event(event_id)
        if (
            event is None
            or event.status != from_status
            or (
                expected_revision is not None
                and expected_revision != event.review_state.get("revision", 0)
            )
        ):
            raise StaleEventStatus
        state = self._review_state(event, actor_id, "clarification", message=message)
        state.update(awaitingReply=True, clarificationId=state["revision"])
        at = _now()
        entry = StatusChange(
            from_status=from_status,
            to_status=from_status,
            at=at,
            by_id=actor_id,
            by_name=self.names.get(actor_id, ""),
            notes=message,
        )
        return self._replace(
            replace(event, updated_at=at, review_state=state, history=(*event.history, entry))
        )

    def set_arrangement_review(
        self,
        event_id: int,
        report: list[dict],
        pending: bool,
        expected_updated_at: str | None = None,
        booking_flags: list[dict] | None = None,
        equipment_flags: list[dict] | None = None,
    ) -> Event:
        event = self.get_event(event_id)
        assert event is not None  # noqa: S101
        if expected_updated_at is not None and event.updated_at != expected_updated_at:
            return event
        from app import booking_store, equipment_store

        bookings = booking_store.repository()
        equipment = equipment_store.repository()
        assert isinstance(bookings, booking_store.InMemoryBookings)  # noqa: S101
        assert isinstance(equipment, equipment_store.InMemoryEquipment)  # noqa: S101
        # Validate the complete read set before writing any metadata.
        for flag in booking_flags or []:
            row = bookings.get_booking(flag["id"])
            if (
                row is None
                or row.event_id != event_id
                or (
                    str(row.status),
                    datetime.fromisoformat(row.starts_at),
                    datetime.fromisoformat(row.ends_at),
                    row.headcount,
                )
                != (
                    flag["status"],
                    datetime.fromisoformat(flag["startsAt"]),
                    datetime.fromisoformat(flag["endsAt"]),
                    flag["headcount"],
                )
            ):
                return self._replace(replace(event, arrangement_review_pending=True))
        for flag in equipment_flags or []:
            row = equipment.get_request(flag["id"])
            if (
                row is None
                or row.event_id != event_id
                or (row.status, row.version) != (flag["status"], flag["version"])
            ):
                return self._replace(replace(event, arrangement_review_pending=True))
        for flag in booking_flags or []:
            row = bookings.get_booking(flag["id"])
            if row.event_conflict_reason != flag["reason"]:
                bookings._set_event_conflict(row.id, flag["reason"])
        for flag in equipment_flags or []:
            row = equipment.get_request(flag["id"])
            if row.event_conflict_reason != flag["reason"]:
                equipment._set_event_conflict(row.id, flag["reason"])
        return self._replace(
            replace(event, arrangement_review=tuple(report), arrangement_review_pending=pending)
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
        expected_revision: int | None = None,
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if (
            existing.status is not from_status
            or (existing.change_requested and not existing.review_state.get("awaitingReply"))
            or (
                expected_revision is not None
                and expected_revision != existing.review_state.get("revision", 0)
            )
        ):
            raise StaleEventStatus
        self.change_requests = [
            (eid, c, "superseded" if eid == event_id and status == "pending" else status)
            for eid, c, status in self.change_requests
        ]
        self.change_requests.extend((event_id, change, "pending") for change in changes)
        state = self._review_state(
            existing,
            actor_id,
            "proposal",
            message=note,
            changes=[
                {"field": c.field, "oldValue": c.old_value, "newValue": c.new_value}
                for c in changes
            ],
        )
        state["awaitingReply"] = False
        return self._replace(
            replace(
                existing,
                updated_at=_now(),
                change_requested=True,
                pending_changes=ordered(changes),
                change_request_note=note,
                review_state=state,
            )
        )

    def resolve_change_request(
        self,
        event_id: int,
        *,
        actor_id: int,
        approve: bool,
        note: str,
        expected_revision: int | None = None,
    ) -> Event:
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if (
            not existing.change_requested
            or existing.status not in (*REQUESTABLE, EventStatus.UNDER_REVIEW)
            or (
                expected_revision is not None
                and expected_revision != existing.review_state.get("revision", 0)
            )
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
        # US11.3: what us11_approve_change does in the real store.
        reopened = approve and reopens_planning(
            status=existing.status, changes=existing.pending_changes
        )
        history = existing.history
        if reopened:
            history = (
                *history,
                StatusChange(
                    from_status=existing.status,
                    to_status=EventStatus.PLANNING,
                    at=at,
                    by_id=actor_id,
                    by_name=self.names.get(actor_id, ""),
                    notes=reopen_reason(existing.pending_changes),
                ),
            )
        return self._replace(
            replace(
                existing,
                **applied,
                status=EventStatus.PLANNING if reopened else existing.status,
                history=history,
                review_state={
                    **self._review_state(existing, actor_id, outcome, message=note),
                    "awaitingReply": False,
                },
                arrangement_review_pending=approve
                and any(
                    c.field in ("proposed_date", "end_date", "expected_attendance")
                    for c in existing.pending_changes
                )
                or existing.arrangement_review_pending,
                updated_at=at,
                change_requested=False,
                pending_changes=(),
                change_request_note="",
                last_change_review=ChangeReview(
                    outcome=outcome,
                    at=at,
                    note=note,
                    request_note=existing.change_request_note,
                ),
            )
        )

    def assign_coordinator(self, event_id: int, coordinator_id: int, assigned_by_id: int) -> Event:
        """US8.3: what assign_event_coordinator does: Submitted -> Under Review.

        A first assignment only, as in the database. Reassigning an event that
        already has a Coordinator is `reassign_coordinator` (US8.4).
        """
        existing = self.get_event(event_id)
        if (
            existing is None
            or existing.status is not EventStatus.SUBMITTED
            or existing.coordinator_id is not None
        ):
            raise StaleEventStatus
        at = _now()
        return self._replace(
            replace(
                existing,
                coordinator_id=coordinator_id,
                coordinator_name=self.names.get(coordinator_id, ""),
                status=EventStatus.UNDER_REVIEW,
                updated_at=at,
                history=(
                    *existing.history,
                    StatusChange(
                        from_status=EventStatus.SUBMITTED,
                        to_status=EventStatus.UNDER_REVIEW,
                        at=at,
                        by_id=assigned_by_id,
                        by_name=self.names.get(assigned_by_id, ""),
                    ),
                ),
            )
        )

    def reassign_coordinator(
        self,
        event_id: int,
        coordinator_id: int,
        *,
        reassigned_by_id: int,
        expected_updated_at: str,
    ) -> Event:
        """US8.4: what reassign_event_coordinator does, including its notices."""
        # Imported here: both modules import this one.
        from app import booking_store, notifications, reassignment

        existing = self.get_event(event_id)
        if (
            existing is None
            or existing.coordinator_id is None
            or existing.status in CLOSED
            or existing.updated_at != expected_updated_at
        ):
            raise StaleEventStatus
        previous = existing.coordinator_id
        if previous == coordinator_id:
            return existing
        at = _now()
        reassigned = self._replace(
            replace(
                existing,
                coordinator_id=coordinator_id,
                coordinator_name=self.names.get(coordinator_id, ""),
                updated_at=at,
                history=(
                    *existing.history,
                    StatusChange(
                        from_status=existing.status,
                        to_status=existing.status,
                        at=at,
                        by_id=reassigned_by_id,
                        by_name=self.names.get(reassigned_by_id, ""),
                        notes=reassignment.note(
                            self.names.get(previous) or f"Coordinator {previous}",
                            self.names.get(coordinator_id) or f"Coordinator {coordinator_id}",
                        ),
                    ),
                ),
            )
        )
        notifications.notify_reassigned(reassigned, previous, coordinator_id)
        if any(
            booking.status is booking_store.BookingStatus.NEEDS_REPLACEMENT
            for booking in booking_store.repository().list_for_event(event_id)
        ):
            notifications.notify_handover_needs_replacement(reassigned)
        return reassigned

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
                existing,
                status=EventStatus.COMPLETED,
                updated_at=at,
                history=(*existing.history, entry),
            )
        )

    def plan_event(self, event_id: int, *, actor_id: int) -> Event:
        return self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=EventStatus.APPROVED,
            to_status=EventStatus.PLANNING,
            reason="",
        )

    def send_to_safety_check(self, event_id: int, *, actor_id: int) -> Event:
        """Readiness is the route's check here; the real store's RPC repeats it."""
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if existing.status is not EventStatus.PLANNING or existing.coordinator_id != actor_id:
            raise StaleEventStatus
        return self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=EventStatus.PLANNING,
            to_status=EventStatus.PENDING_SAFETY_CHECK,
            reason="",
        )

    def decide_safety_check(
        self, event_id: int, *, actor_id: int, to_status: EventStatus, note: str
    ) -> Event:
        return self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=EventStatus.PENDING_SAFETY_CHECK,
            to_status=to_status,
            reason=note,
        )

    def confirm_event(self, event_id: int, *, actor_id: int) -> Event:
        """The RPC's status and assignment checks; readiness is the route's here."""
        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        if (
            existing.status is not EventStatus.PENDING_SAFETY_CHECK
            or existing.coordinator_id != actor_id
        ):
            raise StaleEventStatus
        return self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=EventStatus.PENDING_SAFETY_CHECK,
            to_status=EventStatus.CONFIRMED,
            reason="",
        )

    def cancel_event(
        self, event_id: int, *, actor_id: int, from_status: EventStatus, reason: str
    ) -> CancelledEvent:
        """The RPC's checks and writes, against the in-memory stores beside this one.

        Imported here because all three of those stores import this module.
        """
        from app import booking_store, equipment_store, registration_store

        existing = self.get_event(event_id)
        assert existing is not None  # noqa: S101 - the caller checked it exists
        may_cancel = actor_id == existing.organiser_id or (
            actor_id == existing.coordinator_id and existing.status is not EventStatus.DRAFT
        )
        if existing.status is not from_status or from_status in CLOSED or not may_cancel:
            raise StaleEventStatus
        bookings = booking_store.repository()
        equipment = equipment_store.repository()
        assert isinstance(bookings, booking_store.InMemoryBookings)  # noqa: S101
        assert isinstance(equipment, equipment_store.InMemoryEquipment)  # noqa: S101
        registrations = registration_store.repository()
        assert isinstance(registrations, registration_store.InMemoryRegistrations)  # noqa: S101
        cancelled = self.decide_event(
            event_id,
            actor_id=actor_id,
            from_status=from_status,
            to_status=EventStatus.CANCELLED,
            reason=reason,
        )
        return CancelledEvent(
            event=cancelled,
            booking_ids=bookings.release_for_event(event_id, actor_id=actor_id, reason=reason),
            equipment_ids=equipment.release_for_event(event_id, actor_id=actor_id),
            registration_ids=registrations.cancel_for_event(event_id),
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
