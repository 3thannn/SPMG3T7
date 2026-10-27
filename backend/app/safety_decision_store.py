"""US17.2: the Safety Officer's decisions and the re-review flags they raise.

Backed by `safety_reviews` (one row per decision) and `safety_review_flags`
(one row per venue booking or equipment line a request for changes flagged),
added by SUPABASE_US17_2_SAFETY_DECISIONS.sql. The rules about who may decide
and what a decision may carry live in `app.safety_decisions` and the routes;
this module reads and writes.

Recording a decision is one RPC, `record_safety_decision`, so the event's move,
its US4.2 audit entry, the decision and its flags land together or not at all.
The RPC locks the event and re-checks that it is still in the same stay in
Pending Safety Check, so a decision that lost a race is reported as stale
rather than overwriting the one that won.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from app import event_store, supabase_client
from app.event_status import EventStatus
from app.event_store import StaleEventStatus
from app.safety_decisions import SafetyOutcome, same_check, to_status
from app.safety_review import entered_safety_check

TABLE = "safety_reviews"
FLAGS_TABLE = "safety_review_flags"
FLAG_COLUMNS = (
    "id, decision_id, event_id, booking_id, equipment_request_id, resolved_at, "
    "resolved_by_id, resolved_by:users!safety_review_flags_resolved_by_id_fkey(name)"
)
COLUMNS = (
    "id, event_id, outcome, note, decided_by_id, decided_at, check_started_at, "
    "decided_by:users!safety_reviews_decided_by_id_fkey(name), "
    f"safety_review_flags({FLAG_COLUMNS})"
)


@dataclass(frozen=True)
class ReviewFlag:
    """One arrangement a request for changes flagged for re-review.

    Exactly one of `booking_id` and `equipment_request_id` is set; the table's
    CHECK holds that.
    """

    id: int
    decision_id: int
    event_id: int
    booking_id: int | None = None
    equipment_request_id: int | None = None
    #: Empty while open. Set when the assigned Coordinator marks it re-reviewed.
    resolved_at: str = ""
    resolved_by_id: int | None = None
    resolved_by_name: str = ""

    @property
    def is_open(self) -> bool:
        return not self.resolved_at


@dataclass(frozen=True)
class SafetyDecision:
    """One decision: what, why, who and when, and which stay it was made on."""

    id: int
    event_id: int
    outcome: SafetyOutcome
    note: str
    decided_by_id: int
    decided_by_name: str
    decided_at: str
    #: When the event entered the Pending Safety Check this decision ended.
    check_started_at: str
    flags: tuple[ReviewFlag, ...] = ()


class StaleFlag(RuntimeError):
    """The flag was resolved, or is not this event's, by the time it was written."""


