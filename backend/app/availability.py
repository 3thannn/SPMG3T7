"""Venue availability: is a booking's slot free at its venue? — US15.1.

A request is checked against the full time a venue is occupied, not just the
event's advertised hours, so a Coordinator cannot book a room that is still
being prepared or reset:

* A booking occupies its venue from its start minus the venue's setup time to
  its end plus its turnaround time (US9.4's `occupied_window`). The customer's
  own case: 10:00-12:00 with 30 minutes' setup and 45 minutes' turnaround
  occupies 09:30-12:45.
* A request is blocked when that window overlaps another active booking's
  window at the same venue. Held (until it expires), Requested and Confirmed
  count; Expired holds, Cancelled and Rejected bookings do not (and Replaced,
  once US14.5 adds it, will not either: only `HOLDS_VENUE` statuses count).
* It is also blocked when the window overlaps a venue unavailability period
  (US12.1). A period covers whole days, from the start of its first day to the
  end of its last.
* Windows are half-open: one ending at 12:45 and the next starting at 12:45 is
  back to back, not a clash.
* A blocked request says which booking or period it clashes with.

Approval (US16.1) runs the same rule again with one difference: another
*Requested* booking does not block it. Two requests can only overlap if they
raced each other or a setup/turnaround change made them overlap (US15.2), and
if pending requests blocked each other neither could ever be approved.
Whichever is approved first takes the slot, which is then what blocks the
other. `approve_venue_booking` and `request_venue_and_plan` in
SUPABASE_ADD_BOOKING_CONFLICTS.sql apply the same rules in SQL, under a lock on
the venue, so two writes at once cannot both pass.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app import booking_store
from app.booking_store import Booking, BookingStatus
from app.venue_store import Venue
from app.venue_turnaround import OccupiedBooking, occupied_window
from app.venue_unavailability_store import Unavailability


def takes_slot(booking: Booking, now: datetime) -> bool:
    """Whether a booking blocks an *approval*: Confirmed, or Held and not yet expired."""
    if booking.status is BookingStatus.CONFIRMED:
        return True
    return booking.status is BookingStatus.HELD and not booking.hold_expired_at(now)


def blocks_request(booking: Booking, now: datetime) -> bool:
    """Whether a booking blocks a new *request*: Held (unexpired), Requested or Confirmed."""
    return booking.holds_venue_at(now)


def buffers(venue: Venue | None) -> tuple[int, int]:
    """`(setup, turnaround)` in minutes; a venue that cannot be read has none."""
    return venue.buffers if venue is not None else (0, 0)


def occupied(booking: Booking, venue: Venue | None) -> OccupiedBooking:
    """The booking with its full window, setup and turnaround included (US9.4)."""
    setup, turnaround = buffers(venue)
    start, end = occupied_window(
        booking.starts_at, booking.ends_at, setup_minutes=setup, turnaround_minutes=turnaround
    )
    return OccupiedBooking(booking, start, end)


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    """Half-open overlap: touching at one instant is not a clash."""
    return start < other_end and other_start < end


def blackout_window(entry: Unavailability) -> tuple[datetime, datetime]:
    """A US12.1 period as times: midnight on its first day to midnight after its last."""
    return (
        datetime.combine(entry.start_date, time.min),
        datetime.combine(entry.end_date + timedelta(days=1), time.min),
    )


@dataclass(frozen=True)
class SlotCheck:
    """What US15.1 found for one slot at one venue."""

    #: The slot's own occupied window, setup and turnaround included.
    occupied_from: datetime
    occupied_to: datetime
    #: Active bookings whose windows overlap it, soonest first.
    bookings: tuple[OccupiedBooking, ...] = ()
    #: Unavailability periods it overlaps, soonest first.
    blackouts: tuple[Unavailability, ...] = ()

    @property
    def available(self) -> bool:
        return not self.bookings and not self.blackouts


def check_slot(
    venue: Venue | None,
    starts_at: str,
    ends_at: str,
    *,
    bookings_at_venue: Sequence[Booking],
    unavailability: Sequence[Unavailability] = (),
    exclude_id: int | None = None,
    counting_requests: bool = True,
    now: datetime | None = None,
) -> SlotCheck:
    """US15.1: every booking and blackout this slot clashes with.

    `exclude_id` leaves a booking out of its own check. `counting_requests` is
    False only for approval (see the module docstring). Raises ValueError for a
    time that is not ISO-8601, as `occupied_window` does.
    """
    current = now or booking_store.local_now()
    setup, turnaround = buffers(venue)
    mine_from, mine_to = occupied_window(
        starts_at, ends_at, setup_minutes=setup, turnaround_minutes=turnaround
    )
    counts = blocks_request if counting_requests else takes_slot
    venue_id = venue.id if venue is not None else None

    clashes: list[OccupiedBooking] = []
    for other in bookings_at_venue:
        if other.id == exclude_id or (venue_id is not None and other.venue_id != venue_id):
            continue
        if not counts(other, current):
            continue
        try:
            theirs = occupied(other, venue)
        except ValueError:
            # A booking whose times cannot be read is left out rather than guessed at.
            continue
        if _overlaps(mine_from, mine_to, theirs.occupied_from, theirs.occupied_to):
            clashes.append(theirs)

    blackouts = [
        entry
        for entry in unavailability
        if (venue_id is None or entry.venue_id == venue_id)
        and _overlaps(mine_from, mine_to, *blackout_window(entry))
    ]
    return SlotCheck(
        occupied_from=mine_from,
        occupied_to=mine_to,
        bookings=tuple(sorted(clashes, key=lambda item: (item.occupied_from, item.booking.id))),
        blackouts=tuple(sorted(blackouts, key=lambda item: (item.start_date, item.id))),
    )


def check_booking(
    booking: Booking,
    venue: Venue | None,
    bookings_at_venue: Sequence[Booking],
    unavailability: Sequence[Unavailability] = (),
    *,
    counting_requests: bool = True,
    now: datetime | None = None,
) -> SlotCheck:
    """`check_slot` for a booking already on record, leaving it out of its own check."""
    return check_slot(
        venue,
        booking.starts_at,
        booking.ends_at,
        bookings_at_venue=[b for b in bookings_at_venue if b.venue_id == booking.venue_id],
        unavailability=unavailability,
        exclude_id=booking.id,
        counting_requests=counting_requests,
        now=now,
    )


def find_clashes(
    booking: Booking,
    venue: Venue | None,
    bookings_at_venue: list[Booking],
    *,
    now: datetime | None = None,
    counting_requests: bool = False,
) -> list[OccupiedBooking]:
    """The bookings this one clashes with, soonest first. Approval's rule by default.

    Kept for US16.1, which shows a request's booking clashes in its queue. A
    booking whose own times cannot be read clashes with nothing.
    """
    try:
        found = check_booking(
            booking, venue, bookings_at_venue, counting_requests=counting_requests, now=now
        )
    except ValueError:
        return []
    return list(found.bookings)


# -- Saying what clashed ---------------------------------------------------------


def stamp(moment: datetime) -> str:
    """"2027-11-02 09:30": what a person reads, in the venue's own local time."""
    return moment.strftime("%Y-%m-%d %H:%M")


