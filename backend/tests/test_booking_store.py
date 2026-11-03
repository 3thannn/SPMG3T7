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
    Booking,
    BookingStatus,
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










CANCELLED_ROW = {
    **ROW,
    "status": "Cancelled",
    "cancelled_at": "2026-10-08T10:00:00",
    "cancelled_by_id": 2,
    "cancellation_reason": "Numbers dropped.",
    "cancelled_by": {"name": "Priya"},
}






