"""What is taking up a venue over a date range — US12.3.

Coordinators and Venue Staff pick a range on a venue's page (the next 14 days
unless they choose otherwise) and get one chronological list of everything
that occupies the venue in it, each entry labelled by type:

* Confirmed bookings, Requested bookings and tentative holds (with when the
  hold expires). Each shows its full occupied window, setup and turnaround
  included (US9.4, US15.1), because that is when the venue cannot be had.
* Unavailability periods (US12.1), as whole days.

Only what holds the venue is listed, the same `HOLDS_VENUE` rule US15.1's
check uses: a hold past its expiry, and Cancelled, Rejected, Expired,
Needs replacement and Replaced bookings, are left out. So the list is exactly
what would stop a request, which is what "when it can be requested" asks.

An entry is in the range when any part of it overlaps the range, so a booking
that starts before the first day and runs into it is shown. Windows are
half-open, as in US15.1: one whose turnaround ends at midnight on the first day
is not in it.

This module is the rule, kept free of storage and HTTP; the route in
venues.py reads the records and decides which event titles the viewer may see.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from app import availability
from app.booking_store import Booking, BookingStatus
from app.venue_store import Venue
from app.venue_unavailability_store import Unavailability

#: AC1: the range shown before anyone picks one, today included.
DEFAULT_DAYS = 14
#: Team-chosen ceiling: a year is already more than one list can usefully show.
MAX_DAYS = 366


class EntryKind(StrEnum):
    CONFIRMED = "confirmed"
    REQUESTED = "requested"
    HOLD = "hold"
    UNAVAILABLE = "unavailable"


_KINDS = {
    BookingStatus.CONFIRMED: EntryKind.CONFIRMED,
    BookingStatus.REQUESTED: EntryKind.REQUESTED,
    BookingStatus.HELD: EntryKind.HOLD,
}


@dataclass(frozen=True)
class Entry:
    kind: EntryKind
    #: When the venue is taken: the occupied window for a booking, midnight to
    #: midnight for a period. Naive Singapore local time, as bookings are.
    starts_at: datetime
    ends_at: datetime
    booking: Booking | None = None
    period: Unavailability | None = None


def default_range(today: date) -> tuple[date, date]:
    """AC1: the next 14 days, today being the first."""
    return today, today + timedelta(days=DEFAULT_DAYS - 1)


def entries(
    venue: Venue,
    bookings: Iterable[Booking],
    periods: Iterable[Unavailability],
    *,
    first_day: date,
    last_day: date,
    now: datetime,
) -> list[Entry]:
    """Everything occupying the venue between the two days, both included, in time order."""
    range_start = datetime.combine(first_day, time.min)
    range_end = datetime.combine(last_day + timedelta(days=1), time.min)

    found: list[Entry] = []
    for booking in bookings:
        if booking.venue_id != venue.id or not booking.holds_venue_at(now):
            continue
        try:
            window = availability.occupied(booking, venue)
        except ValueError:
            # A time that cannot be read is left out rather than guessed at,
            # as US9.4's re-check does.
            continue
        if window.occupied_from < range_end and range_start < window.occupied_to:
            found.append(
                Entry(
                    kind=_KINDS[booking.status],
                    starts_at=window.occupied_from,
                    ends_at=window.occupied_to,
                    booking=booking,
                )
            )
    for period in periods:
        if period.venue_id != venue.id:
            continue
        start, end = availability.blackout_window(period)
        if start < range_end and range_start < end:
            found.append(
                Entry(kind=EntryKind.UNAVAILABLE, starts_at=start, ends_at=end, period=period)
            )
    return sorted(found, key=_order)


def _order(entry: Entry) -> tuple:
    """Start first, then end. A tie puts the period first: it is the bigger fact."""
    record_id = entry.booking.id if entry.booking else entry.period.id if entry.period else 0
    return (entry.starts_at, entry.ends_at, entry.kind is not EntryKind.UNAVAILABLE, record_id)
