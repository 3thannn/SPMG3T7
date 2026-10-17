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

from app.booking_store import COLUMNS as BOOKING_COLUMNS
from app.booking_store import Booking, BookingStatus, InMemoryBookings, SupabaseBookings
from app.venue_store import COLUMNS as VENUE_COLUMNS
from app.venue_store import InMemoryVenues, SupabaseVenues, Venue, to_venue
from app.venue_turnaround import (
    MINUTES_MAX,
    InvalidMinutes,
    find_conflicts,
    occupied_window,
    parse_minutes,
    recheck,
)
from tests.test_booking_store import FakeClient as BookingFakeClient
from tests.test_booking_store import FakeQuery as BookingFakeQuery
from tests.test_venue_store import ROW as VENUE_ROW
from tests.test_venue_store import FakeClient as VenueFakeClient
from tests.test_venue_store import FakeQuery as VenueFakeQuery

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


class TestVenueStore:
    def test_every_read_selects_both_columns(self):
        assert "setup_minutes" in VENUE_COLUMNS
        assert "turnaround_minutes" in VENUE_COLUMNS

    def test_a_row_reads_its_minutes(self):
        venue = to_venue({**VENUE_ROW, "setup_minutes": 30, "turnaround_minutes": 45})
        assert (venue.setup_minutes, venue.turnaround_minutes) == (30, 45)
        assert venue.buffers == (30, 45)

    @pytest.mark.parametrize("value", [None, "missing"])
    def test_a_row_without_them_reads_as_0(self, value):
        row = dict(VENUE_ROW)
        if value is None:
            row.update(setup_minutes=None, turnaround_minutes=None)
        venue = to_venue(row)
        assert venue.buffers == (0, 0)

    def test_a_venue_defaults_to_0(self):
        venue = Venue(
            id=1, name="n", location="l", capacity=1, facilities="",
            accessibility_features="", operating_hours="", created_at="", updated_at="",
        )
        assert venue.buffers == (0, 0)

    @pytest.fixture
    def query(self, monkeypatch):
        from app import supabase_client

        recorder = VenueFakeQuery()
        monkeypatch.setattr(supabase_client, "admin", lambda: VenueFakeClient(recorder))
        return recorder

    DETAILS = {
        "name": "Atrium",
        "location": "Science Quarter",
        "capacity": 90,
        "facilities": "",
        "accessibility_features": "",
        "operating_hours": "",
        "supported_layouts": "",
    }

    def test_create_writes_both_columns(self, query):
        SupabaseVenues().create_venue(**self.DETAILS, setup_minutes=30, turnaround_minutes=45)

        (_, row), = query.named("insert")
        assert (row["setup_minutes"], row["turnaround_minutes"]) == (30, 45)

    def test_create_writes_0_when_not_given(self, query):
        SupabaseVenues().create_venue(**self.DETAILS)

        (_, row), = query.named("insert")
        assert (row["setup_minutes"], row["turnaround_minutes"]) == (0, 0)

    def test_save_writes_both_columns(self, query):
        SupabaseVenues().save_venue(1, **self.DETAILS, setup_minutes=10, turnaround_minutes=0)

        (_, changes), = query.named("update")
        assert (changes["setup_minutes"], changes["turnaround_minutes"]) == (10, 0)

    def test_the_in_memory_store_keeps_them(self):
        store = InMemoryVenues()
        created = store.create_venue(**self.DETAILS, setup_minutes=5, turnaround_minutes=6)
        assert created.buffers == (5, 6)

        saved = store.save_venue(created.id, **self.DETAILS, setup_minutes=7, turnaround_minutes=8)
        assert saved.buffers == (7, 8)
        assert store.get_venue(created.id).buffers == (7, 8)


class TestBookingStoreListForVenue:
    def test_supabase_reads_one_venue_s_bookings_soonest_first(self, monkeypatch):
        from app import supabase_client

        recorder = BookingFakeQuery()
        monkeypatch.setattr(supabase_client, "admin", lambda: BookingFakeClient(recorder))

        found = SupabaseBookings().list_for_venue(7)

        assert recorder.named("select") == [("select", BOOKING_COLUMNS)]
        assert recorder.named("eq") == [("eq", "venue_id", 7)]
        assert [call[1] for call in recorder.named("order")] == ["start_at", "end_at", "id"]
        assert len(found) == 1

    def test_supabase_reads_an_empty_answer_as_none(self, monkeypatch):
        from app import supabase_client

        recorder = BookingFakeQuery(rows=None)
        monkeypatch.setattr(supabase_client, "admin", lambda: BookingFakeClient(recorder))

        assert SupabaseBookings().list_for_venue(7) == []

    def test_in_memory_filters_by_venue_and_sorts(self):
        store = InMemoryBookings(
            bookings=[
                booking(3, "2027-03-02T10:00", "2027-03-02T11:00"),
                booking(1, "2027-03-01T10:00", "2027-03-01T11:00", venue_id=2),
                booking(2, "2027-03-01T09:00", "2027-03-01T11:00"),
            ]
        )

        assert [b.id for b in store.list_for_venue(1)] == [2, 3]


