"""US9.4 — Venue Staff set a setup time and turnaround time for each venue.

Acceptance criteria:

AC1  Two fields per venue: setup time and turnaround time, in minutes, whole
     number >= 0, default 0.
AC2  Settable on create and edit, Venue Staff only.
AC3  Shown on the venue detail view for Coordinators (US9.2).
AC4  Changing either value kicks off the re-check in US15.2: existing bookings
     that become problematic are identified rather than silently removed.

The worked example from the requirement: 10:00-12:00 with 30 minutes' setup and
45 minutes' turnaround occupies the venue from 09:30 to 12:45.
"""

from datetime import datetime

import pytest

from app.booking_store import Booking, BookingStatus
from app.venue_turnaround import (
    MINUTES_MAX,
    InvalidMinutes,
    find_conflicts,
    occupied_window,
    parse_minutes,
    recheck,
)

# Removed imports from deleted test store files

STAFF = "Venue Staff"
COORDINATOR = "Event Coordinator"
ORGANISER = "Event Organiser"

NEW_VENUE = {
    "name": "Atrium",
    "location": "Science Quarter",
    "capacity": 90,
}

WHOLE_NUMBER = "Give the {label} as a whole number of minutes, 0 or more."


def booking(
    booking_id: int,
    starts_at: str,
    ends_at: str,
    *,
    venue_id: int = 1,
    event_id: int | None = None,
    status: BookingStatus = BookingStatus.REQUESTED,
) -> Booking:
    return Booking(
        id=booking_id,
        event_id=event_id if event_id is not None else 900 + booking_id,
        venue_id=venue_id,
        venue_name="Great Hall",
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        requested_by_id=2,
        requested_at="2026-10-01T09:00:00",
    )


def create(client, headers, **fields) -> dict:
    response = client.post("/venues", json={**NEW_VENUE, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def put(client, headers, venue_id: str, **fields):
    return client.put(f"/venues/{venue_id}", json={**NEW_VENUE, **fields}, headers=headers)


# =================================================================================
# AC1 — whole minutes, >= 0, default 0 (the rule, as a plain function)
# =================================================================================


class TestParseMinutes:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, 0),
            ("", 0),
            ("   ", 0),
            (0, 0),
            ("0", 0),
            (1, 1),
            (30, 30),
            ("45", 45),
            (" 45 ", 45),
            (30.0, 30),
            (MINUTES_MAX, MINUTES_MAX),
            (str(MINUTES_MAX), MINUTES_MAX),
        ],
    )
    def test_accepts_whole_minutes_from_0_to_the_ceiling(self, raw, expected):
        assert parse_minutes(raw, which="setup") == expected

    @pytest.mark.parametrize(
        "raw", [True, False, 1.5, -0.5, "1.5", "abc", "30m", "-", "+5", "٣", [], {}]
    )
    def test_refuses_anything_that_is_not_a_whole_number(self, raw):
        with pytest.raises(InvalidMinutes) as refused:
            parse_minutes(raw, which="setup")
        assert str(refused.value) == WHOLE_NUMBER.format(label="setup time")

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            (-1, "The turnaround time cannot be negative."),
            (-1.0, "The turnaround time cannot be negative."),
            # Typed text is read as digits or nothing, so "-1" is not a number at all.
            ("-1", WHOLE_NUMBER.format(label="turnaround time")),
        ],
    )
    def test_refuses_a_negative(self, raw, message):
        with pytest.raises(InvalidMinutes) as refused:
            parse_minutes(raw, which="turnaround")
        assert str(refused.value) == message

    @pytest.mark.parametrize("raw", [MINUTES_MAX + 1, str(MINUTES_MAX + 1), 10**12])
    def test_refuses_more_than_a_day(self, raw):
        with pytest.raises(InvalidMinutes) as refused:
            parse_minutes(raw, which="setup")
        assert str(refused.value) == "Keep the setup time to 1440 minutes (24 hours) or fewer."

    def test_the_ceiling_is_a_day(self):
        assert MINUTES_MAX == 24 * 60


# =================================================================================
# The occupied window and conflicts
# =================================================================================


class TestOccupiedWindow:
    def test_the_requirement_s_worked_example(self):
        """10:00-12:00, 30 setup, 45 turnaround -> 09:30-12:45."""
        start, end = occupied_window(
            "2027-03-01T10:00", "2027-03-01T12:00", setup_minutes=30, turnaround_minutes=45
        )
        assert (start, end) == (datetime(2027, 3, 1, 9, 30), datetime(2027, 3, 1, 12, 45))

    def test_zero_buffers_occupy_exactly_the_booking(self):
        start, end = occupied_window(
            "2027-03-01T10:00:00", "2027-03-01T12:00:00", setup_minutes=0, turnaround_minutes=0
        )
        assert (start, end) == (datetime(2027, 3, 1, 10), datetime(2027, 3, 1, 12))

    def test_buffers_cross_midnight(self):
        start, end = occupied_window(
            "2027-03-01T00:15", "2027-03-01T23:30", setup_minutes=30, turnaround_minutes=60
        )
        assert (start, end) == (datetime(2027, 2, 28, 23, 45), datetime(2027, 3, 2, 0, 30))

    def test_an_unreadable_time_raises(self):
        with pytest.raises(ValueError):
            occupied_window("tomorrow", "2027-03-01T12:00", setup_minutes=0, turnaround_minutes=0)


