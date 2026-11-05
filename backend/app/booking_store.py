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
* A tentative hold (US14.3, as Week 9 clarified it) starts after venue
  approval: Venue Staff approve a request as a hold with an expiry, and the
  booking is Held, with the decision on the row. It holds the venue only until
  it expires, and the Coordinator confirms it (Held -> Confirmed) before then.
  Venue Staff can change the expiry or release the hold early (US14.6).
  `holds_venue` reads the expiry, so a hold frees its slot the moment it
  passes without waiting for anything to run.
* US14.4: a scheduled job (`sweep_tentative_holds`, pg_cron, every 15 minutes)
  then records it: Held becomes Expired, and the Coordinator is told. Between
  the deadline and the next sweep the hold is still Held but already expired;
  `hold_expired` answers the same for both, so nothing reads them differently.
* Venue Staff decide a request (US16.1): Confirmed or Rejected, with who
  decided and when on the row, and for a rejection the reason and an optional
  suggested alternative. A rejected booking is kept, like a cancelled one, and
  frees its slot.
* A request is refused when its slot is not free (US15.1, `app.availability`).
  `request_venue_and_plan` re-checks under a lock on the venue, so two requests
  for one slot at once cannot both be stored.
* A booking that clashes after its venue's setup or turnaround time changes is
  flagged "Conflict - review needed" (US15.2): when, and why, on the row. The
  flag is a mark beside the status, never a status of its own, so a flagged
  booking is still Requested, Held or Confirmed, and nothing is deleted or
  cancelled to clear it.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import RLock
from typing import Protocol

from app import event_store, supabase_client, users, venue_store
from app.event_status import CLOSED, EventStatus
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
    "decided_by:users!venue_bookings_decided_by_id_fkey(name), "
    "conflict_flagged_at, conflict_reason, event_conflict_reason, event_conflict_at, "
    "replacement_reason, flagged_by_unavailability_id"
)

#: What `request_venue_and_plan` returns when the slot is taken (US15.1). Ids
#: are SERIAL, so they are never negative, and NULL already means a stale event.
RPC_CLASH = -1

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
    #: US14.3: Venue Staff approved the request as a tentative hold, with an
    #: expiry. Becomes Confirmed only when the Coordinator confirms it.
    HELD = "Held"
    #: US16.1: Venue Staff approved the request. Final.
    CONFIRMED = "Confirmed"
    #: US16.1: Venue Staff turned the request down, with a reason. Final.
    REJECTED = "Rejected"
    #: US14.4: a hold the scheduled sweep found past its expiry. Final: it is
    #: kept as history, never holds its venue and cannot be requested.
    EXPIRED = "Expired"
    #: US12.2: a booking flagged because the venue became unavailable. The
    #: Coordinator must request a replacement venue (US14.5) or cancel (US14.2).
    NEEDS_REPLACEMENT = "Needs replacement"
    #: US14.5: a booking that has been replaced by a new booking. Final: kept
    #: for history, never holds its venue.
    REPLACED = "Replaced"


#: The statuses that can hold a venue for their slot. A cancelled booking does
#: not (US14.2), which is what frees the venue: US15.1's conflict check counts
#: only bookings in these statuses. A Held booking counts only until it expires
#: (US14.3), which `Booking.holds_venue` checks.
HOLDS_VENUE: frozenset[BookingStatus] = frozenset(
    {BookingStatus.REQUESTED, BookingStatus.HELD, BookingStatus.CONFIRMED}
)

