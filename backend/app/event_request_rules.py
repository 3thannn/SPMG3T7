"""The rules an event request must satisfy — Event Request Creation.

An *event request* is the Organiser's completed proposal: unlike the US4.2
draft, it is filled in fully and goes straight to `Submitted`, because there is
nothing left to come back and finish. That difference is the whole reason this
module exists alongside `event_status`: US4.2 asks "may this move?", and this
asks "is there enough here to move it in the first place?".

Nothing here imports FastAPI. The rules are plain functions over plain strings
so they can be read and tested without a request in hand; the route in
`event_requests` turns an `InvalidField` into the 400 the client sees.

Two shapes the schema forced, both worth knowing:

* The form asks for a date, a start time and an end time as three fields,
  because that is how a person thinks about an event. The table holds two
  timestamps — `proposed_date` for the start and `end_date` for the end — so
  the three are recombined here, on the same day. An event that runs past
  midnight is therefore not expressible, which is a real limitation and a
  deliberate one: "end time after start time" is the rule the story states, and
  an overnight event would need a second date field to say so unambiguously.
* Times are kept as naive local strings, like every other timestamp in this
  project. Converting to an aware datetime here and back in the browser would
  shift an event by the server's offset — the bug that puts an event on the
  wrong day.

The limits below are team-chosen defaults, not customer-confirmed. `NAME_MAX`
and `PURPOSE_MAX` mirror VARCHAR(255) and VARCHAR(500) exactly, so those two are
the database's opinion rather than ours. The rest are ours, and are the numbers
to revisit once the customer has one.
"""

import re
from dataclasses import dataclass
from datetime import date, time

#: `events.name` is VARCHAR(255) and `events.purpose` VARCHAR(500).
NAME_MAX = 255
PURPOSE_MAX = 500
#: `events.description` is unbounded `text`. The cap is ours: a field with no
#: limit at all is a field someone can post a novel into.
DESCRIPTION_MAX = 2000
#: Attendance must be a positive integer (the story). The ceiling is ours, and
#: is there to catch a slipped keypress rather than to express a venue limit.
ATTENDANCE_MIN = 1
ATTENDANCE_MAX = 1_000_000

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
#: Seconds are optional because a browser's <input type="time"> sends them once
#: a step smaller than a minute is set, and the value means the same either way.
_TIME = re.compile(r"^(\d{2}):(\d{2})(?::(\d{2}))?$")
_WHOLE_NUMBER = re.compile(r"[+-]?\d+")


