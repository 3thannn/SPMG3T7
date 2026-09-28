"""The Supabase venue store's query building — US9.2, US9.3 and US9.1a-c.

Every other venue test runs against `InMemoryVenues`, which is the right call
for the rules: they are about who may do what, and a network round trip does not
make that truer. But it leaves one gap, and this file exists because that gap bit
during development.

`InMemoryVenues` filters in Python. `SupabaseVenues` has to ask Postgres to
filter, and the two are separate implementations of the same promise. A
`SupabaseVenues.list_venues` that ignored its filters entirely passed the whole
suite, because nothing the suite ran ever called it. So these tests drive the
real store against a fake query builder and assert on the calls it makes — not
on rows, which is what the in-memory tests already cover.
"""

from dataclasses import dataclass, field

import pytest

from app import supabase_client, venue_store
from app.venue_store import NO_FILTERS, SupabaseVenues, VenueFilters

ROW = {
    "id": 1,
    "name": "Great Hall",
    "location": "Main Campus",
    "capacity": 500,
    "facilities": "Stage",
    "accessibility_features": "Step-free access",
    "operating_hours": "08:00-22:00",
    "supported_layouts": "Theatre",
    "created_at": "2026-01-05T09:00:00",
    "updated_at": "2026-01-05T09:00:00",
}


@dataclass
class FakeResponse:
    data: list[dict]


@dataclass
class FakeQuery:
    """Records what was asked of it and answers with one row.

    Every method returns `self`, the way the PostgREST builder chains, so the
    store's calls land in `calls` in the order it made them.
    """

    calls: list[tuple] = field(default_factory=list)
    rows: list[dict] = field(default_factory=lambda: [dict(ROW)])

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def insert(self, row: dict):
        self.calls.append(("insert", row))
        return self

    def update(self, changes: dict):
        self.calls.append(("update", changes))
        return self

    def delete(self):
        self.calls.append(("delete",))
        return self

    def eq(self, column: str, value):
        self.calls.append(("eq", column, value))
        return self

    def gte(self, column: str, value):
        self.calls.append(("gte", column, value))
        return self

    def ilike(self, column: str, pattern: str):
        self.calls.append(("ilike", column, pattern))
        return self

    @property
    def not_(self):
        self.calls.append(("not",))
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

    # -- helpers the assertions read ------------------------------------------

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]

    @property
    def verbs(self) -> list[str]:
        return [call[0] for call in self.calls]


@dataclass
class FakeClient:
    query: FakeQuery

    def table(self, name: str):
        self.query.calls.append(("table", name))
        return self.query


@pytest.fixture
def query(monkeypatch):
    """Point the store's admin client at a fake, and hand back its recorder."""
    recorder = FakeQuery()
    monkeypatch.setattr(supabase_client, "admin", lambda: FakeClient(recorder))
    return recorder


class TestReadingTheCatalogue:
    def test_it_selects_every_column_the_pages_render(self, query):
        SupabaseVenues().list_venues()

        selected = query.named("select")[0][1]
        for column in (
            "name",
            "location",
            "capacity",
            "facilities",
            "accessibility_features",
            "operating_hours",
            "supported_layouts",
        ):
            assert column in selected

    def test_an_unfiltered_list_narrows_nothing(self, query):
        SupabaseVenues().list_venues(NO_FILTERS)

        assert query.named("gte") == []
        assert query.named("ilike") == []

    def test_it_orders_by_name(self, query):
        SupabaseVenues().list_venues()

        assert ("order", "name", False) in query.calls


class TestFilteringHappensInThePostgresQuery:
    """US9.3, asserted where the in-memory store cannot speak for it."""

    def test_minimum_capacity_becomes_a_gte(self, query):
        SupabaseVenues().list_venues(VenueFilters(min_capacity=200))

        assert query.named("gte") == [("gte", "capacity", 200)]

    def test_location_becomes_an_ilike_on_location(self, query):
        SupabaseVenues().list_venues(VenueFilters(location="Library"))

        assert query.named("ilike") == [("ilike", "location", "%Library%")]

    def test_accessibility_becomes_an_ilike_on_its_own_column(self, query):
        SupabaseVenues().list_venues(VenueFilters(accessibility="hearing"))

        assert query.named("ilike") == [("ilike", "accessibility_features", "%hearing%")]

    def test_all_three_are_sent_together(self, query):
        """Chained filters are ANDed by PostgREST, which is US9.3's rule."""
        SupabaseVenues().list_venues(
            VenueFilters(min_capacity=50, location="Library", accessibility="Step-free")
        )

        assert len(query.named("gte")) == 1
        assert len(query.named("ilike")) == 2

    def test_an_empty_filter_is_not_sent_at_all(self, query):
        """A form submitting untouched boxes must not add a clause."""
        SupabaseVenues().list_venues(
            VenueFilters(min_capacity=None, location="   ", accessibility="")
        )

        assert query.named("gte") == []
        assert query.named("ilike") == []

    def test_excluded_venues_become_a_not_in_on_id(self, query):
        """US12.1: venues closed on the planning dates are left out by Postgres."""
        SupabaseVenues().list_venues(VenueFilters(excluded_ids=frozenset({3, 1})))

        assert query.named("not") == [("not",)]
        assert query.named("in") == [("in", "id", [1, 3])]

    def test_no_exclusions_sends_no_not_in(self, query):
        """Nothing to leave out sends no clause, rather than an empty `not.in.()`."""
        SupabaseVenues().list_venues(VenueFilters(excluded_ids=frozenset()))

        assert query.named("not") == []
        assert query.named("in") == []

    def test_exclusions_count_as_a_filter(self):
        assert VenueFilters(excluded_ids=frozenset({1})).applied
        assert not VenueFilters().applied

    def test_a_filter_is_trimmed_before_it_is_sent(self, query):
        SupabaseVenues().list_venues(VenueFilters(location="  Library  "))

        assert query.named("ilike") == [("ilike", "location", "%Library%")]

    def test_wildcards_are_escaped_rather_than_passed_through(self, query):
        """Typing % must not become "match everything" in SQL."""
        SupabaseVenues().list_venues(VenueFilters(location="100%"))

        assert query.named("ilike") == [("ilike", "location", "%100\\%%")]

    def test_underscores_are_escaped_too(self, query):
        SupabaseVenues().list_venues(VenueFilters(location="a_b"))

        assert query.named("ilike") == [("ilike", "location", "%a\\_b%")]


