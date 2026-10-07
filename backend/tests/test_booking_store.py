"""The booking store itself — US14.1.

The route tests run against `InMemoryBookings`, which covers the rules. This
file covers the rest: that `SupabaseBookings` asks PostgREST for the right thing
(a real store that ignored its event id would otherwise pass every other test),
that a row is read back faithfully, and that the in-memory stand-in keeps the
real one's order.
"""

from dataclasses import dataclass, field

import pytest

from app import supabase_client
from app.booking_store import (
    COLUMNS,
    TABLE,
    Booking,
    BookingStatus,
    InMemoryBookings,
    SupabaseBookings,
    to_booking,
)

ROW = {
    "id": 7,
    "event_id": 900,
    "venue_id": 1,
    "start_at": "2027-11-02T09:00:00",
    "end_at": "2027-11-02T17:00:00",
    "status": "Requested",
    "requested_by_id": 2,
    "created_at": "2026-10-07T09:00:00",
    "venues": {"name": "Great Hall"},
}

BOOKING = Booking(
    id=7,
    event_id=900,
    venue_id=1,
    venue_name="Great Hall",
    starts_at="2027-11-02T09:00:00",
    ends_at="2027-11-02T17:00:00",
    status=BookingStatus.REQUESTED,
    requested_by_id=2,
    requested_at="2026-10-07T09:00:00",
)


@dataclass
class FakeResponse:
    data: list[dict] | None


@dataclass
class FakeQuery:
    """Records each call in order and answers with `rows`, like PostgREST's builder."""

    calls: list[tuple] = field(default_factory=list)
    rows: list[dict] | None = field(default_factory=lambda: [dict(ROW)])

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def insert(self, row: dict):
        self.calls.append(("insert", row))
        return self

    def eq(self, column: str, value):
        self.calls.append(("eq", column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, count: int):
        self.calls.append(("limit", count))
        return self

    def execute(self):
        self.calls.append(("execute",))
        return FakeResponse(self.rows)

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]


@dataclass
class FakeClient:
    query: FakeQuery

    def table(self, name: str):
        self.query.calls.append(("table", name))
        return self.query


@pytest.fixture
def query(monkeypatch):
    recorder = FakeQuery()
    monkeypatch.setattr(supabase_client, "admin", lambda: FakeClient(recorder))
    return recorder


class TestSupabaseListing:
    def test_it_reads_the_booking_table_for_one_event(self, query):
        SupabaseBookings().list_for_event(900)

        assert query.calls[0] == ("table", TABLE)
        assert query.named("select") == [("select", COLUMNS)]
        assert query.named("eq") == [("eq", "event_id", 900)]

    def test_it_embeds_the_venue_name(self):
        assert "venues(name)" in COLUMNS

    def test_it_asks_for_soonest_first_with_stable_ties(self, query):
        SupabaseBookings().list_for_event(900)

        assert query.named("order") == [
            ("order", "start_at", False),
            ("order", "end_at", False),
            ("order", "id", False),
        ]

    def test_it_filters_before_it_executes(self, query):
        SupabaseBookings().list_for_event(900)

        verbs = [call[0] for call in query.calls]
        assert verbs.index("eq") < verbs.index("execute")
        assert verbs[-1] == "execute"

    def test_rows_come_back_as_bookings(self, query):
        assert SupabaseBookings().list_for_event(900) == [BOOKING]

    def test_no_rows_is_an_empty_list(self, query):
        query.rows = []

        assert SupabaseBookings().list_for_event(900) == []

    def test_a_null_data_payload_is_an_empty_list(self, query):
        """PostgREST can answer with `data: None`; that is no rows, not a crash."""
        query.rows = None

        assert SupabaseBookings().list_for_event(900) == []


class TestSupabaseCreate:
    def create(self):
        return SupabaseBookings().create(
            event_id=900,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=2,
        )

    def test_it_inserts_one_requested_row(self, query):
        self.create()

        [(_, row)] = query.named("insert")
        assert row["event_id"] == 900
        assert row["venue_id"] == 1
        assert row["start_at"] == "2027-11-02T09:00"
        assert row["end_at"] == "2027-11-02T17:00"
        assert row["status"] == "Requested"
        assert row["requested_by_id"] == 2
        assert row["created_at"]

    def test_it_sends_no_id(self, query):
        """The id is the database's to assign."""
        self.create()

        [(_, row)] = query.named("insert")
        assert "id" not in row

    def test_it_reads_the_row_back_for_the_venue_name(self, query):
        booking = self.create()

        assert ("eq", "id", 7) in query.named("eq")
        assert booking.venue_name == "Great Hall"


class TestSupabaseVenueHasBookings:
    def test_it_asks_about_one_venue_and_one_row(self, query):
        SupabaseBookings().venue_has_bookings(1)

        assert query.calls[0] == ("table", TABLE)
        assert query.named("eq") == [("eq", "venue_id", 1)]
        assert query.named("limit") == [("limit", 1)]

    def test_a_row_means_booked(self, query):
        assert SupabaseBookings().venue_has_bookings(1) is True

    def test_no_rows_means_free_to_delete(self, query):
        query.rows = []

        assert SupabaseBookings().venue_has_bookings(1) is False


class TestToBooking:
    def test_an_embedded_list_is_read_as_its_first_item(self):
        """PostgREST returns a to-one embed as an object, but older versions sent a list."""
        assert to_booking({**ROW, "venues": [{"name": "Great Hall"}]}).venue_name == "Great Hall"

    @pytest.mark.parametrize("venues", [None, [], {}])
    def test_a_missing_embed_is_an_empty_name(self, venues):
        assert to_booking({**ROW, "venues": venues}).venue_name == ""

    def test_a_null_requester_stays_null(self):
        """`requested_by_id` is SET NULL when the user goes; the booking stays."""
        assert to_booking({**ROW, "requested_by_id": None}).requested_by_id is None

    def test_an_unknown_status_is_refused_loudly(self):
        with pytest.raises(ValueError):
            to_booking({**ROW, "status": "Approved"})


class TestInMemory:
    def test_it_keeps_the_real_stores_order(self):
        store = InMemoryBookings()
        for start, end in [
            ("2027-11-02T13:00", "2027-11-02T15:00"),
            ("2027-11-02T09:00", "2027-11-02T17:00"),
            ("2027-11-02T09:00", "2027-11-02T12:00"),
        ]:
            store.create(
                event_id=900, venue_id=1, starts_at=start, ends_at=end, requested_by_id=2
            )

        listed = store.list_for_event(900)

        assert [(b.starts_at, b.ends_at) for b in listed] == [
            ("2027-11-02T09:00", "2027-11-02T12:00"),
            ("2027-11-02T09:00", "2027-11-02T17:00"),
            ("2027-11-02T13:00", "2027-11-02T15:00"),
        ]

    def test_it_reads_the_venue_name_from_the_catalogue(self):
        booking = InMemoryBookings().create(
            event_id=900,
            venue_id=3,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=2,
        )

        assert booking.venue_name == "Seminar Room 4"