# =================================================================================
# AC1 + AC2 through the routes
# =================================================================================


class TestCreating:
    def test_both_default_to_0(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF))

        assert (venue["setupMinutes"], venue["turnaroundMinutes"]) == (0, 0)

    def test_venue_staff_set_both_on_create(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF), setupMinutes=30, turnaroundMinutes=45)

        assert (venue["setupMinutes"], venue["turnaroundMinutes"]) == (30, 45)

    @pytest.mark.parametrize(
        ("sent", "stored"),
        [(None, 0), ("", 0), ("15", 15), (0, 0), (MINUTES_MAX, MINUTES_MAX), (20.0, 20)],
    )
    def test_accepted_values(self, client, auth_headers, sent, stored):
        venue = create(client, auth_headers(STAFF), setupMinutes=sent, turnaroundMinutes=sent)

        assert (venue["setupMinutes"], venue["turnaroundMinutes"]) == (stored, stored)

    @pytest.mark.parametrize(
        ("field", "sent", "message"),
        [
            ("setupMinutes", -1, "The setup time cannot be negative."),
            ("turnaroundMinutes", -5, "The turnaround time cannot be negative."),
            ("setupMinutes", 1.5, WHOLE_NUMBER.format(label="setup time")),
            ("turnaroundMinutes", "abc", WHOLE_NUMBER.format(label="turnaround time")),
            ("setupMinutes", True, WHOLE_NUMBER.format(label="setup time")),
            (
                "setupMinutes",
                MINUTES_MAX + 1,
                "Keep the setup time to 1440 minutes (24 hours) or fewer.",
            ),
            (
                "turnaroundMinutes",
                MINUTES_MAX + 1,
                "Keep the turnaround time to 1440 minutes (24 hours) or fewer.",
            ),
        ],
    )
    def test_refused_values_name_the_field(
        self, client, auth_headers, venue_repository, field, sent, message
    ):
        before = len(venue_repository.venues)

        response = client.post(
            "/venues", json={**NEW_VENUE, field: sent}, headers=auth_headers(STAFF)
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {"code": "invalid_venue", "message": message}
        assert len(venue_repository.venues) == before

    @pytest.mark.parametrize("role", [COORDINATOR, ORGANISER, "Event Coordinator Lead"])
    def test_only_venue_staff_may_create(self, client, auth_headers, role):
        response = client.post(
            "/venues",
            json={**NEW_VENUE, "setupMinutes": 30},
            headers=auth_headers(role),
        )

        assert response.status_code == 403


class TestEditing:
    def test_venue_staff_change_both(self, client, auth_headers):
        staff = auth_headers(STAFF)
        venue = create(client, staff)

        response = put(client, staff, venue["id"], setupMinutes=20, turnaroundMinutes=10)

        assert response.status_code == 200, response.text
        assert (response.json()["setupMinutes"], response.json()["turnaroundMinutes"]) == (20, 10)

    def test_leaving_them_out_of_an_edit_sets_them_back_to_0(self, client, auth_headers):
        """The form always sends both; an API caller that omits one gets the default."""
        staff = auth_headers(STAFF)
        venue = create(client, staff, setupMinutes=30, turnaroundMinutes=30)

        response = put(client, staff, venue["id"])

        assert (response.json()["setupMinutes"], response.json()["turnaroundMinutes"]) == (0, 0)

    def test_a_refused_edit_changes_nothing(self, client, auth_headers):
        staff = auth_headers(STAFF)
        venue = create(client, staff, setupMinutes=30)

        response = put(client, staff, venue["id"], setupMinutes=-1)

        assert response.status_code == 400
        fetched = client.get(f"/venues/{venue['id']}", headers=staff).json()
        assert fetched["setupMinutes"] == 30

    @pytest.mark.parametrize("role", [COORDINATOR, ORGANISER, "Safety Officer"])
    def test_only_venue_staff_may_edit(self, client, auth_headers, role):
        response = put(client, auth_headers(role), "1", setupMinutes=30)

        assert response.status_code == 403

    def test_editing_a_missing_venue_is_404(self, client, auth_headers):
        response = put(client, auth_headers(STAFF), "999", setupMinutes=30)

        assert response.status_code == 404


# =================================================================================
# AC3 — shown on the venue detail view for Coordinators
# =================================================================================


class TestCoordinatorsSeeThem:
    def test_on_the_detail_view(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF), setupMinutes=30, turnaroundMinutes=45)

        response = client.get(f"/venues/{venue['id']}", headers=auth_headers(COORDINATOR))

        assert response.status_code == 200
        assert (response.json()["setupMinutes"], response.json()["turnaroundMinutes"]) == (30, 45)

    def test_in_the_catalogue(self, client, auth_headers):
        create(client, auth_headers(STAFF), setupMinutes=5, turnaroundMinutes=10)

        listed = client.get("/venues", headers=auth_headers(COORDINATOR)).json()

        atrium = next(v for v in listed if v["name"] == "Atrium")
        assert (atrium["setupMinutes"], atrium["turnaroundMinutes"]) == (5, 10)
        hall = next(v for v in listed if v["name"] == "Great Hall")
        assert (hall["setupMinutes"], hall["turnaroundMinutes"]) == (0, 0)