class TestFindConflicts:
    def test_no_bookings_no_conflicts(self):
        assert find_conflicts([], setup_minutes=30, turnaround_minutes=45) == ()

    def test_bookings_that_only_clash_once_the_buffers_are_counted(self):
        morning = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        lunch = booking(2, "2027-03-01T12:30", "2027-03-01T14:00")

        assert find_conflicts([morning, lunch], setup_minutes=0, turnaround_minutes=0) == ()
        (conflict,) = find_conflicts([morning, lunch], setup_minutes=0, turnaround_minutes=45)
        assert conflict.key == (1, 2)
        assert conflict.first.occupied_to == datetime(2027, 3, 1, 12, 45)
        assert conflict.caused_by_change is False

    def test_back_to_back_windows_do_not_clash(self):
        """Turnaround ending 12:45 and the next setup starting 12:45 is fine."""
        morning = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        afternoon = booking(2, "2027-03-01T13:15", "2027-03-01T15:00")

        assert find_conflicts(
            [morning, afternoon], setup_minutes=30, turnaround_minutes=45
        ) == ()

    def test_one_minute_more_and_they_clash(self):
        morning = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        afternoon = booking(2, "2027-03-01T13:14", "2027-03-01T15:00")

        conflicts = find_conflicts([morning, afternoon], setup_minutes=30, turnaround_minutes=45)
        assert len(conflicts) == 1

    def test_a_cancelled_booking_frees_its_slot(self):
        morning = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        cancelled = booking(
            2, "2027-03-01T11:00", "2027-03-01T13:00", status=BookingStatus.CANCELLED
        )

        assert find_conflicts([morning, cancelled], setup_minutes=60, turnaround_minutes=60) == ()

    def test_a_booking_with_unreadable_times_is_left_out(self):
        morning = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        broken = booking(2, "not-a-time", "2027-03-01T13:00")

        assert find_conflicts([morning, broken], setup_minutes=60, turnaround_minutes=60) == ()

    def test_every_clashing_pair_in_time_order(self):
        late = booking(3, "2027-03-01T12:10", "2027-03-01T13:00")
        early = booking(1, "2027-03-01T10:00", "2027-03-01T12:00")
        middle = booking(2, "2027-03-01T12:05", "2027-03-01T12:30")
        tomorrow = booking(4, "2027-03-02T10:00", "2027-03-02T12:00")

        conflicts = find_conflicts(
            [late, tomorrow, early, middle], setup_minutes=0, turnaround_minutes=15
        )

        assert [conflict.key for conflict in conflicts] == [(1, 2), (1, 3), (2, 3)]


class TestRecheck:
    BOOKINGS = [
        # Already overlap with no buffers at all.
        booking(1, "2027-03-01T10:00", "2027-03-01T12:00"),
        booking(2, "2027-03-01T11:00", "2027-03-01T11:30"),
        # Clear of each other until a turnaround of 30+ minutes.
        booking(3, "2027-03-02T10:00", "2027-03-02T12:00"),
        booking(4, "2027-03-02T12:30", "2027-03-02T13:00"),
        # Not checked: cancelled, and unreadable.
        booking(5, "2027-03-02T11:00", "2027-03-02T13:00", status=BookingStatus.CANCELLED),
        booking(6, "", ""),
    ]

    def test_identifies_what_the_change_made_clash_and_what_already_did(self):
        result = recheck(self.BOOKINGS, before=(0, 0), after=(15, 30))

        assert result.setup_minutes == 15
        assert result.turnaround_minutes == 30
        assert result.checked == 4
        assert [(c.key, c.caused_by_change) for c in result.conflicts] == [
            ((1, 2), False),
            ((3, 4), True),
        ]

    def test_lowering_the_values_can_clear_a_conflict(self):
        result = recheck(self.BOOKINGS, before=(15, 30), after=(0, 0))

        assert [c.key for c in result.conflicts] == [(1, 2)]
        assert result.conflicts[0].caused_by_change is False

    def test_nothing_is_removed_from_the_list_it_was_given(self):
        bookings = list(self.BOOKINGS)
        recheck(bookings, before=(0, 0), after=(60, 60))
        assert bookings == self.BOOKINGS


# =================================================================================
# The stores
# =================================================================================
