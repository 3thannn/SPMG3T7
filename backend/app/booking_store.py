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
* A cancelled booking (US14.2) is kept, not deleted. It stays on the event with
  who cancelled it, when and why, and it stops holding the venue for its slot.
* Each booking carries what it needs of a venue (US18.1): its own headcount,
  which is why a breakout room is not checked against the whole event's
  attendance, and an optional layout, facilities and accessibility needs. They
  are stored so the event page can show what each room was booked for.
* A tentative hold (US14.3) is a booking with status Held, placed by Venue
  Staff for an event's Coordinator, with an expiry. It holds the venue only
  until it expires, and the Coordinator can turn it into a request before
  then. Nothing rewrites an expired hold: it stays Held, and `holds_venue`
  reads the expiry, so it frees its slot the moment it passes without a job
  having to run.
* Venue Staff decide a request (US16.1): Confirmed or Rejected, with who
  decided and when on the row, and for a rejection the reason and an optional
  suggested alternative. A rejected booking is kept, like a cancelled one, and
  frees its slot.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol

from app import event_store, supabase_client, users, venue_store
from app.event_status import EventStatus
from app.venue_store import _now

TABLE = "venue_bookings"
#: `venues(name)` is embedded so the event page can say which venue without a
#: second request per booking. There is one foreign key to `venues`, so
#: PostgREST needs no constraint name to resolve it. There are two to `users`
#: (who requested, who cancelled), so the canceller's name is embedded by
#: constraint name, as US8.1 had to for an event's two users.
COLUMNS = (
    "id, event_id, venue_id, start_at, end_at, status, requested_by_id, created_at, "
    "headcount, required_layout, required_facilities, accessibility_needs, "
    "cancelled_at, cancelled_by_id, cancellation_reason, venues(name), "
    "cancelled_by:users!venue_bookings_cancelled_by_id_fkey(name), "
    "hold_expires_at, held_by_id, held_by:users!venue_bookings_held_by_id_fkey(name), "
    "decided_at, decided_by_id, rejection_reason, suggested_alternative, "
    "decided_by:users!venue_bookings_decided_by_id_fkey(name)"
)

#: Booking times are naive Singapore local times, as event times are (see
#: `event_status.check_completion`), so a hold's expiry is compared with this.
SINGAPORE = timezone(timedelta(hours=8))


def local_now() -> datetime:
    """Now, as a naive Singapore local time, to compare with booking times."""
    return datetime.now(SINGAPORE).replace(tzinfo=None)


class BookingStatus(StrEnum):
    """Matches the `booking_status` enum in Postgres."""

    REQUESTED = "Requested"
    #: US14.2. Final: nothing moves a cancelled booking on.
    CANCELLED = "Cancelled"
    #: US14.3: a tentative hold Venue Staff placed. Becomes Requested when the
    #: Coordinator asks for it, and is never Confirmed on its own.
    HELD = "Held"
    #: US16.1: Venue Staff approved the request. Final.
    CONFIRMED = "Confirmed"
    #: US16.1: Venue Staff turned the request down, with a reason. Final.
    REJECTED = "Rejected"


#: The statuses that can hold a venue for their slot. A cancelled booking does
#: not (US14.2), which is what frees the venue: US15.1's conflict check counts
#: only bookings in these statuses. A Held booking counts only until it expires
#: (US14.3), which `Booking.holds_venue` checks.
HOLDS_VENUE: frozenset[BookingStatus] = frozenset(
    {BookingStatus.REQUESTED, BookingStatus.HELD, BookingStatus.CONFIRMED}
)


@dataclass(frozen=True)
class Cancellation:
    """Who cancelled a booking, when, and why — US14.2."""

    at: str
    #: Nullable so removing a user keeps the cancellation on record.
    by_id: int | None
    by_name: str
    reason: str