class TestWritingARecord:
    def test_creating_sends_the_writable_columns(self, query):
        SupabaseVenues().create_venue(
            name="Atrium",
            location="Science Quarter",
            capacity=90,
            facilities="Cafe",
            accessibility_features="Ramp",
            operating_hours="09:00-17:00",
            supported_layouts="Standing",
        )

        row = query.named("insert")[0][1]
        assert row["name"] == "Atrium"
        assert row["location"] == "Science Quarter"
        assert row["capacity"] == 90
        assert row["supported_layouts"] == "Standing"

    def test_an_empty_optional_field_is_stored_as_null(self, query):
        """One state for "nothing recorded" in the database, not two."""
        SupabaseVenues().create_venue(
            name="Atrium",
            location="Science Quarter",
            capacity=90,
            facilities="",
            accessibility_features="",
            operating_hours="",
            supported_layouts="",
        )

        row = query.named("insert")[0][1]
        assert row["facilities"] is None
        assert row["accessibility_features"] is None
        assert row["operating_hours"] is None
        assert row["supported_layouts"] is None

    def test_updating_never_sends_the_system_generated_fields(self, query):
        """US9.1b: `id` and `created_at` are not editable, so they are not sent."""
        SupabaseVenues().save_venue(
            1,
            name="Great Hall",
            location="Main Campus",
            capacity=450,
            facilities="Stage",
            accessibility_features="Step-free access",
            operating_hours="08:00-22:00",
            supported_layouts="Theatre",
        )

        changes = query.named("update")[0][1]
        assert "id" not in changes
        assert "created_at" not in changes
        assert changes["capacity"] == 450

    def test_updating_stamps_updated_at_itself(self, query):
        SupabaseVenues().save_venue(
            1,
            name="Great Hall",
            location="Main Campus",
            capacity=450,
            facilities="",
            accessibility_features="",
            operating_hours="",
            supported_layouts="",
        )

        assert query.named("update")[0][1]["updated_at"]

    def test_updating_targets_the_one_row(self, query):
        SupabaseVenues().save_venue(
            7,
            name="Great Hall",
            location="Main Campus",
            capacity=450,
            facilities="",
            accessibility_features="",
            operating_hours="",
            supported_layouts="",
        )

        assert ("eq", "id", 7) in query.calls

    def test_deleting_is_a_delete_of_that_row(self, query):
        """US9.1c: a hard delete, not a flag written by an update."""
        SupabaseVenues().delete_venue(3)

        assert "delete" in query.verbs
        assert "update" not in query.verbs
        assert ("eq", "id", 3) in query.calls


class TestDuplicateNames:
    """A unique violation is a rule; anything else is still a failure."""

    def test_a_unique_violation_becomes_a_named_error(self):
        error = venue_store._as_duplicate(_ApiError("23505"), "Great Hall")

        assert isinstance(error, venue_store.DuplicateVenueName)
        assert "Great Hall" in str(error)

    def test_a_unique_violation_reported_in_the_args_is_recognised(self):
        error = venue_store._as_duplicate(Exception({"code": "23505"}), "Great Hall")

        assert isinstance(error, venue_store.DuplicateVenueName)

    def test_any_other_failure_is_left_alone_to_be_re_raised(self):
        """An unreachable database is not a name clash, and must not read as one."""
        original = _ApiError("08006")

        assert venue_store._as_duplicate(original, "Great Hall") is original

    def test_an_error_with_no_code_at_all_is_left_alone(self):
        original = RuntimeError("something else entirely")

        assert venue_store._as_duplicate(original, "Great Hall") is original


class _ApiError(Exception):
    """Stands in for the client's error object, which carries a SQLSTATE."""

    def __init__(self, code: str) -> None:
        super().__init__(f"error {code}")
        self.code = code
