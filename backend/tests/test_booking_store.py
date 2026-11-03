"""The booking store itself — US14.1.

The route tests run against `InMemoryBookings`, which covers the rules. This
file covers the rest: that `SupabaseBookings` asks PostgREST for the right thing
(a real store that ignored its event id would otherwise pass every other test),
that a row is read back faithfully, and that the in-memory stand-in keeps the
real one's order.
"""

from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import pytest

from app import supabase_client
from app.booking_store import (
    COLUMNS,
    TABLE,
    Booking,
    BookingStatus,
    InMemoryBookings,
    StaleBookingStatus,
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
    "headcount": 100,
    "required_layout": "Theatre",
    "required_facilities": ["projector"],
    "accessibility_needs": ["hearing loop"],
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
    headcount=100,
    required_layout="Theatre",
    required_facilities=("projector",),
    accessibility_needs=("hearing loop",),
)




@pytest.mark.parametrize("count", [None, 0, 3])
def test_supabase_counts_bookings_for_the_given_blackout(monkeypatch, count):
    client = MagicMock()
    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value.count = count
    monkeypatch.setattr(supabase_client, "admin", lambda: client)

    assert SupabaseBookings().count_flagged_by_unavailability(42) == (count or 0)
    client.table.assert_called_once_with(TABLE)
    query.select.assert_called_once_with("id", count="exact")
    query.eq.assert_called_once_with("flagged_by_unavailability_id", 42)


def test_in_memory_counts_only_bookings_flagged_by_the_given_blackout():
    store = InMemoryBookings(bookings=[
        BOOKING,
        replace(BOOKING, id=8, flagged_by_unavailability_id=42),
        replace(BOOKING, id=9, flagged_by_unavailability_id=42),
        replace(BOOKING, id=10, flagged_by_unavailability_id=43),
    ])

    assert store.count_flagged_by_unavailability(42) == 2
    assert store.count_flagged_by_unavailability(43) == 1
    assert store.count_flagged_by_unavailability(99) == 0


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

    def update(self, changes: dict):
        self.calls.append(("update", changes))
        return self

    def eq(self, column: str, value):
        self.calls.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list):
        self.calls.append(("in", column, values))
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





    def test_no_rows_is_an_empty_list(self, query):
        query.rows = []

        assert SupabaseBookings().list_for_event(900) == []



class TestSupabaseCreate:
    def create(self):
        return SupabaseBookings().create(
            event_id=900,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=2,
            headcount=100,
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




class TestSupabaseCreateNeeds:
    """US18.1: what the booking needs goes in with it."""


    def test_no_layout_is_stored_as_null(self, query):
        SupabaseBookings().create(
            event_id=900,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=2,
            headcount=120,
        )

        [(_, row)] = query.named("insert")
        assert row["required_layout"] is None
        assert row["required_facilities"] == []




class TestToBooking:
    def test_an_embedded_list_is_read_as_its_first_item(self):
        """PostgREST returns a to-one embed as an object, but older versions sent a list."""
        assert to_booking({**ROW, "venues": [{"name": "Great Hall"}]}).venue_name == "Great Hall"



    def test_an_unknown_status_is_refused_loudly(self):
        with pytest.raises(ValueError):
            to_booking({**ROW, "status": "Approved"})


CANCELLED_ROW = {
    **ROW,
    "status": "Cancelled",
    "cancelled_at": "2026-10-08T10:00:00",
    "cancelled_by_id": 2,
    "cancellation_reason": "Numbers dropped.",
    "cancelled_by": {"name": "Priya"},
}


class TestSupabaseCancel:
    """US14.2: one conditional update, then the row read back."""

    def test_it_writes_the_status_who_when_and_why(self, query):
        query.rows = [dict(CANCELLED_ROW)]

        SupabaseBookings().cancel(7, actor_id=2, reason="Numbers dropped.")

        [(_, changes)] = query.named("update")
        assert changes["status"] == "Cancelled"
        assert changes["cancelled_by_id"] == 2
        assert changes["cancellation_reason"] == "Numbers dropped."
        assert changes["cancelled_at"]
        assert set(changes) == {"status", "cancelled_at", "cancelled_by_id", "cancellation_reason"}




    def test_no_row_updated_means_it_was_no_longer_requested(self, query):
        query.rows = []

        with pytest.raises(StaleBookingStatus):
            SupabaseBookings().cancel(7, actor_id=2, reason="Numbers dropped.")


class TestCancellationColumns:




    def test_holds_venue_follows_the_status(self):
        assert to_booking(ROW).holds_venue
        assert not to_booking(CANCELLED_ROW).holds_venue


class TestInMemory:



    def test_cancel_twice_is_stale_like_the_real_store(self):
        store = InMemoryBookings()
        booking = store.create(
            event_id=900,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=2,
            headcount=100,
        )
        store.cancel(booking.id, actor_id=2, reason="Numbers dropped.")

        with pytest.raises(StaleBookingStatus):
            store.cancel(booking.id, actor_id=2, reason="Again.")

