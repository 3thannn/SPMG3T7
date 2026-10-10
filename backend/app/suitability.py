"""Whether a venue suits one booking — US18.1 (Week 4's suitability check).

Before a Coordinator requests a venue, the system says whether it suits the
booking: Suitable, or Not suitable with every reason. A venue is not suitable
if any of these is true, in the story's order:

* the booking's headcount is more than the venue's capacity;
* the booking needs a layout the venue does not support;
* the booking needs a facility or an accessibility feature the venue does not list;
* the booking runs outside the venue's operating hours.

This module is pure: a venue and what a booking needs go in, a verdict comes
out. The routes in `app.events` call it twice — to show the verdict while the
form is filled in, and to refuse the request when it says Not suitable — so what
a Coordinator is shown and what the server enforces cannot disagree.

The venue fields it reads are free text that Venue Staff write (US9.1a), and the
catalogue holds them two ways: as plain lists ("Theatre, standing") and as
Postgres array literals ('{stage,"AV system"}'), left by a seed script that
wrote arrays into TEXT columns. `listed_items` reads both.

Two choices worth knowing:

* Something a booking needs has to be listed to count. A venue with no layouts
  recorded does not support the one asked for, which is the reading US9.3 gives
  an empty accessibility field: an unfilled field is not evidence of a feature.
* Operating hours are the other way round, because they are a limit rather than
  a feature. A venue with no hours recorded, or hours this module cannot read,
  has no limit the booking can be shown to break, so the time is not held
  against it. The verdict carries a note saying the time was not checked,
  rather than refusing every venue nobody has filled in.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app.venue_store import Venue


@dataclass(frozen=True)
class BookingNeeds:
    """What one booking asks of a venue. Empty text and tuples ask for nothing."""

    headcount: int
    starts_at: datetime
    ends_at: datetime
    layout: str = ""
    facilities: tuple[str, ...] = ()
    accessibility: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    #: Why the venue is not suitable, one sentence each. Empty means Suitable.
    reasons: tuple[str, ...] = ()
    #: What could not be checked. Shown with the verdict, never a reason.
    notes: tuple[str, ...] = ()

    @property
    def suitable(self) -> bool:
        return not self.reasons


def _normal(text: str) -> str:
    """Case and spacing aside, so "AV  System" and "av system" are one thing."""
    return " ".join(text.split()).casefold()


def _array_literal_items(inner: str) -> list[str]:
    """The elements of a Postgres array literal, without its braces.

    Elements are separated by commas, and an element with a comma or a space in
    it is double-quoted, with backslash escaping inside the quotes.
    """
    items: list[str] = []
    current: list[str] = []
    quoted = escaped = False
    for character in inner:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\" and quoted:
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == "," and not quoted:
            items.append("".join(current))
            current = []
        else:
            current.append(character)
    items.append("".join(current))
    return items


def listed_items(text: str) -> tuple[str, ...]:
    """The items a venue lists in one of its free-text fields, as written.

    Reads a Postgres array literal ('{stage,"AV system"}', or '{}' for none) and
    a plain list separated by commas, semicolons or new lines.
    """
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        raw = _array_literal_items(stripped[1:-1])
    else:
        raw = re.split(r"[,;\n]", stripped)
    return tuple(item.strip() for item in raw if item.strip())


# -- Operating hours -------------------------------------------------------------

_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_EVERY_DAY = frozenset(range(7))
_DAY_WORDS = {
    "daily": _EVERY_DAY,
    "everyday": _EVERY_DAY,
    "weekdays": frozenset(range(5)),
    "weekends": frozenset({5, 6}),
}
_CLAUSE = re.compile(
    r"(?:(?P<days>[a-z]+(?:\s*[-–]\s*[a-z]+)?)\s+)?"
    r"(?P<open>[0-9]{1,2}:[0-9]{2})\s*[-–]\s*(?P<close>[0-9]{1,2}:[0-9]{2})"
)

#: weekday (Monday is 0) -> the (open, close) windows that day, in minutes.
OpeningHours = dict[int, list[tuple[int, int]]]


def _day(word: str) -> int | None:
    prefix = word[:3]
    return _DAY_NAMES.index(prefix) if prefix in _DAY_NAMES else None


def _days(spec: str | None) -> frozenset[int] | None:
    """The weekdays a clause covers; no day named means every day."""
    if spec is None:
        return _EVERY_DAY
    spec = spec.strip()
    if spec in _DAY_WORDS:
        return _DAY_WORDS[spec]
    ends = [part.strip() for part in re.split(r"[-–]", spec)]
    numbers = [_day(part) for part in ends]
    if any(number is None for number in numbers):
        return None
    first, last = numbers[0], numbers[-1]
    assert first is not None and last is not None  # noqa: S101 — checked above
    # A range may wrap the weekend: Fri-Mon is Friday to Monday.
    return frozenset((first + offset) % 7 for offset in range((last - first) % 7 + 1))


def _minutes(clock: str) -> int | None:
    hours, minutes = (int(part) for part in clock.split(":"))
    if hours > 24 or minutes > 59 or (hours == 24 and minutes):
        return None
    # "23:59" as a closing time means the end of the day, the way it is
    # written on a sign: a venue open "00:00-23:59" is open all day, and a
    # booking ending at midnight is inside it.
    if hours == 23 and minutes == 59:
        return 24 * 60
    return hours * 60 + minutes


def parse_hours(text: str) -> OpeningHours | None:
    """A venue's opening times, or None when they cannot be read.

    Reads clauses like "08:00-22:00", "Mon-Sat 08:00-22:00", "Weekdays
    09:00-17:00", separated by commas or semicolons. A clause that does not
    read, or one that closes no later than it opens (overnight hours), makes
    the whole thing unreadable rather than half-understood.
    """
    hours: OpeningHours = {}
    clauses = [clause.strip() for clause in re.split(r"[,;]", text.casefold()) if clause.strip()]
    if not clauses:
        return None
    for clause in clauses:
        match = _CLAUSE.fullmatch(clause)
        if not match:
            return None
        days = _days(match["days"])
        opens, closes = _minutes(match["open"]), _minutes(match["close"])
        if days is None or opens is None or closes is None or closes <= opens:
            return None
        for day in days:
            hours.setdefault(day, []).append((opens, closes))
    return hours


def within_hours(hours: OpeningHours, starts_at: datetime, ends_at: datetime) -> bool:
    """Whether every moment of the booking falls in an open window.

    Taken a calendar day at a time: each day the booking touches must be an
    open day, and its part of the booking must sit inside one of that day's
    windows. A booking that runs overnight therefore needs a venue open across
    midnight, which is what the rule asks.
    """
    day = starts_at.date()
    while True:
        midnight = datetime.combine(day, time())
        part_start = max(starts_at, midnight)
        part_end = min(ends_at, midnight + timedelta(days=1))
        if part_end > part_start:
            start = (part_start - midnight).total_seconds() / 60
            end = (part_end - midnight).total_seconds() / 60
            windows = hours.get(day.weekday(), [])
            if not any(opens <= start and end <= closes for opens, closes in windows):
                return False
        if part_end >= ends_at:
            return True
        day += timedelta(days=1)


# -- The check ---------------------------------------------------------------------


def _missing(needed: tuple[str, ...], listed: tuple[str, ...]) -> list[str]:
    """What is needed and not listed, matched as a case-insensitive substring.

    Substring, as US9.3's accessibility filter matches: "projector" is met by
    "twin projectors" and "lift" by "Lift access to rooftop level".
    """
    have = [_normal(item) for item in listed]
    return [need for need in needed if not any(_normal(need) in item for item in have)]


def assess(venue: Venue, needs: BookingNeeds) -> Verdict:
    """US18.1: Suitable, or Not suitable with every reason that applies."""
    reasons: list[str] = []
    notes: list[str] = []

    # Equal is suitable: a room for 60 holds 60.
    if needs.headcount > venue.capacity:
        reasons.append(
            f"It holds {venue.capacity} people, and this booking is for {needs.headcount}."
        )

    layout = needs.layout.strip()
    if layout:
        layouts = listed_items(venue.supported_layouts)
        if _normal(layout) not in {_normal(item) for item in layouts}:
            supported = (
                f"It supports: {', '.join(layouts)}."
                if layouts
                else "It has no layouts recorded."
            )
            reasons.append(f"It does not support the {layout} layout. {supported}")

    for facility in _missing(needs.facilities, listed_items(venue.facilities)):
        reasons.append(f"It does not list {facility} among its facilities.")

    for need in _missing(needs.accessibility, listed_items(venue.accessibility_features)):
        reasons.append(f"It does not list {need} among its accessibility features.")

    recorded = venue.operating_hours.strip()
    hours = parse_hours(recorded) if recorded else None
    if not recorded:
        notes.append(
            "Its operating hours are not recorded, so the booking time was not checked."
        )
    elif hours is None:
        notes.append(
            f"Its operating hours ({recorded}) could not be read, so the booking time "
            "was not checked."
        )
    elif not within_hours(hours, needs.starts_at, needs.ends_at):
        reason = f"The booking falls outside its operating hours ({recorded})."
        if needs.starts_at.date() != needs.ends_at.date():
            reason += " A booking over several days can be requested a day at a time."
        reasons.append(reason)

    return Verdict(reasons=tuple(reasons), notes=tuple(notes))