#: US14.2: the statuses a Coordinator can cancel. A booking flagged Needs
#: replacement (US12.2) can be too: US12.2 AC5 and US15.2 AC4 clear a flag by
#: cancelling, and the Week 4 answer leaves that decision to the Coordinator
#: (CODE_AUDIT.md D7). Rejected, Replaced, Expired and Cancelled hold nothing.
CANCELLABLE: frozenset[BookingStatus] = HOLDS_VENUE | {BookingStatus.NEEDS_REPLACEMENT}


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
class ConflictFlag:
    """US15.2: a booking that clashes since its venue's setup or turnaround changed."""

    #: Naive UTC, as the other `_at` columns are.
    flagged_at: str
    #: What it clashes with, in words the event's Coordinator may read.
    reason: str


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
    #: US14.3: when a hold lapses. Always set while Held, and kept once the
    #: Coordinator confirms it, as the record of how it started. Empty otherwise.
    hold_expires_at: str = ""
    #: US14.3: the Venue Staff member who approved the request as a hold.
    held_by_id: int | None = None
    held_by_name: str = ""
    #: US16.1: set once Venue Staff approve or reject the request.
    decision: Decision | None = None
    #: US15.2: set while the booking is flagged "Conflict - review needed".
    conflict: ConflictFlag | None = None
    event_conflict_reason: str = ""
    event_conflict_at: str = ""
    #: US12.2: Why this booking needs replacement (from venue unavailability).
    #: Empty unless status is NEEDS_REPLACEMENT.
    replacement_reason: str = ""
    #: US12.2: The unavailability_id that triggered the flagging. Nullable.
    flagged_by_unavailability_id: int | None = None

    def hold_expired_at(self, now: datetime) -> bool:
        """Whether this is a hold whose expiry has passed. Expiry itself counts.

        US14.4: an Expired hold has, by definition; a Held one past its expiry
        has too, it just has not been swept yet.

        An expiry that cannot be read is taken as passed: a hold must never
        block a venue for longer than anyone agreed to.
        """
        if self.status is BookingStatus.EXPIRED:
            return True
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

    def ends_after(self, now: datetime) -> bool:
        """Whether this booking has yet to end. One under way has not.

        An end that cannot be read is taken as still to come, so a venue is
        never deleted out from under a booking we could not judge (US9.5).
        """
        try:
            return datetime.fromisoformat(self.ends_at) > now
        except ValueError:
            return True

    def upcoming_at(self, now: datetime) -> bool:
        """US9.5: whether this booking still holds its venue and has not ended."""
        return self.holds_venue_at(now) and self.ends_after(now)

    def awaiting_replacement_at(self, now: datetime) -> bool:
        """US9.5: flagged by US12.2 and not yet ended, so its Coordinator still
        has to find it another venue (US14.5). Deleting the venue would delete
        the booking, and the Coordinator's task with it."""
        return self.status is BookingStatus.NEEDS_REPLACEMENT and self.ends_after(now)


def is_replacement(booking: Booking, event_bookings: list[Booking]) -> bool:
    """US10.4: whether `booking` was requested in place of one that fell through.

    Nothing links the two rows. request_replacement_venue (US14.5) copies the
    old booking's times onto the new one and marks the old one Replaced, so a
    Replaced booking of the same event at the same times is the one it replaced.
    """
    return any(
        other.id != booking.id
        and other.event_id == booking.event_id
        and other.status is BookingStatus.REPLACED
        and (other.starts_at, other.ends_at) == (booking.starts_at, booking.ends_at)
        for other in event_bookings
    )


class StaleBookingStatus(RuntimeError):
    """The booking changed after the route checked it, e.g. cancelled twice at once."""


class HoldExpired(RuntimeError):
    """US14.3: the hold lapsed before the Coordinator confirmed it."""


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


def _conflict(row: dict) -> ConflictFlag | None:
    if not row.get("conflict_flagged_at"):
        return None
    return ConflictFlag(
        flagged_at=str(row["conflict_flagged_at"]),
        reason=row.get("conflict_reason") or "",
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
        conflict=_conflict(row),
        event_conflict_reason=row.get("event_conflict_reason") or "",
        event_conflict_at=str(row["event_conflict_at"]) if row.get("event_conflict_at") else "",
        replacement_reason=row.get("replacement_reason") or "",
        flagged_by_unavailability_id=row.get("flagged_by_unavailability_id"),
    )


