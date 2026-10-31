"""US12.3: what is taking up a venue over a date range.

AC1: from a venue's page, pick a date range (default: the next 14 days).
AC2: a chronological list of Confirmed bookings, Requested bookings, tentative
     holds (with expiry time) and unavailability periods, each labelled by type.
AC3: booking entries show the full occupied window, setup and turnaround
     included (US15.1).
AC4: Expired, Cancelled and Rejected entries are hidden.
"""

from dataclasses import replace
from datetime import date, datetime

import pytest

from app import booking_store
from app.booking_store import Booking, BookingStatus, Cancellation
from app.event_status import EventStatus
from app.event_store import Event
from app.venue_availability import EntryKind, default_range, entries
from app.venue_store import Venue
from app.venue_unavailability_store import Unavailability, UnavailabilityReasonType
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

NOW = datetime(2027, 3, 1, 10, 0)
TODAY = NOW.date()

#: Great Hall, given US9.4's customer example: 30 minutes' setup, 45 turnaround.
VENUE = Venue(
    id=1,
    name="Great Hall",
    location="Main Campus",
    capacity=500,
    facilities="",
    accessibility_features="",
    operating_hours="",
    created_at="2026-01-05T09:00:00",
    updated_at="2026-01-05T09:00:00",
    setup_minutes=30,
    turnaround_minutes=45,
)


def booking(booking_id: int = 1, **overrides) -> Booking:
    fields = {
        "id": booking_id,
        "event_id": 1,
        "venue_id": 1,
        "venue_name": "Great Hall",
        "starts_at": "2027-03-03T10:00:00",
        "ends_at": "2027-03-03T12:00:00",
        "status": BookingStatus.CONFIRMED,
        "requested_by_id": COORDINATOR_ID,
        "requested_at": "2027-02-01T09:00:00",
    }
    return Booking(**{**fields, **overrides})


def period(period_id: int = 1, start: str = "2027-03-05", end: str = "2027-03-06", **overrides):
    fields = {
        "id": period_id,
        "venue_id": 1,
        "start_date": date.fromisoformat(start),
        "end_date": date.fromisoformat(end),
        "reason_type": UnavailabilityReasonType.MAINTENANCE,
        "other_reason": "",
        "created_by_id": 4,
        "created_at": "2027-02-01T09:00:00",
    }
    return Unavailability(**{**fields, **overrides})


def listed(bookings=(), periods=(), first=date(2027, 3, 1), last=date(2027, 3, 14)):
    return entries(VENUE, bookings, periods, first_day=first, last_day=last, now=NOW)


# -- The rule -------------------------------------------------------------------


class TestTheDefaultRange:
    def test_it_is_the_next_14_days_today_included(self):
        assert default_range(TODAY) == (date(2027, 3, 1), date(2027, 3, 14))


class TestWhatIsListed:
    """AC2 and AC4."""

    def test_each_entry_is_labelled_by_type(self):
        found = listed(
            [
                booking(1, status=BookingStatus.CONFIRMED),
                booking(2, status=BookingStatus.REQUESTED, starts_at="2027-03-04T10:00"),
                booking(
                    3,
                    status=BookingStatus.HELD,
                    starts_at="2027-03-08T10:00",
                    ends_at="2027-03-08T12:00",
                    hold_expires_at="2027-03-02T17:00:00",
                ),
            ],
            [period()],
        )

        assert [entry.kind for entry in found] == [
            EntryKind.CONFIRMED,
            EntryKind.REQUESTED,
            EntryKind.UNAVAILABLE,
            EntryKind.HOLD,
        ]

    @pytest.mark.parametrize(
        "status",
        [
            BookingStatus.CANCELLED,
            BookingStatus.REJECTED,
            BookingStatus.EXPIRED,
            BookingStatus.NEEDS_REPLACEMENT,
            BookingStatus.REPLACED,
        ],
    )
    def test_what_does_not_hold_the_venue_is_hidden(self, status):
        assert listed([booking(status=status)]) == []

    def test_a_hold_past_its_expiry_is_hidden_before_the_sweep_marks_it(self):
        lapsed = booking(status=BookingStatus.HELD, hold_expires_at="2027-03-01T09:00:00")

        assert listed([lapsed]) == []

    def test_another_venues_records_are_not_listed(self):
        assert listed([booking(venue_id=2)], [period(venue_id=2)]) == []

    def test_a_booking_whose_times_cannot_be_read_is_left_out(self):
        assert listed([booking(starts_at="not a time")]) == []