# =================================================================================
# AC4 — changing either value kicks off the re-check; problems are identified
# =================================================================================

GREAT_HALL = {
    "name": "Great Hall",
    "location": "Main Campus, Building A",
    "capacity": 500,
    "facilities": "Stage, PA system, projector",
    "accessibilityFeatures": "Step-free access, hearing loop",
    "operatingHours": "08:00-22:00",
}


@pytest.fixture
def hall_bookings(booking_repository):
    """Two clear bookings at the Great Hall (venue 1), one cancelled, one elsewhere."""
    booking_repository.bookings.extend(
        [
            booking(1, "2027-03-01T10:00", "2027-03-01T12:00"),
            booking(2, "2027-03-01T12:30", "2027-03-01T14:00"),
            booking(3, "2027-03-01T11:00", "2027-03-01T13:00", status=BookingStatus.CANCELLED),
            booking(4, "2027-03-01T10:00", "2027-03-01T12:00", venue_id=2),
        ]
    )
    return booking_repository


def put_hall(client, auth_headers, **fields):
    return client.put("/venues/1", json={**GREAT_HALL, **fields}, headers=auth_headers(STAFF))


class TestRecheckOnChange:
    def test_no_change_no_recheck(self, client, auth_headers, hall_bookings):
        response = put_hall(client, auth_headers, capacity=450)

        assert response.status_code == 200, response.text
        assert response.json()["recheck"] is None

    @pytest.mark.parametrize(
        "change", [{"setupMinutes": 45}, {"turnaroundMinutes": 45}], ids=["setup", "turnaround"]
    )
    def test_changing_either_value_rechecks_and_identifies_the_clash(
        self, client, auth_headers, hall_bookings, change
    ):
        response = put_hall(client, auth_headers, **change)

        assert response.status_code == 200, response.text
        result = response.json()["recheck"]
        assert result["checkedBookings"] == 2
        assert len(result["conflicts"]) == 1
        conflict = result["conflicts"][0]
        assert conflict["causedByChange"] is True
        assert conflict["first"]["bookingId"] == "1"
        assert conflict["first"]["eventId"] == "901"
        assert conflict["second"]["bookingId"] == "2"

    def test_the_conflict_shows_the_occupied_windows(self, client, auth_headers, hall_bookings):
        result = put_hall(client, auth_headers, setupMinutes=30, turnaroundMinutes=45).json()[
            "recheck"
        ]

        assert (result["setupMinutes"], result["turnaroundMinutes"]) == (30, 45)
        first, second = result["conflicts"][0]["first"], result["conflicts"][0]["second"]
        assert first == {
            "bookingId": "1",
            "eventId": "901",
            "startsAt": "2027-03-01T10:00",
            "endsAt": "2027-03-01T12:00",
            "occupiedFrom": "2027-03-01T09:30",
            "occupiedTo": "2027-03-01T12:45",
        }
        assert (second["occupiedFrom"], second["occupiedTo"]) == (
            "2027-03-01T12:00",
            "2027-03-01T14:45",
        )

    def test_a_change_that_leaves_room_finds_nothing(self, client, auth_headers, hall_bookings):
        result = put_hall(client, auth_headers, setupMinutes=15, turnaroundMinutes=15).json()[
            "recheck"
        ]

        assert result["checkedBookings"] == 2
        assert result["conflicts"] == []

    def test_problem_bookings_are_identified_not_removed(
        self, client, auth_headers, hall_bookings
    ):
        before = [(b.id, b.status) for b in hall_bookings.bookings]

        put_hall(client, auth_headers, turnaroundMinutes=120)

        # US15.2 flags them, but nothing is removed and no status changes.
        assert [(b.id, b.status) for b in hall_bookings.bookings] == before
        assert all(
            b.status is BookingStatus.REQUESTED for b in hall_bookings.bookings if b.id != 3
        )

    def test_a_venue_with_no_bookings_rechecks_to_nothing(self, client, auth_headers):
        staff = auth_headers(STAFF)
        venue = create(client, staff)

        result = put(client, staff, venue["id"], setupMinutes=10).json()["recheck"]

        assert result == {
            "setupMinutes": 10,
            "turnaroundMinutes": 0,
            "checkedBookings": 0,
            "conflicts": [],
            "flaggedBookingIds": [],
            "clearedBookingIds": [],
        }

    def test_a_refused_change_does_not_recheck_or_save(
        self, client, auth_headers, hall_bookings, venue_repository
    ):
        response = put_hall(client, auth_headers, setupMinutes=MINUTES_MAX + 1)

        assert response.status_code == 400
        assert venue_repository.get_venue(1).buffers == (0, 0)

    def test_a_create_never_carries_a_recheck(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF), setupMinutes=30)

        assert "recheck" not in venue
