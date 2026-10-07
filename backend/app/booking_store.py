"""Venue bookings, backed by the Supabase `venue_bookings` table — US14.1.

A Coordinator asks for a venue for an event, and each request is one row, so an
event that needs a main hall and two breakout rooms has three (Week 7 change
#3). This module is only the access. Who may request, and for which events, is
the business of the routes in `app.events`, as it is for every other store.

Three choices worth knowing:

* A booking is its own record rather than a column on `events`. One event can
  have many, and each one is checked, approved or refused on its own: a breakout
  room that is turned down must not take the main hall with it.
* Times are naive timestamps passed through as strings, for the reason
  `event_store` gives: converting here and back in the client would shift a
  booking by the server's offset.
* Every booking starts Requested. Venue Staff approval is its own epic, and the
  statuses it moves a booking to arrive with it.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app import supabase_client, venue_store
from app.venue_store import _now

TABLE = "venue_bookings"
#: `venues(name)` is embedded so the event page can say which venue without a
#: second request per booking. There is one foreign key to `venues`, so
#: PostgREST needs no constraint name to resolve it.
COLUMNS = (
    "id, event_id, venue_id, start_at, end_at, status, requested_by_id, created_at, "
    "venues(name)"
)


class BookingStatus(StrEnum):
    """Matches the `booking_status` enum in Postgres, which holds only this so far."""

    REQUESTED = "Requested"


@dataclass(frozen=True)
class Booking:
    id: int
    event_id: int
    venue_id: int
    venue_name: str
    starts_at: str
    ends_at: str
    status: BookingStatus
    #: Who asked. Nullable so removing a user does not remove their bookings.
    requested_by_id: int | None
    requested_at: str


def _venue_name(row: dict) -> str:
    """The joined `venues(name)`, which PostgREST returns as an object or a list."""
    joined = row.get("venues")
    if isinstance(joined, list):
        joined = joined[0] if joined else None
    return joined.get("name", "") if isinstance(joined, dict) else ""


def to_booking(row: dict) -> Booking:
    return Booking(
        id=row["id"],
        event_id=row["event_id"],
        venue_id=row["venue_id"],
        venue_name=_venue_name(row),
        starts_at=str(row["start_at"]),
        ends_at=str(row["end_at"]),
        status=BookingStatus(row["status"]),
        requested_by_id=row.get("requested_by_id"),
        requested_at=str(row["created_at"]) if row.get("created_at") else "",
    )


class Repository(Protocol):
    """What the routes need from a booking store."""

    def list_for_event(self, event_id: int) -> list[Booking]: ...

    def create(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        requested_by_id: int,
    ) -> Booking: ...

    def venue_has_bookings(self, venue_id: int) -> bool: ...


class SupabaseBookings:
    """The real store. Goes through the service role client, like the others."""

    def _get(self, booking_id: int) -> Booking | None:
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("id", booking_id)
            .limit(1)
            .execute()
            .data
        )
        return to_booking(rows[0]) if rows else None

    def list_for_event(self, event_id: int) -> list[Booking]:
        """Soonest first, so the event page reads in the order the day runs.

        `end_at` and then `id` break ties, so two bookings starting together come
        back in the same order every time.
        """
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("event_id", event_id)
            .order("start_at")
            .order("end_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [to_booking(row) for row in rows]

    def create(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        requested_by_id: int,
    ) -> Booking:
        """US14.1: record one request for one venue, in the Requested state.

        The status is sent rather than left to the column default, so the row
        says what this code meant instead of what the database happened to do.
        The insert response carries no embedded venue name, so the row is read
        back, as `event_store` does after an insert.
        """
        row = {
            "event_id": event_id,
            "venue_id": venue_id,
            "start_at": starts_at,
            "end_at": ends_at,
            "status": str(BookingStatus.REQUESTED),
            "requested_by_id": requested_by_id,
            "created_at": _now(),
        }
        created = supabase_client.admin().table(TABLE).insert(row).execute()
        booking = self._get(created.data[0]["id"])
        assert booking is not None  # noqa: S101 — the row was just inserted
        return booking

    def venue_has_bookings(self, venue_id: int) -> bool:
        """Whether anything books this venue — asked before US9.1c deletes it."""
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select("id")
            .eq("venue_id", venue_id)
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)


def _sort_key(booking: Booking) -> tuple[str, str, int]:
    return (booking.starts_at, booking.ends_at, booking.id)


@dataclass
class InMemoryBookings:
    """A stand-in for tests, ordered the way the real query is.

    The venue name is read from the venue store at the time of the request,
    standing in for the join the real query makes.
    """

    bookings: list[Booking] = field(default_factory=list)
    #: Well clear of anything a fixture might use, so a created row is obvious.
    next_id: int = 100

    def list_for_event(self, event_id: int) -> list[Booking]:
        return sorted((b for b in self.bookings if b.event_id == event_id), key=_sort_key)

    def create(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        requested_by_id: int,
    ) -> Booking:
        venue = venue_store.repository().get_venue(venue_id)
        self.next_id += 1
        booking = Booking(
            id=self.next_id,
            event_id=event_id,
            venue_id=venue_id,
            venue_name=venue.name if venue else "",
            starts_at=starts_at,
            ends_at=ends_at,
            status=BookingStatus.REQUESTED,
            requested_by_id=requested_by_id,
            requested_at=_now(),
        )
        self.bookings.append(booking)
        return booking

    def venue_has_bookings(self, venue_id: int) -> bool:
        return any(booking.venue_id == venue_id for booking in self.bookings)


_repository: Repository = SupabaseBookings()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
