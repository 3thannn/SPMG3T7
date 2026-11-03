"""The blackout store itself — US12.1.

The route tests run against `InMemoryUnavailability`, which covers the rules.
This file covers the rest: that `SupabaseUnavailability` asks PostgREST for the
right thing (the same gap `test_venue_store` closes for venues — a real store
that ignored its venue id would otherwise pass every other test), that a row is
read back faithfully, and that the in-memory stand-in keeps the real one's order.
"""

from dataclasses import dataclass, field
from datetime import date

import pytest

from app import supabase_client, venue_unavailability_store
from app.venue_unavailability_store import (
    COLUMNS,
    TABLE,
    InMemoryUnavailability,
    SupabaseUnavailability,
    Unavailability,
    to_unavailability,
)

ROW = {
    "id": 7,
    "venue_id": 1,
    "start_date": "2026-11-02",
    "end_date": "2026-11-06",
    "reason_type": "maintenance",
    "other_reason": "",
    "created_by_id": 3,
    "created_at": "2026-10-01T09:00:00",
}


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

    def lte(self, column: str, value):
        self.calls.append(("lte", column, value))
        return self

    def gte(self, column: str, value):
        self.calls.append(("gte", column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self.calls.append(("order", column, desc))
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
    def test_it_reads_the_blackout_table_for_one_venue(self, query):
        SupabaseUnavailability().list_for_venue(1)

        assert query.calls[0] == ("table", TABLE)
        assert query.named("select") == [("select", COLUMNS)]
        assert query.named("eq") == [("eq", "venue_id", 1)]




    def test_no_rows_is_an_empty_list(self, query):
        query.rows = []

        assert SupabaseUnavailability().list_for_venue(1) == []



class TestSupabaseCreating:
    def create(self, **overrides) -> Unavailability:
        arguments = {
            "venue_id": 1,
            "start_date": date(2026, 11, 2),
            "end_date": date(2026, 11, 6),
            "reason_type": "maintenance",
            "other_reason": "",
            "created_by_id": 3,
            **overrides,
        }
        return SupabaseUnavailability().create(**arguments)

    def test_it_inserts_into_the_blackout_table(self, query):
        self.create()

        assert query.calls[0] == ("table", TABLE)
        assert len(query.named("insert")) == 1







class TestSupabaseOverlap:
    """Which venues a planning window rules out, asked of the database."""

    def test_it_asks_for_ranges_overlapping_the_window_inclusively(self, query):
        SupabaseUnavailability().venues_unavailable_between(date(2026, 11, 2), date(2026, 11, 6))

        assert query.calls[0] == ("table", TABLE)
        assert query.named("select") == [("select", "venue_id")]
        # Starts no later than the window ends, and ends no earlier than it starts.
        assert query.named("lte") == [("lte", "start_date", "2026-11-06")]
        assert query.named("gte") == [("gte", "end_date", "2026-11-02")]



    def test_nothing_overlapping_is_an_empty_set(self, query):
        query.rows = None

        blocked = SupabaseUnavailability().venues_unavailable_between(
            date(2026, 11, 2), date(2026, 11, 6)
        )

        assert blocked == frozenset()


class TestReadingARow:




    def test_dates_already_parsed_are_accepted(self):
        """A driver that hands back `date` objects reads the same as one that sends text."""
        entry = to_unavailability(
            {**ROW, "start_date": date(2026, 11, 2), "end_date": date(2026, 11, 6)}
        )

        assert entry.start_date == date(2026, 11, 2)
        assert entry.end_date == date(2026, 11, 6)


class TestInMemoryStore:
    def create(self, store: InMemoryUnavailability, start: date, end: date, venue_id: int = 1):
        return store.create(
            venue_id=venue_id,
            start_date=start,
            end_date=end,
            reason_type="maintenance",
            other_reason="",
            created_by_id=3,
        )




    @pytest.mark.parametrize(
        ("start", "end", "blocked"),
        [
            (date(2026, 11, 2), date(2026, 11, 6), True),  # the same days
            (date(2026, 10, 1), date(2026, 11, 2), True),  # ends on its first day
            (date(2026, 11, 6), date(2026, 12, 1), True),  # starts on its last day
            (date(2026, 11, 4), date(2026, 11, 4), True),  # one day inside it
            (date(2026, 10, 1), date(2026, 11, 1), False),  # ends the day before
            (date(2026, 11, 7), date(2026, 12, 1), False),  # starts the day after
        ],
    )
    def test_overlap_is_inclusive_at_both_ends(self, start, end, blocked):
        store = InMemoryUnavailability()
        self.create(store, date(2026, 11, 2), date(2026, 11, 6), venue_id=1)

        assert (1 in store.venues_unavailable_between(start, end)) is blocked



class TestSwappingTheStore:
    def test_use_repository_returns_the_previous_store(self, unavailability_repository):
        replacement = InMemoryUnavailability()

        previous = venue_unavailability_store.use_repository(replacement)
        try:
            assert previous is unavailability_repository
            assert venue_unavailability_store.repository() is replacement
        finally:
            venue_unavailability_store.use_repository(previous)
