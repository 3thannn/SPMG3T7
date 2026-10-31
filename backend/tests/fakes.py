"""A stand-in for the Supabase admin client, for testing the stores' queries.

Most tests run against the in-memory stores, which is the right call for the
rules. But the Supabase stores are separate implementations of the same
promise, and a store that asked Postgres for the wrong thing would pass every
one of those tests. These fakes let a test drive the real store and assert on
what it asked for: which table, which filters, which order, which function.

`FakeClient` answers each table with its own rows, so a store method that reads
one table and then another can be given an answer for each. When a test needs
the same table to answer differently on a later call (insert, then read back),
it queues the answers in `queued`. The `fake` fixture in conftest installs one.
"""

from dataclasses import dataclass, field


@dataclass
class FakeResponse:
    data: object


@dataclass
class FakeQuery:
    """One table's query: records each call and answers with that table's rows."""

    table: str
    rows: object
    calls: list[tuple] = field(default_factory=list)

    def _record(self, *call):
        self.calls.append(call)
        return self

    def select(self, columns: str):
        return self._record("select", columns)

    def insert(self, row):
        return self._record("insert", row)

    def update(self, changes: dict):
        return self._record("update", changes)

    def delete(self):
        return self._record("delete")

    def eq(self, column: str, value):
        return self._record("eq", column, value)

    def neq(self, column: str, value):
        return self._record("neq", column, value)

    def is_(self, column: str, value):
        return self._record("is", column, value)

    def in_(self, column: str, values: list):
        return self._record("in", column, values)

    def ilike(self, column: str, pattern: str):
        return self._record("ilike", column, pattern)

    def order(self, column: str, desc: bool = False):
        return self._record("order", column, desc)

    def limit(self, count: int):
        return self._record("limit", count)

    def execute(self):
        return FakeResponse(self.rows)

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]


@dataclass
class FakeRpc:
    name: str
    arguments: dict
    answer: object

    def execute(self):
        return FakeResponse(self.answer)


@dataclass
class FakeClient:
    """Answers each table with its rows and each database function with its answer."""

    rows: dict[str, object] = field(default_factory=dict)
    queued: dict[str, list[object]] = field(default_factory=dict)
    rpc_answers: dict[str, object] = field(default_factory=dict)
    queries: list[FakeQuery] = field(default_factory=list)
    rpcs: list[tuple[str, dict]] = field(default_factory=list)

    def table(self, name: str) -> FakeQuery:
        waiting = self.queued.get(name)
        rows = waiting.pop(0) if waiting else self.rows.get(name, [])
        query = FakeQuery(name, rows)
        self.queries.append(query)
        return query

    def rpc(self, name: str, arguments: dict) -> FakeRpc:
        self.rpcs.append((name, arguments))
        return FakeRpc(name, arguments, self.rpc_answers.get(name))

    def on(self, table: str) -> list[FakeQuery]:
        return [query for query in self.queries if query.table == table]