class Repository(Protocol):
    """What the routes need from a booking store."""

    def list_for_event(self, event_id: int) -> list[Booking]: ...

    def list_for_venue(self, venue_id: int) -> list[Booking]: ...

    def list_for_venues(self, venue_ids: list[int]) -> dict[int, list[Booking]]: ...

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

    def approve_as_hold(self, booking_id: int, *, actor_id: int, expires_at: str) -> Booking: ...

    def confirm_hold(self, booking_id: int, *, actor_id: int) -> Booking: ...

    def update_hold(self, booking_id: int, *, expires_at: str) -> Booking: ...

    def list_requested(self) -> list[Booking]: ...

    def approve(self, booking_id: int, *, actor_id: int) -> Booking: ...

    def reject(
        self, booking_id: int, *, actor_id: int, reason: str, suggestion: str = ""
    ) -> Booking: ...

    def flag_conflict(self, booking_id: int, *, reason: str) -> Booking: ...

    def clear_conflict(self, booking_id: int) -> Booking: ...

    def list_flagged(self) -> list[Booking]: ...

    def count_flagged_by_unavailability(self, unavailability_id: int) -> int: ...

    def request_replacement(
        self, booking_id: int, *, venue_id: int, actor_id: int, reason: str = ""
    ) -> Booking: ...


