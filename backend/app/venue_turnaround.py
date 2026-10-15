"""Venue setup and turnaround time — US9.4.

ConnectSphere found that an event's advertised start and end are not enough to
say whether a venue is free. Venue Staff need time before each event to prepare
the room (setup) and time after it to reset the room (turnaround). An event
from 10:00 to 12:00 at a venue with 30 minutes' setup and 45 minutes'
turnaround occupies the venue from 09:30 to 12:45.

Each venue carries both values, in whole minutes, 0 by default. This module is
the rule, kept free of storage and HTTP so each part is a plain function:

* `parse_minutes` reads a value a form or API client sent.
* `occupied_window` widens a booking's times by the venue's setup and turnaround.
* `find_conflicts` pairs up active bookings whose occupied windows overlap.
* `recheck` is what changing either value kicks off (US15.2): every booking that
  holds the venue is checked again under the new values, and the ones that now
  clash are identified — never removed. Each conflict says whether the change
  caused it or it was already there, so Venue Staff can tell what they did.

Windows are half-open: a turnaround ending at 12:45 and the next setup starting
at 12:45 is back to back, not a clash.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations

from app.booking_store import Booking

#: Team-chosen ceiling, not customer-confirmed: a day of setup or turnaround is
#: already more than any room needs, and a larger number is a typing mistake.
#: It also keeps the window arithmetic well inside what a datetime can hold.
MINUTES_MAX = 1440

LABELS = {"setup": "setup time", "turnaround": "turnaround time"}


class InvalidMinutes(ValueError):
    """A setup or turnaround value that is not a whole number of minutes in range."""


def parse_minutes(raw: object, *, which: str) -> int:
    """A whole number of minutes, 0 to `MINUTES_MAX`; missing or blank is 0.

    Accepts an int, an integral float (JSON has no int type of its own) or a
    string of digits, so the message for a bad value is this module's sentence
    rather than a framework's. A bool is refused: `true` is not 1 minute.
    """
    label = LABELS[which]
    if raw is None:
        return 0
    if isinstance(raw, bool):
        raise InvalidMinutes(f"Give the {label} as a whole number of minutes, 0 or more.")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return 0
        if not text.isascii() or not text.isdigit():
            raise InvalidMinutes(f"Give the {label} as a whole number of minutes, 0 or more.")
        value = int(text)
    elif isinstance(raw, float):
        if not raw.is_integer():
            raise InvalidMinutes(f"Give the {label} as a whole number of minutes, 0 or more.")
        value = int(raw)
    elif isinstance(raw, int):
        value = raw
    else:
        raise InvalidMinutes(f"Give the {label} as a whole number of minutes, 0 or more.")
    if value < 0:
        raise InvalidMinutes(f"The {label} cannot be negative.")
    if value > MINUTES_MAX:
        raise InvalidMinutes(f"Keep the {label} to {MINUTES_MAX} minutes (24 hours) or fewer.")
    return value


def occupied_window(
    starts_at: str, ends_at: str, *, setup_minutes: int, turnaround_minutes: int
) -> tuple[datetime, datetime]:
    """When a booking really holds the venue: its times widened by both buffers.

    Raises ValueError for a time that is not ISO-8601.
    """
    start = datetime.fromisoformat(starts_at)
    end = datetime.fromisoformat(ends_at)
    return (
        start - timedelta(minutes=setup_minutes),
        end + timedelta(minutes=turnaround_minutes),
    )


@dataclass(frozen=True)
class OccupiedBooking:
    booking: Booking
    occupied_from: datetime
    occupied_to: datetime


@dataclass(frozen=True)
class BookingConflict:
    """Two bookings at one venue whose occupied windows overlap."""

    first: OccupiedBooking
    second: OccupiedBooking
    #: True when the pair did not overlap under the values before the change.
    caused_by_change: bool = False

    @property
    def key(self) -> tuple[int, int]:
        return (self.first.booking.id, self.second.booking.id)


def _occupied(
    bookings: list[Booking], *, setup_minutes: int, turnaround_minutes: int
) -> list[OccupiedBooking]:
    """The bookings that hold the venue, with their windows, earliest first.

    A cancelled booking frees its slot (US14.2), so it cannot clash. A booking
    whose times cannot be read is left out rather than guessed at.
    """
    occupied: list[OccupiedBooking] = []
    for booking in bookings:
        if not booking.holds_venue:
            continue
        try:
            window = occupied_window(
                booking.starts_at,
                booking.ends_at,
                setup_minutes=setup_minutes,
                turnaround_minutes=turnaround_minutes,
            )
        except ValueError:
            continue
        occupied.append(OccupiedBooking(booking, *window))
    return sorted(occupied, key=lambda item: (item.occupied_from, item.booking.id))


def find_conflicts(
    bookings: list[Booking], *, setup_minutes: int, turnaround_minutes: int
) -> tuple[BookingConflict, ...]:
    """Every pair of active bookings whose occupied windows overlap, in time order."""
    occupied = _occupied(
        bookings, setup_minutes=setup_minutes, turnaround_minutes=turnaround_minutes
    )
    return tuple(
        BookingConflict(first, second)
        for first, second in combinations(occupied, 2)
        if first.occupied_from < second.occupied_to and second.occupied_from < first.occupied_to
    )


@dataclass(frozen=True)
class Recheck:
    """The outcome of re-checking a venue's bookings after US9.4's values changed."""

    setup_minutes: int
    turnaround_minutes: int
    #: How many bookings hold the venue and were checked.
    checked: int
    conflicts: tuple[BookingConflict, ...]


def recheck(
    bookings: list[Booking], *, before: tuple[int, int], after: tuple[int, int]
) -> Recheck:
    """US15.2's re-check, as US9.4 kicks it off: identify, never remove.

    `before` and `after` are `(setup_minutes, turnaround_minutes)`.
    """
    previous = {
        conflict.key
        for conflict in find_conflicts(
            bookings, setup_minutes=before[0], turnaround_minutes=before[1]
        )
    }
    current = find_conflicts(bookings, setup_minutes=after[0], turnaround_minutes=after[1])
    return Recheck(
        setup_minutes=after[0],
        turnaround_minutes=after[1],
        checked=len(_occupied(bookings, setup_minutes=after[0], turnaround_minutes=after[1])),
        conflicts=tuple(
            BookingConflict(c.first, c.second, caused_by_change=c.key not in previous)
            for c in current
        ),
    )