@dataclass(frozen=True)
class Decision:
    """Who decided a request, when, and for a rejection why — US16.1."""

    at: str
    #: Nullable so removing a user keeps the decision on record.
    by_id: int | None
    by_name: str
    #: Empty for an approval.
    reason: str = ""
    #: US16.1: an alternative venue or time Venue Staff suggest. Free text, optional.
    suggestion: str = ""


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
    #: US18.1: how many people this booking is for. None only on a booking made
    #: before US18.1 for an event with no attendance to copy.
    headcount: int | None = None
    #: US18.1: empty when the booking asked for no particular layout.
    required_layout: str = ""
    required_facilities: tuple[str, ...] = ()
    accessibility_needs: tuple[str, ...] = ()
    #: Set exactly when the status is Cancelled; the table's CHECK holds that.
    cancellation: Cancellation | None = None
    #: US14.3: when a hold lapses. Always set while Held, and kept once the hold
    #: becomes a request, as the record of how it started. Empty otherwise.
    hold_expires_at: str = ""
    #: US14.3: the Venue Staff member who placed the hold.
    held_by_id: int | None = None
    held_by_name: str = ""
    #: US16.1: set once Venue Staff approve or reject the request.
    decision: Decision | None = None

    def hold_expired_at(self, now: datetime) -> bool:
        """Whether this is a hold whose expiry has passed. Expiry itself counts.

        An expiry that cannot be read is taken as passed: a hold must never
        block a venue for longer than anyone agreed to.
        """
        if self.status is not BookingStatus.HELD:
            return False
        try:
            return datetime.fromisoformat(self.hold_expires_at) <= now
        except ValueError:
            return True

    @property
    def hold_expired(self) -> bool:
        return self.hold_expired_at(local_now())

    def holds_venue_at(self, now: datetime) -> bool:
        return self.status in HOLDS_VENUE and not self.hold_expired_at(now)

    @property
    def holds_venue(self) -> bool:
        return self.holds_venue_at(local_now())


class StaleBookingStatus(RuntimeError):
    """The booking changed after the route checked it, e.g. cancelled twice at once."""


class HoldExpired(RuntimeError):
    """US14.3: the hold lapsed before it could be turned into a request."""


class SlotTaken(RuntimeError):
    """US16.1: approving would clash with a booking that already takes the slot."""



def _embedded_name(row: dict, key: str) -> str:
    """A joined `name`, which PostgREST returns as an object or a list."""
    joined = row.get(key)
    if isinstance(joined, list):
        joined = joined[0] if joined else None
    return joined.get("name", "") if isinstance(joined, dict) else ""


def _cancellation(row: dict) -> Cancellation | None:
    if not row.get("cancelled_at"):
        return None
    return Cancellation(
        at=str(row["cancelled_at"]),
        by_id=row.get("cancelled_by_id"),
        by_name=_embedded_name(row, "cancelled_by"),
        reason=row.get("cancellation_reason") or "",
    )


def _decision(row: dict) -> Decision | None:
    if not row.get("decided_at"):
        return None
    return Decision(
        at=str(row["decided_at"]),
        by_id=row.get("decided_by_id"),
        by_name=_embedded_name(row, "decided_by"),
        reason=row.get("rejection_reason") or "",
        suggestion=row.get("suggested_alternative") or "",
    )


def to_booking(row: dict) -> Booking:
    return Booking(
        id=row["id"],
        event_id=row["event_id"],
        venue_id=row["venue_id"],
        venue_name=_embedded_name(row, "venues"),
        starts_at=str(row["start_at"]),
        ends_at=str(row["end_at"]),
        status=BookingStatus(row["status"]),
        requested_by_id=row.get("requested_by_id"),
        requested_at=str(row["created_at"]) if row.get("created_at") else "",
        headcount=row.get("headcount"),
        required_layout=row.get("required_layout") or "",
        required_facilities=tuple(row.get("required_facilities") or ()),
        accessibility_needs=tuple(row.get("accessibility_needs") or ()),
        cancellation=_cancellation(row),
        hold_expires_at=str(row["hold_expires_at"]) if row.get("hold_expires_at") else "",
        held_by_id=row.get("held_by_id"),
        held_by_name=_embedded_name(row, "held_by"),
        decision=_decision(row),
    )