def _now() -> str:
    """A naive UTC timestamp, like every other recorded time."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _embedded_name(row: dict, key: str) -> str:
    """A joined `users(name)`, which PostgREST returns as an object or a list."""
    joined = row.get(key)
    if isinstance(joined, list):
        joined = joined[0] if joined else None
    return joined.get("name", "") if isinstance(joined, dict) else ""


def to_flag(row: dict) -> ReviewFlag:
    return ReviewFlag(
        id=row["id"],
        decision_id=row["decision_id"],
        event_id=row["event_id"],
        booking_id=row.get("booking_id"),
        equipment_request_id=row.get("equipment_request_id"),
        resolved_at=str(row.get("resolved_at") or ""),
        resolved_by_id=row.get("resolved_by_id"),
        resolved_by_name=_embedded_name(row, "resolved_by"),
    )


def to_decision(row: dict) -> SafetyDecision:
    return SafetyDecision(
        id=row["id"],
        event_id=row["event_id"],
        outcome=SafetyOutcome(row["outcome"]),
        note=row.get("note") or "",
        decided_by_id=row["decided_by_id"],
        decided_by_name=_embedded_name(row, "decided_by"),
        decided_at=str(row["decided_at"]),
        check_started_at=str(row["check_started_at"]),
        flags=tuple(
            sorted(
                (to_flag(flag) for flag in row.get("safety_review_flags") or ()),
                key=lambda flag: flag.id,
            )
        ),
    )


class Repository(Protocol):
    def record(
        self,
        event_id: int,
        *,
        officer_id: int,
        outcome: SafetyOutcome,
        note: str,
        check_started_at: str,
        booking_ids: tuple[int, ...],
        equipment_ids: tuple[int, ...],
    ) -> SafetyDecision: ...

    def list_for_event(self, event_id: int) -> list[SafetyDecision]: ...

    def get_flag(self, flag_id: int) -> ReviewFlag | None: ...

    def resolve_flag(self, flag_id: int, *, event_id: int, actor_id: int) -> ReviewFlag: ...


class SupabaseSafetyDecisions:
    """The real store. Goes through the service role client, like the others."""

    def record(
        self,
        event_id: int,
        *,
        officer_id: int,
        outcome: SafetyOutcome,
        note: str,
        check_started_at: str,
        booking_ids: tuple[int, ...],
        equipment_ids: tuple[int, ...],
    ) -> SafetyDecision:
        result = supabase_client.admin().rpc(
            "record_safety_decision",
            {
                "p_event_id": event_id,
                "p_outcome": str(outcome),
                "p_officer_id": officer_id,
                "p_note": note or None,
                "p_check_started_at": check_started_at or None,
                "p_booking_ids": list(booking_ids),
                "p_equipment_ids": list(equipment_ids),
            },
        ).execute()
        decision_id = result.data
        # NULL when the RPC refused. `type` rather than isinstance: a bool is an int.
        if type(decision_id) is not int:
            raise StaleEventStatus
        return next(item for item in self.list_for_event(event_id) if item.id == decision_id)

    def list_for_event(self, event_id: int) -> list[SafetyDecision]:
        """Newest first: the decision that matters now is the one on top."""
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("event_id", event_id)
            .order("decided_at", desc=True)
            .order("id", desc=True)
            .execute()
            .data
            or []
        )
        return [to_decision(row) for row in rows]

    def get_flag(self, flag_id: int) -> ReviewFlag | None:
        rows = (
            supabase_client.admin()
            .table(FLAGS_TABLE)
            .select(FLAG_COLUMNS)
            .eq("id", flag_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return to_flag(rows[0]) if rows else None

    def resolve_flag(self, flag_id: int, *, event_id: int, actor_id: int) -> ReviewFlag:
        """Resolve an open flag once. The filter on `resolved_at` makes it so."""
        rows = (
            supabase_client.admin()
            .table(FLAGS_TABLE)
            .update({"resolved_at": _now(), "resolved_by_id": actor_id})
            .eq("id", flag_id)
            .eq("event_id", event_id)
            .is_("resolved_at", "null")
            .execute()
            .data
            or []
        )
        if not rows:
            raise StaleFlag
        resolved = self.get_flag(flag_id)
        assert resolved is not None  # noqa: S101 - the row was just updated
        return resolved


@dataclass
class InMemorySafetyDecisions:
    """A stand-in for tests that moves the event through the in-memory event store.

    It makes the same checks the RPC does — still Pending Safety Check, still the
    same stay — so the routes' tests see the same refusals.
    """

    decisions: list[SafetyDecision] = field(default_factory=list)
    #: user id -> display name, standing in for the joined `users(name)`.
    names: dict[int, str] = field(default_factory=dict)
    next_id: int = 1
    next_flag_id: int = 1

    def record(
        self,
        event_id: int,
        *,
        officer_id: int,
        outcome: SafetyOutcome,
        note: str,
        check_started_at: str,
        booking_ids: tuple[int, ...],
        equipment_ids: tuple[int, ...],
    ) -> SafetyDecision:
        events = event_store.repository()
        existing = events.get_event(event_id)
        if existing is None or existing.status is not EventStatus.PENDING_SAFETY_CHECK:
            raise StaleEventStatus
        entered = entered_safety_check(existing)
        if check_started_at and not same_check(check_started_at, entered):
            raise StaleEventStatus
        moved = events.decide_safety_check(
            event_id, actor_id=officer_id, to_status=to_status(outcome), note=note
        )
        decision_id = self.next_id
        self.next_id += 1
        # A repeated id is flagged once, as the RPC's DISTINCT does.
        targets = [(booking_id, None) for booking_id in dict.fromkeys(booking_ids)] + [
            (None, line_id) for line_id in dict.fromkeys(equipment_ids)
        ]
        flags = []
        for booking_id, line_id in targets:
            flags.append(
                ReviewFlag(
                    id=self.next_flag_id,
                    decision_id=decision_id,
                    event_id=event_id,
                    booking_id=booking_id,
                    equipment_request_id=line_id,
                )
            )
            self.next_flag_id += 1
        decision = SafetyDecision(
            id=decision_id,
            event_id=event_id,
            outcome=outcome,
            note=note,
            decided_by_id=officer_id,
            decided_by_name=self.names.get(officer_id, ""),
            decided_at=moved.updated_at,
            check_started_at=entered,
            flags=tuple(flags),
        )
        self.decisions.append(decision)
        return decision

    def list_for_event(self, event_id: int) -> list[SafetyDecision]:
        return sorted(
            (item for item in self.decisions if item.event_id == event_id),
            key=lambda item: (item.decided_at, item.id),
            reverse=True,
        )

    def get_flag(self, flag_id: int) -> ReviewFlag | None:
        return next(
            (flag for item in self.decisions for flag in item.flags if flag.id == flag_id),
            None,
        )

    def resolve_flag(self, flag_id: int, *, event_id: int, actor_id: int) -> ReviewFlag:
        flag = self.get_flag(flag_id)
        if flag is None or flag.event_id != event_id or not flag.is_open:
            raise StaleFlag
        resolved = replace(
            flag,
            resolved_at=_now(),
            resolved_by_id=actor_id,
            resolved_by_name=self.names.get(actor_id, ""),
        )
        self.decisions = [
            replace(
                item,
                flags=tuple(resolved if each.id == flag_id else each for each in item.flags),
            )
            for item in self.decisions
        ]
        return resolved


_repository: Repository = SupabaseSafetyDecisions()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