def describe_booking(item: OccupiedBooking, *, title: str = "") -> str:
    """One clashing booking as a phrase. The title is left out unless the reader may see it."""
    other = item.booking
    named = f'"{title}", ' if title else ""
    return (
        f"booking #{other.id} ({named}{other.status}) occupying "
        f"{stamp(item.occupied_from)} to {stamp(item.occupied_to)}"
    )


def describe_blackout(entry: Unavailability) -> str:
    """One unavailability period as a phrase, inclusive dates and any reason."""
    span = (
        entry.start_date.isoformat()
        if entry.start_date == entry.end_date
        else f"{entry.start_date.isoformat()} to {entry.end_date.isoformat()}"
    )
    because = f" ({entry.reason})" if entry.reason else ""
    return f"the venue's unavailable period {span}{because}"


def describe(found: SlotCheck, *, titles: dict[int, str] | None = None) -> list[str]:
    """Every clash as a phrase, bookings first then periods. `titles` by booking id."""
    named = titles or {}
    return [
        describe_booking(item, title=named.get(item.booking.id, "")) for item in found.bookings
    ] + [describe_blackout(entry) for entry in found.blackouts]


def unavailable_message(venue_name: str, found: SlotCheck, phrases: list[str]) -> str:
    """The sentence a blocked request shows: the window, then what it overlaps."""
    return (
        f"{venue_name or 'This venue'} is not available for this booking. With setup and "
        f"turnaround it would occupy {stamp(found.occupied_from)} to "
        f"{stamp(found.occupied_to)}, which overlaps " + "; and ".join(phrases) + "."
    )
