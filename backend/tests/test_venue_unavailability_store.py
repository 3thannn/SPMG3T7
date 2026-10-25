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

    def test_it_asks_for_soonest_first_with_stable_ties(self, query):
        SupabaseUnavailability().list_for_venue(1)

        assert query.named("order") == [
            ("order", "start_date", False),
            ("order", "end_date", False),
            ("order", "id", False),
        ]

    def test_it_filters_before_it_executes(self, query):
        SupabaseUnavailability().list_for_venue(1)

        verbs = [call[0] for call in query.calls]
        assert verbs.index("eq") < verbs.index("execute")
        assert verbs[-1] == "execute"

    def test_rows_come_back_as_ranges(self, query):
        [entry] = SupabaseUnavailability().list_for_venue(1)

        assert entry == Unavailability(
            id=7,
            venue_id=1,
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 6),
            reason_type="maintenance",
            other_reason="",
            created_by_id=3,
            created_at="2026-10-01T09:00:00",
        )

    def test_no_rows_is_an_empty_list(self, query):
        query.rows = []

        assert SupabaseUnavailability().list_for_venue(1) == []

    def test_a_null_data_payload_is_an_empty_list(self, query):
        """PostgREST can answer with `data: None`; that is no rows, not a crash."""
        query.rows = None

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

    def test_the_row_carries_the_range_as_iso_dates(self, query):
        self.create()

        [(_, row)] = query.named("insert")
        assert row["venue_id"] == 1
        assert row["start_date"] == "2026-11-02"
        assert row["end_date"] == "2026-11-06"
        assert row["reason_type"] == "maintenance"
        assert row["other_reason"] == ""
        assert row["created_by_id"] == 3

    def test_the_row_is_timestamped(self, query):
        self.create()

        [(_, row)] = query.named("insert")
        assert row["created_at"]

    def test_the_row_sends_no_id(self, query):
        """The id is the database's to assign."""
        self.create()

        [(_, row)] = query.named("insert")
        assert "id" not in row

    def test_an_empty_other_reason_is_stored_as_null(self, query):
        self.create(other_reason="")

        [(_, row)] = query.named("insert")
        assert row["other_reason"] is None

    def test_the_stored_row_is_what_comes_back(self, query):
        query.rows = [{**ROW, "id": 42}]

        created = self.create()

        assert created.id == 42
        assert created.start_date == date(2026, 11, 2)


class TestSupabaseOverlap:
    """Which venues a planning window rules out, asked of the database."""

    def test_it_asks_for_ranges_overlapping_the_window_inclusively(self, query):
        SupabaseUnavailability().venues_unavailable_between(date(2026, 11, 2), date(2026, 11, 6))

        assert query.calls[0] == ("table", TABLE)
        assert query.named("select") == [("select", "venue_id")]
        # Starts no later than the window ends, and ends no earlier than it starts.
        assert query.named("lte") == [("lte", "start_date", "2026-11-06")]
        assert query.named("gte") == [("gte", "end_date", "2026-11-02")]

    def test_it_does_not_narrow_to_one_venue(self, query):
        SupabaseUnavailability().venues_unavailable_between(date(2026, 11, 2), date(2026, 11, 6))

        assert query.named("eq") == []

    def test_the_answer_is_the_distinct_venue_ids(self, query):
        query.rows = [{"venue_id": 1}, {"venue_id": 3}, {"venue_id": 1}]

        blocked = SupabaseUnavailability().venues_unavailable_between(
            date(2026, 11, 2), date(2026, 11, 6)
        )

        assert blocked == frozenset({1, 3})

    def test_nothing_overlapping_is_an_empty_set(self, query):
        query.rows = None

        blocked = SupabaseUnavailability().venues_unavailable_between(
            date(2026, 11, 2), date(2026, 11, 6)
        )

        assert blocked == frozenset()


class TestReadingARow:
    def test_a_null_other_reason_reads_as_empty(self):
        assert to_unavailability({**ROW, "other_reason": None}).other_reason == ""

    def test_a_missing_other_reason_reads_as_empty(self):
        row = {key: value for key, value in ROW.items() if key != "other_reason"}

        assert to_unavailability(row).other_reason == ""

    def test_a_null_author_stays_null(self):
        """`created_by_id` is SET NULL when the user goes; the range is still shown."""
        assert to_unavailability({**ROW, "created_by_id": None}).created_by_id is None

    def test_a_missing_timestamp_reads_as_empty(self):
        assert to_unavailability({**ROW, "created_at": None}).created_at == ""

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

    def test_ids_are_assigned_in_sequence_from_next_id(self):
        store = InMemoryUnavailability()

        first = self.create(store, date(2026, 1, 1), date(2026, 1, 2))
        second = self.create(store, date(2026, 1, 1), date(2026, 1, 2))

        assert (first.id, second.id) == (101, 102)

    def test_it_orders_by_start_then_end_then_id(self):
        store = InMemoryUnavailability()
        late = self.create(store, date(2026, 3, 1), date(2026, 3, 2))
        long = self.create(store, date(2026, 1, 1), date(2026, 1, 9))
        short = self.create(store, date(2026, 1, 1), date(2026, 1, 2))
        twin = self.create(store, date(2026, 1, 1), date(2026, 1, 2))

        assert store.list_for_venue(1) == [short, twin, long, late]

    def test_it_lists_one_venue_only(self):
        store = InMemoryUnavailability()
        mine = self.create(store, date(2026, 1, 1), date(2026, 1, 2), venue_id=1)
        self.create(store, date(2026, 1, 1), date(2026, 1, 2), venue_id=2)

        assert store.list_for_venue(1) == [mine]

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

    def test_an_unknown_venue_has_nothing(self):
        assert InMemoryUnavailability().list_for_venue(999) == []


class TestSwappingTheStore:
    def test_use_repository_returns_the_previous_store(self, unavailability_repository):
        replacement = InMemoryUnavailability()

        previous = venue_unavailability_store.use_repository(replacement)
        try:
            assert previous is unavailability_repository
            assert venue_unavailability_store.repository() is replacement
        finally:
            venue_unavailability_store.use_repository(previous)