class Repository(Protocol):
    """What the routes need from a booking store."""

    def list_for_event(self, event_id: int) -> list[Booking]: ...

    def list_for_venue(self, venue_id: int) -> list[Booking]: ...

    def get_booking(self, booking_id: int) -> Booking | None: ...

    def create(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        requested_by_id: int,
        headcount: int,
        required_layout: str = "",
        required_facilities: tuple[str, ...] = (),
        accessibility_needs: tuple[str, ...] = (),
        expected_status: EventStatus | None = None,
    ) -> Booking: ...

    def cancel(self, booking_id: int, *, actor_id: int, reason: str) -> Booking: ...

    def place_hold(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        expires_at: str,
        held_by_id: int,
        headcount: int | None,
    ) -> Booking: ...

    def request_hold(
        self, booking_id: int, *, actor_id: int, expected_status: EventStatus
    ) -> Booking: ...

    def venue_has_bookings(self, venue_id: int) -> bool: ...

    def list_requested(self) -> list[Booking]: ...

    def approve(self, booking_id: int, *, actor_id: int) -> Booking: ...

    def reject(
        self, booking_id: int, *, actor_id: int, reason: str, suggestion: str = ""
    ) -> Booking: ...


class SupabaseBookings:
    """The real store. Goes through the service role client, like the others."""

    def get_booking(self, booking_id: int) -> Booking | None:
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
        headcount: int,
        required_layout: str = "",
        required_facilities: tuple[str, ...] = (),
        accessibility_needs: tuple[str, ...] = (),
        expected_status: EventStatus | None = None,
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
            "headcount": headcount,
            # NULL rather than "" for no layout, as `venue_store` keeps "nothing
            # recorded" as one state. The lists go as JSON arrays to TEXT[].
            "required_layout": required_layout or None,
            "required_facilities": list(required_facilities),
            "accessibility_needs": list(accessibility_needs),
        }
        if expected_status is None:
            created = supabase_client.admin().table(TABLE).insert(row).execute()
            booking_id = created.data[0]["id"]
        else:
            result = supabase_client.admin().rpc(
                "request_venue_and_plan",
                {"p_event_id": event_id, "p_expected_status": str(expected_status),
                 "p_venue_id": venue_id, "p_start_at": starts_at, "p_end_at": ends_at,
                 "p_requested_by_id": requested_by_id, "p_headcount": headcount,
                 "p_required_layout": required_layout or None,
                 "p_required_facilities": list(required_facilities),
                 "p_accessibility_needs": list(accessibility_needs)},
            ).execute()
            if not result.data:
                raise event_store.StaleEventStatus
            booking_id = result.data
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just inserted
        return booking

    def cancel(self, booking_id: int, *, actor_id: int, reason: str) -> Booking:
        """US14.2: Requested -> Cancelled, with who, when and why on the row.

        US14.3: a Held booking can be cancelled too, which releases the hold.
        The update only matches a booking that is still Requested or Held, so two
        cancels racing each other cannot both succeed. The second finds no row
        and raises, as `event_store.request_clarification` does for an event
        that moved. Nothing else is written: the event and its other bookings
        are left exactly as they were.
        """
        updated = (
            supabase_client.admin()
            .table(TABLE)
            .update(
                {
                    "status": str(BookingStatus.CANCELLED),
                    "cancelled_at": _now(),
                    "cancelled_by_id": actor_id,
                    "cancellation_reason": reason,
                }
            )
            .eq("id", booking_id)
            .in_("status", [str(BookingStatus.REQUESTED), str(BookingStatus.HELD)])
            .execute()
        )
        if not updated.data:
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def place_hold(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        expires_at: str,
        held_by_id: int,
        headcount: int | None,
    ) -> Booking:
        """US14.3: record a tentative hold. Nobody has requested it yet."""
        created = (
            supabase_client.admin()
            .table(TABLE)
            .insert(
                {
                    "event_id": event_id,
                    "venue_id": venue_id,
                    "start_at": starts_at,
                    "end_at": ends_at,
                    "status": str(BookingStatus.HELD),
                    "requested_by_id": None,
                    "created_at": _now(),
                    "headcount": headcount,
                    "hold_expires_at": expires_at,
                    "held_by_id": held_by_id,
                }
            )
            .execute()
        )
        booking = self.get_booking(created.data[0]["id"])
        assert booking is not None  # noqa: S101 — the row was just inserted
        return booking

    def request_hold(
        self, booking_id: int, *, actor_id: int, expected_status: EventStatus
    ) -> Booking:
        """US14.3: Held -> Requested, in one transaction with US4.5's Planning move.

        The RPC re-checks under row locks what the route already checked, so a
        hold that expires, is cancelled, or whose event moves in between is
        refused rather than half-applied.
        """
        outcome = (
            supabase_client.admin()
            .rpc(
                "request_held_booking",
                {
                    "p_booking_id": booking_id,
                    "p_expected_status": str(expected_status),
                    "p_requested_by_id": actor_id,
                },
            )
            .execute()
            .data
        )
        if outcome == "expired":
            raise HoldExpired
        if outcome == "stale-event":
            raise event_store.StaleEventStatus
        if outcome != "requested":
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def list_for_venue(self, venue_id: int) -> list[Booking]:
        """US9.4: every booking at a venue, soonest first, for its re-check.

        Cancelled bookings come back too; the re-check is what decides they no
        longer hold the venue, so the rule lives in one place.
        """
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("venue_id", venue_id)
            .order("start_at")
            .order("end_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [to_booking(row) for row in rows]

    def list_requested(self) -> list[Booking]:
        """US16.1: every Requested booking, oldest request first, then by id."""
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("status", str(BookingStatus.REQUESTED))
            .order("created_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [to_booking(row) for row in rows]

    def approve(self, booking_id: int, *, actor_id: int) -> Booking:
        """US16.1: Requested -> Confirmed, unless the slot is taken by then.

        The RPC locks the venue, so two approvals for one venue run one at a
        time, and re-checks the clash in SQL under that lock: the route's own
        check is what explains a clash, this is what makes two approvals for
        the same slot impossible.
        """
        outcome = (
            supabase_client.admin()
            .rpc("approve_venue_booking", {"p_booking_id": booking_id, "p_actor_id": actor_id})
            .execute()
            .data
        )
        if outcome == "clash":
            raise SlotTaken
        if outcome != "confirmed":
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def reject(
        self, booking_id: int, *, actor_id: int, reason: str, suggestion: str = ""
    ) -> Booking:
        """US16.1: Requested -> Rejected, with who, when, why and any suggestion.

        Matches only a booking still Requested, so a request decided twice at
        once is decided once. Nothing else is written.
        """
        updated = (
            supabase_client.admin()
            .table(TABLE)
            .update(
                {
                    "status": str(BookingStatus.REJECTED),
                    "decided_at": _now(),
                    "decided_by_id": actor_id,
                    "rejection_reason": reason,
                    "suggested_alternative": suggestion or None,
                }
            )
            .eq("id", booking_id)
            .eq("status", str(BookingStatus.REQUESTED))
            .execute()
        )
        if not updated.data:
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def venue_has_bookings(self, venue_id: int) -> bool:
        """Whether anything books this venue — asked before US9.1c deletes it.

        Cancelled bookings count. They free the venue's slot, but they are
        still the event's record of what was asked for, and the row cannot
        outlive its venue.
        """
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

    The venue and canceller names are read from their stores at the time of
    the write, standing in for the joins the real query makes.
    """

    bookings: list[Booking] = field(default_factory=list)
    #: Well clear of anything a fixture might use, so a created row is obvious.
    next_id: int = 100

    def list_for_event(self, event_id: int) -> list[Booking]:
        return sorted((b for b in self.bookings if b.event_id == event_id), key=_sort_key)

    def list_for_venue(self, venue_id: int) -> list[Booking]:
        return sorted((b for b in self.bookings if b.venue_id == venue_id), key=_sort_key)

    def get_booking(self, booking_id: int) -> Booking | None:
        return next((b for b in self.bookings if b.id == booking_id), None)

    def cancel(self, booking_id: int, *, actor_id: int, reason: str) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.HELD,
        ):
            raise StaleBookingStatus
        actor = users.get_by_id(actor_id)
        cancelled = replace(
            existing,
            status=BookingStatus.CANCELLED,
            cancellation=Cancellation(
                at=_now(),
                by_id=actor_id,
                by_name=actor.name if actor else "",
                reason=reason,
            ),
        )
        self.bookings = [cancelled if b.id == booking_id else b for b in self.bookings]
        return cancelled

    def create(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        requested_by_id: int,
        headcount: int,
        required_layout: str = "",
        required_facilities: tuple[str, ...] = (),
        accessibility_needs: tuple[str, ...] = (),
        expected_status: EventStatus | None = None,
    ) -> Booking:
        if expected_status is not None:
            event = event_store.repository().get_event(event_id)
            if (
                event is None
                or event.status is not expected_status
                or event.coordinator_id != requested_by_id
            ):
                raise event_store.StaleEventStatus
            if event.status is EventStatus.APPROVED:
                event_store.repository().plan_event(event_id, actor_id=requested_by_id)
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
            headcount=headcount,
            required_layout=required_layout,
            required_facilities=tuple(required_facilities),
            accessibility_needs=tuple(accessibility_needs),
        )
        self.bookings.append(booking)
        return booking

    def place_hold(
        self,
        *,
        event_id: int,
        venue_id: int,
        starts_at: str,
        ends_at: str,
        expires_at: str,
        held_by_id: int,
        headcount: int | None,
    ) -> Booking:
        venue = venue_store.repository().get_venue(venue_id)
        holder = users.get_by_id(held_by_id)
        self.next_id += 1
        booking = Booking(
            id=self.next_id,
            event_id=event_id,
            venue_id=venue_id,
            venue_name=venue.name if venue else "",
            starts_at=starts_at,
            ends_at=ends_at,
            status=BookingStatus.HELD,
            requested_by_id=None,
            requested_at=_now(),
            headcount=headcount,
            hold_expires_at=expires_at,
            held_by_id=held_by_id,
            held_by_name=holder.name if holder else "",
        )
        self.bookings.append(booking)
        return booking

    def request_hold(
        self, booking_id: int, *, actor_id: int, expected_status: EventStatus
    ) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.HELD:
            raise StaleBookingStatus
        if existing.hold_expired:
            raise HoldExpired
        event = event_store.repository().get_event(existing.event_id)
        if (
            event is None
            or event.status is not expected_status
            or event.status not in (EventStatus.APPROVED, EventStatus.PLANNING)
            or event.coordinator_id != actor_id
        ):
            raise event_store.StaleEventStatus
        if event.status is EventStatus.APPROVED:
            event_store.repository().plan_event(event.id, actor_id=actor_id)
        requested = replace(existing, status=BookingStatus.REQUESTED, requested_by_id=actor_id)
        self.bookings = [requested if b.id == booking_id else b for b in self.bookings]
        return requested

    def venue_has_bookings(self, venue_id: int) -> bool:
        return any(booking.venue_id == venue_id for booking in self.bookings)

    def list_requested(self) -> list[Booking]:
        requested = [b for b in self.bookings if b.status is BookingStatus.REQUESTED]
        return sorted(requested, key=lambda b: (b.requested_at, b.id))

    def _decide(self, booking_id: int, decided: Booking) -> Booking:
        self.bookings = [decided if b.id == booking_id else b for b in self.bookings]
        return decided

    def _decision(self, actor_id: int, reason: str = "", suggestion: str = "") -> Decision:
        actor = users.get_by_id(actor_id)
        return Decision(
            at=_now(),
            by_id=actor_id,
            by_name=actor.name if actor else "",
            reason=reason,
            suggestion=suggestion,
        )

    def approve(self, booking_id: int, *, actor_id: int) -> Booking:
        from app import availability  # the US15.1 rule, as the RPC applies it in SQL

        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.REQUESTED:
            raise StaleBookingStatus
        venue = venue_store.repository().get_venue(existing.venue_id)
        if availability.find_clashes(existing, venue, self.list_for_venue(existing.venue_id)):
            raise SlotTaken
        return self._decide(
            booking_id,
            replace(existing, status=BookingStatus.CONFIRMED, decision=self._decision(actor_id)),
        )

    def reject(
        self, booking_id: int, *, actor_id: int, reason: str, suggestion: str = ""
    ) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.REQUESTED:
            raise StaleBookingStatus
        return self._decide(
            booking_id,
            replace(
                existing,
                status=BookingStatus.REJECTED,
                decision=self._decision(actor_id, reason, suggestion),
            ),
        )


_repository: Repository = SupabaseBookings()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
