"""Venue blackout periods, backed by the Supabase `venue_unavailability` table — US12.1, US12.2.

Venue Staff mark the date ranges a venue cannot be used (maintenance, closure),
and Coordinators read them while planning. This module is only the access; who
may do which is the routes' business, as it is for `venue_store`.

Three choices worth knowing:

* A range is inclusive at both ends and whole days only. `start_date` and
  `end_date` are Postgres DATE columns, so a one-day closure is a range whose
  start and end are the same day — not a zero-length range to be refused.
* Nothing here compares a range with anything else. Ranges may overlap one
  another, and nothing checks them against venue bookings (US14.1) here. That
  is US15.1's availability check, and it belongs with the booking request, not
  in this store.
* The table has its own `CHECK (end_date >= start_date)`. The route validates
  first and says why in a sentence; the constraint is there so a row that slips
  past the API cannot exist either.

US12.2 additions:
* `reason_type` is a structured enum (maintenance, equipment_failure, renovation,
  safety_concern, or other) that replaces the free-text `reason` field.
* When `reason_type` is "other", `other_reason` must be provided with custom text.
* A database trigger automatically flags affected bookings as "Needs replacement"
  and notifies the assigned Coordinator when an unavailability period is created.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol

from app import supabase_client
from app.venue_store import _now

TABLE = "venue_unavailability"
COLUMNS = "id, venue_id, start_date, end_date, reason_type, other_reason, created_by_id, created_at"


class UnavailabilityReasonType(StrEnum):
    """US12.2: Structured reasons for venue unavailability."""

    MAINTENANCE = "maintenance"
    EQUIPMENT_FAILURE = "equipment_failure"
    RENOVATION = "renovation"
    SAFETY_CONCERN = "safety_concern"
    OTHER = "other"


@dataclass(frozen=True)
class Unavailability:
    id: int
    venue_id: int
    start_date: date
    end_date: date
    #: US12.2: Structured reason type (maintenance, equipment_failure, etc.)
    reason_type: UnavailabilityReasonType
    #: US12.2: Custom reason text when reason_type = "other", otherwise empty string
    other_reason: str
    #: Who marked it. Nullable so removing a user does not remove the record
    #: of a closure they entered.
    created_by_id: int | None
    created_at: str


def _as_date(value: object) -> date:
    """PostgREST sends DATE as "YYYY-MM-DD"; `str` also covers a `date` passed through."""
    return date.fromisoformat(str(value))


def to_unavailability(row: dict) -> Unavailability:
    return Unavailability(
        id=row["id"],
        venue_id=row["venue_id"],
        start_date=_as_date(row["start_date"]),
        end_date=_as_date(row["end_date"]),
        reason_type=UnavailabilityReasonType(row.get("reason_type", "other")),
        other_reason=row.get("other_reason") or "",
        created_by_id=row.get("created_by_id"),
        created_at=str(row["created_at"]) if row.get("created_at") else "",
    )


class Repository(Protocol):
    """What the routes need from a blackout store."""

    def list_for_venue(self, venue_id: int) -> list[Unavailability]: ...

    def venues_unavailable_between(self, start: date, end: date) -> frozenset[int]: ...

    def create(
        self,
        *,
        venue_id: int,
        start_date: date,
        end_date: date,
        reason_type: UnavailabilityReasonType,
        other_reason: str,
        created_by_id: int,
    ) -> Unavailability: ...


class SupabaseUnavailability:
    """The real store. Goes through the service role client, like the others."""

    def list_for_venue(self, venue_id: int) -> list[Unavailability]:
        """Soonest first — the order a Coordinator scans a calendar in.

        `end_date` and then `id` break ties, so two ranges starting the same day
        come back in the same order every time rather than whichever Postgres
        happened to read first.
        """
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("venue_id", venue_id)
            .order("start_date")
            .order("end_date")
            .order("id")
            .execute()
            .data
            or []
        )
        return [to_unavailability(row) for row in rows]

    def venues_unavailable_between(self, start: date, end: date) -> frozenset[int]:
        """Venues with any blackout touching `start`..`end`, both ends included.

        Two inclusive ranges overlap when each starts no later than the other
        ends, which is the whole of the test — a closure on the 6th rules out a
        window ending on the 6th, and one ending on the 1st does not touch a
        window starting on the 2nd.
        """
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select("venue_id")
            .lte("start_date", end.isoformat())
            .gte("end_date", start.isoformat())
            .execute()
            .data
            or []
        )
        return frozenset(row["venue_id"] for row in rows)

    def create(
        self,
        *,
        venue_id: int,
        start_date: date,
        end_date: date,
        reason_type: UnavailabilityReasonType,
        other_reason: str,
        created_by_id: int,
    ) -> Unavailability:
        """US12.1/US12.2: record one blackout period against one venue.

        The insert's own response is the stored row, defaults applied, so there
        is no second read. An empty other_reason is stored as NULL when
        reason_type is not "other".

        US12.2: A database trigger automatically flags affected bookings and
        notifies Coordinators when the unavailability is created.
        """
        # Handle both enum and string values for backwards compatibility
        reason_value = (
            reason_type.value
            if isinstance(reason_type, UnavailabilityReasonType)
            else reason_type
        )
        row = {
            "venue_id": venue_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "reason_type": reason_value,
            "other_reason": other_reason or None,
            "created_by_id": created_by_id,
            "created_at": _now(),
        }
        created = supabase_client.admin().table(TABLE).insert(row).execute()
        return to_unavailability(created.data[0])


def _sort_key(entry: Unavailability) -> tuple[date, date, int]:
    return (entry.start_date, entry.end_date, entry.id)


@dataclass
class InMemoryUnavailability:
    """A stand-in for tests, ordered the way the real query is."""

    entries: list[Unavailability] = field(default_factory=list)
    #: Well clear of anything a fixture might use, so a created row is obvious.
    next_id: int = 100

    def list_for_venue(self, venue_id: int) -> list[Unavailability]:
        return sorted((e for e in self.entries if e.venue_id == venue_id), key=_sort_key)

    def venues_unavailable_between(self, start: date, end: date) -> frozenset[int]:
        """The same overlap test as the SQL above."""
        return frozenset(
            e.venue_id for e in self.entries if e.start_date <= end and e.end_date >= start
        )

    def create(
        self,
        *,
        venue_id: int,
        start_date: date,
        end_date: date,
        reason_type: UnavailabilityReasonType,
        other_reason: str,
        created_by_id: int,
    ) -> Unavailability:
        self.next_id += 1
        # Handle both enum and string values for backwards compatibility
        if isinstance(reason_type, str):
            reason_type = UnavailabilityReasonType(reason_type)
        entry = Unavailability(
            id=self.next_id,
            venue_id=venue_id,
            start_date=start_date,
            end_date=end_date,
            reason_type=reason_type,
            other_reason=other_reason,
            created_by_id=created_by_id,
            created_at=_now(),
        )
        self.entries.append(entry)
        return entry


_repository: Repository = SupabaseUnavailability()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
