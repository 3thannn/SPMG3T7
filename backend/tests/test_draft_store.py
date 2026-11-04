"""Database payload details required for partial drafts."""

from app import event_store, supabase_client
from app.event_store import SupabaseEvents


class FakeQuery:
    def __init__(self, recorder: "FakeClient", table: str) -> None:
        self.recorder = recorder
        self.table_name = table
        self.rows: list[dict] = []

    def insert(self, payload):
        self.recorder.inserts.append((self.table_name, payload))
        self.rows = [{"id": 42}]
        return self

    def select(self, _columns):
        if self.table_name == event_store.EVENTS_TABLE:
            self.rows = [self.recorder.stored_row]
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def in_(self, *_args):
        self.rows = []
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class FakeClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict]] = []
        self.stored_row = {
            "id": 42,
            "name": "",
            "purpose": None,
            "description": "  Planning notes  ",
            "proposed_date": None,
            "end_date": None,
            "expected_attendance": None,
            "status": "Draft",
            "organiser_id": 7,
            "created_at": "2026-09-15T09:00:00",
            "updated_at": "2026-09-15T09:00:00",
            "submitted_at": None,
            "users": {"name": "Dylan"},
        }

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def test_a_partial_draft_writes_a_null_date_without_trimming_text(monkeypatch):
    recorder = FakeClient()
    monkeypatch.setattr(supabase_client, "admin", lambda: recorder)

    draft = SupabaseEvents().create_event(
        title="",
        purpose="",
        description="  Planning notes  ",
        starts_at="",
        ends_at=None,
        expected_attendance=None,
        organiser_id=7,
    )

    _, written = recorder.inserts[0]
    assert written["proposed_date"] is None
    assert written["description"] == "  Planning notes  "
    assert draft.starts_at == ""
    assert draft.description == "  Planning notes  "