class TestTheOccupiedWindow:
    """AC3: US9.4's example, 10:00-12:00, occupies 09:30-12:45."""

    def test_a_booking_spans_setup_to_turnaround(self):
        [entry] = listed([booking()])

        assert entry.starts_at == datetime(2027, 3, 3, 9, 30)
        assert entry.ends_at == datetime(2027, 3, 3, 12, 45)

    def test_a_period_spans_its_whole_days(self):
        [entry] = listed(periods=[period()])

        assert entry.starts_at == datetime(2027, 3, 5)
        assert entry.ends_at == datetime(2027, 3, 7)


class TestTheRange:
    def test_it_is_chronological_by_when_the_venue_is_taken(self):
        found = listed(
            [
                booking(1, starts_at="2027-03-10T10:00", ends_at="2027-03-10T11:00"),
                booking(2, starts_at="2027-03-02T10:00", ends_at="2027-03-02T11:00"),
            ],
            [period(start="2027-03-04", end="2027-03-04")],
        )

        assert [entry.starts_at.day for entry in found] == [2, 4, 10]

    def test_an_entry_running_into_the_range_is_shown(self):
        found = listed(periods=[period(start="2027-02-20", end="2027-03-01")])

        assert len(found) == 1

    def test_setup_alone_can_bring_a_booking_into_the_range(self):
        """Starting 00:15 on the day after the range, its setup begins inside it."""
        early = booking(starts_at="2027-03-15T00:15", ends_at="2027-03-15T02:00")

        assert len(listed([early])) == 1

    def test_one_whose_turnaround_ends_at_midnight_on_the_first_day_is_not(self):
        """Half-open, as US15.1's windows are."""
        late = booking(starts_at="2027-02-28T22:00", ends_at="2027-02-28T23:15")

        assert listed([late]) == []

    def test_entries_after_the_last_day_are_not_shown(self):
        assert listed([booking(starts_at="2027-03-20T10:00", ends_at="2027-03-20T12:00")]) == []


# -- The route ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(booking_store, "local_now", lambda: NOW)


@pytest.fixture
def great_hall(venue_repository):
    """The fixture Great Hall with US9.4's setup and turnaround."""
    venue_repository.venues[0] = replace(
        venue_repository.venues[0], setup_minutes=30, turnaround_minutes=45
    )


def seed_event(event_repository, event_id: int, title: str, coordinator_id: int | None):
    event_repository.events.append(
        Event(
            id=event_id,
            title=title,
            purpose="",
            description="",
            starts_at="2027-03-03T10:00",
            ends_at="2027-03-03T12:00",
            expected_attendance=30,
            status=EventStatus.APPROVED,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="2027-01-01T09:00:00",
            updated_at="2027-01-01T09:00:00",
            coordinator_id=coordinator_id,
        )
    )


@pytest.fixture
def seeded(great_hall, event_repository, booking_repository, unavailability_repository):
    seed_event(event_repository, 1, "Faculty Welcome Night", COORDINATOR_ID)
    seed_event(event_repository, 2, "Someone Else's Gala", 99)
    booking_repository.bookings.extend(
        [
            booking(1, event_id=1),
            booking(
                2,
                event_id=2,
                status=BookingStatus.HELD,
                starts_at="2027-03-08T14:00:00",
                ends_at="2027-03-08T16:00:00",
                hold_expires_at="2027-03-04T17:00:00",
            ),
            booking(
                3,
                event_id=2,
                status=BookingStatus.CANCELLED,
                cancellation=Cancellation(at="2027-02-10", by_id=2, by_name="", reason="x"),
            ),
            booking(4, event_id=1, starts_at="2027-04-01T10:00", ends_at="2027-04-01T12:00"),
        ]
    )
    unavailability_repository.entries.append(
        period(
            start="2027-03-05",
            end="2027-03-06",
            reason_type=UnavailabilityReasonType.OTHER,
            other_reason="Floor polishing",
        )
    )


def view(client, headers, query: str = "", venue_id: str = "1"):
    return client.get(f"/venues/{venue_id}/availability{query}", headers=headers)


