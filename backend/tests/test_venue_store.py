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

from app import supabase_client

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












class _ApiError(Exception):
    """Stands in for the client's error object, which carries a SQLSTATE."""

    def __init__(self, code: str) -> None:
        super().__init__(f"error {code}")
        self.code = code