class SupabaseBookings:
    """The real store. Goes through the service role client, like the others."""

    def request_replacement(
        self, booking_id: int, *, venue_id: int, actor_id: int, reason: str = ""
    ) -> Booking:
        """US14.5, and US12.4: on a Confirmed event, the move back to Planning.

        us12_4_request_replacement calls request_replacement_venue as it stands
        and, once the booking is Replaced, moves a Confirmed event to Planning
        with `reason` in its history, in the same transaction. It answers what
        request_replacement_venue answers.
        """
        result = (
            supabase_client.admin()
            .rpc(
                "us12_4_request_replacement",
                {
                    "p_booking_id": booking_id,
                    "p_venue_id": venue_id,
                    "p_actor_id": actor_id,
                    "p_reason": reason,
                },
            )
            .execute()
        )
        if result.data == RPC_CLASH:
            raise SlotTaken
        if not result.data:
            raise StaleBookingStatus
        booking = self.get_booking(result.data)
        if booking is None:
            raise StaleBookingStatus
        return booking

    def count_flagged_by_unavailability(self, unavailability_id: int) -> int:
        result = (
            supabase_client.admin()
            .table(TABLE)
            .select("id", count="exact")
            .eq("flagged_by_unavailability_id", unavailability_id)
            .execute()
        )
        return result.count or 0

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
        US15.1: the RPC locks the venue and refuses a slot that is not free
        (`SlotTaken`), so the route's own check cannot be raced.
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
            result = (
                supabase_client.admin()
                .rpc(
                    "request_venue_and_plan",
                    {
                        "p_event_id": event_id,
                        "p_expected_status": str(expected_status),
                        "p_venue_id": venue_id,
                        "p_start_at": starts_at,
                        "p_end_at": ends_at,
                        "p_requested_by_id": requested_by_id,
                        "p_headcount": headcount,
                        "p_required_layout": required_layout or None,
                        "p_required_facilities": list(required_facilities),
                        "p_accessibility_needs": list(accessibility_needs),
                    },
                )
                .execute()
            )
            if result.data == RPC_CLASH:
                raise SlotTaken
            if not result.data:
                raise event_store.StaleEventStatus
            booking_id = result.data
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just inserted
        return booking

    def cancel(self, booking_id: int, *, actor_id: int, reason: str) -> Booking:
        """US14.2: a booking -> Cancelled, with who, when and why on the row.

        US14.3: a Held booking can be cancelled too, which releases the hold;
        so can a Confirmed or flagged one (`CANCELLABLE`, D7). The update only
        matches a booking still in one of those statuses, so two
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
            .in_("status", sorted(str(each) for each in CANCELLABLE))
            .execute()
        )
        if not updated.data:
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def approve_as_hold(self, booking_id: int, *, actor_id: int, expires_at: str) -> Booking:
        """US14.3/US16.1: Requested -> Held, an approval with an expiry.

        approve_venue_booking_as_hold locks the venue and re-checks the clash
        as approve_venue_booking does, then records the decision, who holds it
        and until when. Only a booking still Requested moves.
        """
        outcome = (
            supabase_client.admin()
            .rpc(
                "approve_venue_booking_as_hold",
                {"p_booking_id": booking_id, "p_actor_id": actor_id, "p_expires_at": expires_at},
            )
            .execute()
            .data
        )
        if outcome == "clash":
            raise SlotTaken
        if outcome != "held":
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def confirm_hold(self, booking_id: int, *, actor_id: int) -> Booking:
        """US14.3: Held -> Confirmed, by the event's Coordinator, before it expires.

        The RPC re-checks under row locks what the route already checked, so a
        hold that expires, is released, or whose event moves in between is
        refused rather than half-applied.
        """
        outcome = (
            supabase_client.admin()
            .rpc("confirm_held_booking", {"p_booking_id": booking_id, "p_actor_id": actor_id})
            .execute()
            .data
        )
        if outcome == "expired":
            raise HoldExpired
        if outcome == "stale-event":
            raise event_store.StaleEventStatus
        if outcome != "confirmed":
            raise StaleBookingStatus
        booking = self.get_booking(booking_id)
        assert booking is not None  # noqa: S101 — the row was just updated
        return booking

    def update_hold(self, booking_id: int, *, expires_at: str) -> Booking:
        """US14.6: a new expiry for a hold that is still Held and has not lapsed.

        The warning is cleared, so the sweep warns again before the new expiry.
        """
        updated = (
            supabase_client.admin()
            .table(TABLE)
            .update({"hold_expires_at": expires_at, "expiry_warned_at": None})
            .eq("id", booking_id)
            .eq("status", str(BookingStatus.HELD))
            .gt("hold_expires_at", local_now().isoformat(timespec="seconds"))
            .execute()
        )
        if not updated.data:
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

    def list_for_venues(self, venue_ids: list[int]) -> dict[int, list[Booking]]:
        """All bookings for a queue's venues in one database round trip."""
        wanted = sorted(set(venue_ids))
        if not wanted:
            return {}
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .in_("venue_id", wanted)
            .order("venue_id")
            .order("start_at")
            .order("end_at")
            .order("id")
            .execute()
            .data
            or []
        )
        grouped: dict[int, list[Booking]] = {venue_id: [] for venue_id in wanted}
        for row in rows:
            grouped[row["venue_id"]].append(to_booking(row))
        return grouped

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

    def _write_conflict(self, booking_id: int, changes: dict) -> Booking:
        supabase_client.admin().table(TABLE).update(changes).eq("id", booking_id).execute()
        booking = self.get_booking(booking_id)
        if booking is None:
            raise StaleBookingStatus
        return booking

    def flag_conflict(self, booking_id: int, *, reason: str) -> Booking:
        """US15.2: mark the booking "Conflict - review needed". Status untouched."""
        return self._write_conflict(
            booking_id, {"conflict_flagged_at": _now(), "conflict_reason": reason}
        )

    def clear_conflict(self, booking_id: int) -> Booking:
        """US15.2: the clash is resolved, so the flag goes. Status untouched."""
        return self._write_conflict(
            booking_id, {"conflict_flagged_at": None, "conflict_reason": None}
        )

    def list_flagged(self) -> list[Booking]:
        """US15.2: every flagged booking, soonest first, for Venue Staff to review."""
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .or_("conflict_flagged_at.not.is.null,event_conflict_at.not.is.null")
            .order("start_at")
            .order("end_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [to_booking(row) for row in rows]


def _sort_key(booking: Booking) -> tuple[str, str, int]:
    return (booking.starts_at, booking.ends_at, booking.id)


@dataclass
class InMemoryBookings:
    """A stand-in for tests, ordered the way the real query is.

    The venue and canceller names are read from their stores at the time of
    the write, standing in for the joins the real query makes.
    """

    bookings: list[Booking] = field(default_factory=list)
    replacement_lock: RLock = field(default_factory=RLock, repr=False, compare=False)
    #: Well clear of anything a fixture might use, so a created row is obvious.
    next_id: int = 100

    def request_replacement(
        self, booking_id: int, *, venue_id: int, actor_id: int, reason: str = ""
    ) -> Booking:
        with self.replacement_lock:
            old = self.get_booking(booking_id)
            event = event_store.repository().get_event(old.event_id) if old else None
            venue = venue_store.repository().get_venue(venue_id)
            if (
                old is None
                or old.status is not BookingStatus.NEEDS_REPLACEMENT
                or event is None
                or event.coordinator_id != actor_id
                or event.status in CLOSED
                or venue is None
                or venue_id == old.venue_id
            ):
                raise StaleBookingStatus
            self._refuse_taken_slot(venue_id, old.starts_at, old.ends_at)
            self.next_id += 1
            created = Booking(
                id=self.next_id,
                event_id=old.event_id,
                venue_id=venue_id,
                venue_name=venue.name,
                starts_at=old.starts_at,
                ends_at=old.ends_at,
                status=BookingStatus.REQUESTED,
                requested_by_id=actor_id,
                requested_at=_now(),
                headcount=old.headcount,
                required_layout=old.required_layout,
                required_facilities=old.required_facilities,
                accessibility_needs=old.accessibility_needs,
            )
            self.bookings = [
                replace(booking, status=BookingStatus.REPLACED) if booking.id == old.id else booking
                for booking in self.bookings
            ] + [created]
            # US12.4: what us12_4_request_replacement does to a Confirmed event.
            event_store.repository().reopen_for_replacement(
                event.id, actor_id=actor_id, reason=reason
            )
            return created

    def flag_for_unavailability(
        self, booking_id: int, *, reason: str, unavailability_id: int
    ) -> None:
        """US12.2: what the unavailability trigger writes to one booking."""
        existing = self.get_booking(booking_id)
        if existing is None:
            return
        self._decide(
            booking_id,
            replace(
                existing,
                status=BookingStatus.NEEDS_REPLACEMENT,
                replacement_reason=reason,
                flagged_by_unavailability_id=unavailability_id,
            ),
        )

    def _set_event_conflict(self, booking_id: int, reason: str) -> None:
        self.bookings = [
            replace(row, event_conflict_reason=reason, event_conflict_at=_now() if reason else "")
            if row.id == booking_id
            else row
            for row in self.bookings
        ]

    def count_flagged_by_unavailability(self, unavailability_id: int) -> int:
        return sum(
            booking.flagged_by_unavailability_id == unavailability_id for booking in self.bookings
        )

    def list_for_event(self, event_id: int) -> list[Booking]:
        return sorted((b for b in self.bookings if b.event_id == event_id), key=_sort_key)

    def list_for_venue(self, venue_id: int) -> list[Booking]:
        return sorted((b for b in self.bookings if b.venue_id == venue_id), key=_sort_key)

    def list_for_venues(self, venue_ids: list[int]) -> dict[int, list[Booking]]:
        wanted = set(venue_ids)
        return {
            venue_id: sorted(
                (booking for booking in self.bookings if booking.venue_id == venue_id),
                key=_sort_key,
            )
            for venue_id in wanted
        }

    def get_booking(self, booking_id: int) -> Booking | None:
        return next((b for b in self.bookings if b.id == booking_id), None)

    def cancel(self, booking_id: int, *, actor_id: int, reason: str) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status not in CANCELLABLE:
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

    def release_for_event(self, event_id: int, *, actor_id: int, reason: str) -> tuple[int, ...]:
        """US4.6: the `cancel_event` RPC's booking update, for `InMemoryEvents`.

        Every booking of the event that still holds its venue is Cancelled with
        the event's reason. A Confirmed one keeps its decision, as the row does.
        Cancelled, Rejected and expired holds are left as they are.
        """
        actor = users.get_by_id(actor_id)
        now = local_now()
        released: list[int] = []
        for booking in self.list_for_event(event_id):
            if not booking.holds_venue_at(now):
                continue
            released.append(booking.id)
            self._decide(
                booking.id,
                replace(
                    booking,
                    status=BookingStatus.CANCELLED,
                    cancellation=Cancellation(
                        at=_now(),
                        by_id=actor_id,
                        by_name=actor.name if actor else "",
                        reason=reason,
                    ),
                ),
            )
        return tuple(released)

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
            self._refuse_taken_slot(venue_id, starts_at, ends_at)
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

    def approve_as_hold(self, booking_id: int, *, actor_id: int, expires_at: str) -> Booking:
        existing = self._approvable(booking_id)
        actor = users.get_by_id(actor_id)
        return self._decide(
            booking_id,
            replace(
                existing,
                status=BookingStatus.HELD,
                decision=self._decision(actor_id),
                hold_expires_at=expires_at,
                held_by_id=actor_id,
                held_by_name=actor.name if actor else "",
            ),
        )

    def confirm_hold(self, booking_id: int, *, actor_id: int) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.HELD:
            raise StaleBookingStatus
        if existing.hold_expired:
            raise HoldExpired
        event = event_store.repository().get_event(existing.event_id)
        if event is None or event.status in CLOSED or event.coordinator_id != actor_id:
            raise event_store.StaleEventStatus
        return self._decide(booking_id, replace(existing, status=BookingStatus.CONFIRMED))

    def update_hold(self, booking_id: int, *, expires_at: str) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.HELD or existing.hold_expired:
            raise StaleBookingStatus
        return self._decide(booking_id, replace(existing, hold_expires_at=expires_at))

    def _refuse_taken_slot(self, venue_id: int, starts_at: str, ends_at: str) -> None:
        """US15.1, as `request_venue_and_plan` re-checks it in SQL under its lock."""
        from app import availability, venue_unavailability_store

        found = availability.check_slot(
            venue_store.repository().get_venue(venue_id),
            starts_at,
            ends_at,
            bookings_at_venue=self.list_for_venue(venue_id),
            unavailability=venue_unavailability_store.repository().list_for_venue(venue_id),
        )
        if not found.available:
            raise SlotTaken

    def _set_conflict(self, booking_id: int, flag: ConflictFlag | None) -> Booking:
        existing = self.get_booking(booking_id)
        if existing is None:
            raise StaleBookingStatus
        return self._decide(booking_id, replace(existing, conflict=flag))

    def flag_conflict(self, booking_id: int, *, reason: str) -> Booking:
        return self._set_conflict(booking_id, ConflictFlag(flagged_at=_now(), reason=reason))

    def clear_conflict(self, booking_id: int) -> Booking:
        return self._set_conflict(booking_id, None)

    def list_flagged(self) -> list[Booking]:
        return sorted(
            (b for b in self.bookings if b.conflict is not None or b.event_conflict_reason),
            key=_sort_key,
        )

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

    def _approvable(self, booking_id: int) -> Booking:
        """A Requested booking whose slot is still free: the US15.1 rule at
        approval, as the RPCs apply it in SQL."""
        from app import availability, venue_unavailability_store

        existing = self.get_booking(booking_id)
        if existing is None or existing.status is not BookingStatus.REQUESTED:
            raise StaleBookingStatus
        found = availability.check_booking(
            existing,
            venue_store.repository().get_venue(existing.venue_id),
            self.list_for_venue(existing.venue_id),
            venue_unavailability_store.repository().list_for_venue(existing.venue_id),
            counting_requests=False,
        )
        if not found.available:
            raise SlotTaken
        return existing

    def approve(self, booking_id: int, *, actor_id: int) -> Booking:
        existing = self._approvable(booking_id)
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
