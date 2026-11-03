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
from app.booking_store import Booking, BookingStatus, SupabaseBookings
from app.venue_store import SupabaseVenues
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
        "raw", [True, False, 1.5, -0.5, "1.5", "abc", "30m", "-", "+5", "٣", [], {}]
    )
    def test_refuses_anything_that_is_not_a_whole_number(self, raw):
        with pytest.raises(InvalidMinutes) as refused:
            parse_minutes(raw, which="setup")
        assert str(refused.value) == WHOLE_NUMBER.format(label="setup time")





# =================================================================================
# The occupied window and conflicts
# =================================================================================


class TestOccupiedWindow:

    def test_zero_buffers_occupy_exactly_the_booking(self):
        start, end = occupied_window(
            "2027-03-01T10:00:00", "2027-03-01T12:00:00", setup_minutes=0, turnaround_minutes=0
        )
        assert (start, end) == (datetime(2027, 3, 1, 10), datetime(2027, 3, 1, 12))




class TestFindConflicts:






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




# =================================================================================
# The stores
# =================================================================================


class TestVenueStore:




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



# =================================================================================
# AC1 + AC2 through the routes
# =================================================================================


class TestCreating:


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



class TestEditing:


    def test_a_refused_edit_changes_nothing(self, client, auth_headers):
        staff = auth_headers(STAFF)
        venue = create(client, staff, setupMinutes=30)

        response = put(client, staff, venue["id"], setupMinutes=-1)

        assert response.status_code == 400
        fetched = client.get(f"/venues/{venue['id']}", headers=staff).json()
        assert fetched["setupMinutes"] == 30




# =================================================================================
# AC3 — shown on the venue detail view for Coordinators
# =================================================================================


class TestCoordinatorsSeeThem:

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