class InvalidField(Exception):
    """One field is wrong, named so the form can put the message beside it.

    Raised on the first failure rather than collected: the client checks every
    field before it sends, so by the time a request reaches the server the
    realistic case is one bad field, and one clear sentence beats a list.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class EventRequest:
    """A request that passed every rule, in the shape the store writes."""

    name: str
    purpose: str
    description: str
    #: "YYYY-MM-DDTHH:MM" — the date and start time, for `proposed_date`.
    starts_at: str
    #: The same date and the end time, for `end_date`.
    ends_at: str
    expected_attendance: int


def parse_date(raw: str) -> date | None:
    """A calendar date, or None if it is not one. Deliberately strict.

    `date.fromisoformat` also accepts compact forms like `20261102` and week
    dates, which a form field should not quietly take. Matching the one format
    the field produces means a malformed value is reported rather than
    reinterpreted.
    """
    match = _DATE.match(raw)
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        # Well-formed but not a real day — 2026-02-30, or month 13.
        return None


def parse_time(raw: str) -> time | None:
    """A time of day, or None. Strict for the same reason, plus one more.

    `time.fromisoformat` accepts an offset (`18:00+08:00`), and an aware time
    cannot be compared with a naive one — so the end-after-start check would
    raise rather than answer. Refusing the offset here keeps that comparison
    total.
    """
    match = _TIME.match(raw)
    if not match:
        return None
    try:
        return time(int(match[1]), int(match[2]), int(match[3] or 0))
    except ValueError:
        return None


def _required_text(raw: str, *, field: str, message: str, maximum: int) -> str:
    value = raw.strip()
    if not value:
        raise InvalidField(field, message)
    return _capped(value, field=field, label=field, maximum=maximum)


def _capped(value: str, *, field: str, label: str, maximum: int) -> str:
    if len(value) > maximum:
        raise InvalidField(field, f"Keep the {label} to {maximum} characters or fewer.")
    return value


def _attendance(raw: object) -> int:
    """The expected head count: a positive whole number, and nothing else.

    A bool is refused explicitly because `bool` subclasses `int` in Python, so
    `true` in the JSON would otherwise arrive as an attendance of one.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise InvalidField("expectedAttendance", "Give the expected attendance.")
    if isinstance(raw, bool):
        raise InvalidField(
            "expectedAttendance", "Expected attendance must be a whole number."
        )
    if isinstance(raw, str):
        if not _WHOLE_NUMBER.fullmatch(raw.strip()):
            raise InvalidField(
                "expectedAttendance", "Expected attendance must be a whole number."
            )
        value = int(raw.strip())
    elif isinstance(raw, int):
        value = raw
    else:
        # A float, a list, anything else JSON can carry.
        raise InvalidField(
            "expectedAttendance", "Expected attendance must be a whole number."
        )
    if value < ATTENDANCE_MIN:
        raise InvalidField(
            "expectedAttendance",
            f"Expected attendance must be at least {ATTENDANCE_MIN}.",
        )
    if value > ATTENDANCE_MAX:
        raise InvalidField(
            "expectedAttendance",
            f"Expected attendance cannot be more than {ATTENDANCE_MAX:,}.",
        )
    return value


def validated(
    *,
    name: str,
    purpose: str,
    description: str,
    proposed_date: str,
    start_time: str,
    end_time: str,
    expected_attendance: object,
    today: date | None = None,
) -> EventRequest:
    """Every rule the story states, in the order the form reads top to bottom.

    `today` is a parameter so the "not in the past" rule can be checked against
    a fixed day rather than against whatever day the suite happens to run on —
    a test that passes in September and fails in November is not a test.
    """
    clean_name = _required_text(
        name, field="name", message="Give the event a name.", maximum=NAME_MAX
    )
    clean_purpose = _required_text(
        purpose,
        field="purpose",
        message="Say what the event is for.",
        maximum=PURPOSE_MAX,
    )
    clean_description = _capped(
        description.strip(),
        field="description",
        label="description",
        maximum=DESCRIPTION_MAX,
    )

    if not proposed_date.strip():
        raise InvalidField("proposedDate", "Give the event a proposed date.")
    day = parse_date(proposed_date.strip())
    if day is None:
        raise InvalidField("proposedDate", "Give the proposed date as YYYY-MM-DD.")
    if day < (today if today is not None else date.today()):
        raise InvalidField("proposedDate", "The proposed date cannot be in the past.")

    if not start_time.strip():
        raise InvalidField("startTime", "Give the event a start time.")
    starts = parse_time(start_time.strip())
    if starts is None:
        raise InvalidField("startTime", "Give the start time as HH:MM.")

    if not end_time.strip():
        raise InvalidField("endTime", "Give the event an end time.")
    ends = parse_time(end_time.strip())
    if ends is None:
        raise InvalidField("endTime", "Give the end time as HH:MM.")

    if ends <= starts:
        raise InvalidField("endTime", "The end time must be after the start time.")

    return EventRequest(
        name=clean_name,
        purpose=clean_purpose,
        description=clean_description,
        starts_at=f"{day.isoformat()}T{starts.strftime('%H:%M')}",
        ends_at=f"{day.isoformat()}T{ends.strftime('%H:%M')}",
        expected_attendance=_attendance(expected_attendance),
    )
