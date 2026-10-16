"""Venue availability: does a booking's slot clash with one already taken? — US15.1.

PLACEHOLDER. US15.1 (the conflict check) is not built yet. US16.1 needs its
check to run again at approval, so this module holds the smallest version of
it, built on US9.4's rules, for approval to call. Whoever builds US15.1 should
extend or replace `find_clashes` here rather than writing a second check, so
the request-time and approval-time checks stay one rule.

What it does now:

* A booking really occupies its venue from its start minus the venue's setup
  time to its end plus its turnaround time (US9.4's `occupied_window`).
  Windows are half-open: back to back is not a clash.
* A slot is taken by a booking that is Confirmed (US16.1), or Held and not yet
  expired (US14.3). Requested bookings do not take it: two requests for the
  same slot may both wait, and whichever is approved first takes it, which is
  what then blocks the other.

What it does not do yet (US15.1 / US12.2): venue unavailability (US12.1
blackouts) and operating hours.

`approve_venue_booking` in SUPABASE_ADD_BOOKING_DECISIONS.sql applies the same
rule in SQL, under a lock, so two approvals at once cannot both pass.
"""

from datetime import datetime

from app import booking_store
from app.booking_store import Booking, BookingStatus
from app.venue_store import Venue
from app.venue_turnaround import OccupiedBooking, occupied_window


def takes_slot(booking: Booking, now: datetime) -> bool:
    """Whether a booking already takes its slot, so others cannot be approved into it."""
    if booking.status is BookingStatus.CONFIRMED:
        return True
    return booking.status is BookingStatus.HELD and not booking.hold_expired_at(now)


def occupied(booking: Booking, venue: Venue | None) -> OccupiedBooking:
    """The booking with its full window, setup and turnaround included (US9.4)."""
    setup, turnaround = venue.buffers if venue is not None else (0, 0)
    start, end = occupied_window(
        booking.starts_at, booking.ends_at, setup_minutes=setup, turnaround_minutes=turnaround
    )
    return OccupiedBooking(booking, start, end)


def find_clashes(
    booking: Booking,
    venue: Venue | None,
    bookings_at_venue: list[Booking],
    *,
    now: datetime | None = None,
) -> list[OccupiedBooking]:
    """The bookings at this venue that take a slot overlapping this one, soonest first."""
    current = now or booking_store.local_now()
    mine = occupied(booking, venue)
    clashes: list[OccupiedBooking] = []
    for other in bookings_at_venue:
        if other.id == booking.id or other.venue_id != booking.venue_id:
            continue
        if not takes_slot(other, current):
            continue
        try:
            theirs = occupied(other, venue)
        except ValueError:
            continue
        if theirs.occupied_from < mine.occupied_to and mine.occupied_from < theirs.occupied_to:
            clashes.append(theirs)
    return sorted(clashes, key=lambda item: (item.occupied_from, item.booking.id))