@pytest.mark.usefixtures("seeded")
class TestTheRoute:
    def test_with_no_range_it_shows_the_next_14_days(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff")).json()

        assert (body["from"], body["to"]) == ("2027-03-01", "2027-03-14")
        assert [entry["bookingId"] or entry["kind"] for entry in body["entries"]] == [
            "1",
            "unavailable",
            "2",
        ]

    def test_a_booking_entry_carries_both_windows(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff")).json()
        first = body["entries"][0]

        assert (body["setupMinutes"], body["turnaroundMinutes"]) == (30, 45)
        assert first == {
            "kind": "confirmed",
            "startsAt": "2027-03-03T09:30",
            "endsAt": "2027-03-03T12:45",
            "bookingId": "1",
            "eventId": "1",
            "eventTitle": "Faculty Welcome Night",
            "eventStartsAt": "2027-03-03T10:00",
            "eventEndsAt": "2027-03-03T12:00",
            "holdExpiresAt": "",
            "periodId": "",
            "startDate": "",
            "endDate": "",
            "reasonType": "",
            "otherReason": "",
        }

    def test_a_hold_says_when_it_expires(self, client, auth_headers):
        hold = view(client, auth_headers("Venue Staff")).json()["entries"][2]

        assert hold["kind"] == "hold"
        assert hold["holdExpiresAt"] == "2027-03-04T17:00"

    def test_a_period_carries_its_dates_and_reason(self, client, auth_headers):
        closed = view(client, auth_headers("Venue Staff")).json()["entries"][1]

        assert closed["kind"] == "unavailable"
        assert closed["periodId"] == "1"
        assert (closed["startDate"], closed["endDate"]) == ("2027-03-05", "2027-03-06")
        assert (closed["reasonType"], closed["otherReason"]) == ("other", "Floor polishing")

    def test_a_chosen_range_is_used(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff"), "?from=2027-03-25&to=2027-04-05").json()

        assert (body["from"], body["to"]) == ("2027-03-25", "2027-04-05")
        assert [entry["bookingId"] for entry in body["entries"]] == ["4"]

    def test_a_range_with_nothing_in_it_is_an_empty_list(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff"), "?from=2027-05-01&to=2027-05-02").json()

        assert body["entries"] == []

    def test_venue_staff_see_every_events_title(self, client, auth_headers):
        titles = [
            entry["eventTitle"]
            for entry in view(client, auth_headers("Venue Staff")).json()["entries"]
            if entry["bookingId"]
        ]

        assert titles == ["Faculty Welcome Night", "Someone Else's Gala"]

    def test_a_coordinator_sees_only_their_own_events_titles(self, client, auth_headers):
        """US8.6: someone else's booking is shown by number, status and times alone."""
        found = view(client, auth_headers("Event Coordinator")).json()["entries"]
        mine, theirs = found[0], found[2]

        assert (mine["eventId"], mine["eventTitle"]) == ("1", "Faculty Welcome Night")
        assert (theirs["eventId"], theirs["eventTitle"]) == ("", "")
        assert theirs["bookingId"] == "2"
        assert theirs["startsAt"] == "2027-03-08T13:30"

    def test_an_unknown_venue_is_404(self, client, auth_headers):
        assert view(client, auth_headers("Venue Staff"), venue_id="999").status_code == 404

    def test_a_role_without_the_catalogue_is_refused(self, client, auth_headers):
        assert view(client, auth_headers("Event Organiser")).status_code == 403


@pytest.mark.usefixtures("great_hall")
class TestPickingTheRange:
    def test_from_alone_runs_14_days(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff"), "?from=2027-06-01").json()

        assert (body["from"], body["to"]) == ("2027-06-01", "2027-06-14")

    def test_to_alone_runs_the_14_days_before_it(self, client, auth_headers):
        body = view(client, auth_headers("Venue Staff"), "?to=2027-06-14").json()

        assert (body["from"], body["to"]) == ("2027-06-01", "2027-06-14")

    def test_one_day_is_a_range(self, client, auth_headers):
        response = view(client, auth_headers("Venue Staff"), "?from=2027-06-01&to=2027-06-01")

        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("query", "message"),
        [
            ("?from=2027-06-14&to=2027-06-01", "The to date cannot be earlier than the from date."),
            ("?from=01/06/2027", "Give the from date as YYYY-MM-DD."),
            ("?to=2027-02-30", "The to date 2027-02-30 is not a real calendar date."),
            ("?from=2027-01-01&to=2028-01-02", "Pick a range of 366 days or fewer."),
            ("?to=0001-01-05", "That range runs off the calendar. Pick nearer dates."),
            ("?from=9999-12-25", "That range runs off the calendar. Pick nearer dates."),
            (
                "?from=9999-12-31&to=9999-12-31",
                "That range runs off the calendar. Pick nearer dates.",
            ),
        ],
    )
    def test_a_range_that_cannot_be_used_is_refused(self, client, auth_headers, query, message):
        response = view(client, auth_headers("Venue Staff"), query)

        assert response.status_code == 400
        assert response.json()["detail"] == {"code": "invalid_filter", "message": message}
