"""What `create_event_request` actually writes — Event Request Creation.

The rest of the suite runs against `InMemoryEvents`, because the rules are what
it is testing and a network round trip makes none of them truer. This file is
the exception, and only for the new write: "row written to events table on
success" is an acceptance criterion about columns, and a stand-in store cannot
tell you that `end_date` was spelled right or that `submitted_at` was set.

So `supabase_client.admin` is replaced with a recorder that answers like
PostgREST and keeps what it was asked to write. Nothing here reaches the
network; what is asserted is the payload, which is the part that can be wrong.
"""

import pytest

from app import event_store, supabase_client
from app.event_status import EventStatus
from app.event_store import SupabaseEvents

EVENT_ID = 42
ORGANISER_ID = 7

#: What the recorder hands back when the row is read again after insert.
STORED_ROW = {
    "id": EVENT_ID,
    "name": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "proposed_date": "2026-11-02T18:00",
    "end_date": "2026-11-02T21:30",
    "expected_attendance": 120,
    "status": "Submitted",
    "organiser_id": ORGANISER_ID,
    "created_at": "2026-09-15T09:00:00",
    "updated_at": "2026-09-15T09:00:00",
    "submitted_at": "2026-09-15T09:00:00",
    "users": {"name": "Dylan"},
}


class FakeQuery:
    """One PostgREST query chain. Every filter returns self, as the real one does."""

    def __init__(self, recorder: "FakeClient", table: str) -> None:
        self.recorder = recorder
        self.table_name = table
        self.rows: list[dict] = []

    def insert(self, payload):
        self.recorder.inserts.append((self.table_name, payload))
        # PostgREST answers an insert with the row it made, id included.
        self.rows = [{"id": EVENT_ID}]
        return self

    def select(self, columns):
        self.recorder.selected[self.table_name] = columns
        if self.table_name == event_store.EVENTS_TABLE:
            self.rows = [STORED_ROW]
        else:
            self.rows = self.recorder.change_rows
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def in_(self, *_args):
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class FakeClient:
    """Stands in for the service-role Supabase client, and keeps the receipts."""

    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict]] = []
        self.selected: dict[str, str] = {}
        self.change_rows: list[dict] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


@pytest.fixture
def recorder(monkeypatch) -> FakeClient:
    """Point the store's admin client at the recorder for the length of a test."""
    client = FakeClient()
    monkeypatch.setattr(supabase_client, "admin", lambda: client)
    return client


@pytest.fixture
def written(recorder) -> dict:
    """The `events` payload from one create_event_request call."""
    SupabaseEvents().create_event_request(
        name="Faculty Welcome Night",
        purpose="Welcome the new intake.",
        description="Talks.",
        starts_at="2026-11-02T18:00",
        ends_at="2026-11-02T21:30",
        expected_attendance=120,
        organiser_id=ORGANISER_ID,
    )
    table, payload = recorder.inserts[0]
    assert table == event_store.EVENTS_TABLE
    return payload


class TestTheEventsRow:
    def test_it_is_inserted_into_the_events_table(self, recorder, written):
        assert recorder.inserts[0][0] == "events"

    def test_it_carries_the_text_the_organiser_typed(self, written):
        assert written["name"] == "Faculty Welcome Night"
        assert written["purpose"] == "Welcome the new intake."
        assert written["description"] == "Talks."

    def test_the_start_goes_to_proposed_date(self, written):
        assert written["proposed_date"] == "2026-11-02T18:00"

    def test_the_end_goes_to_the_new_end_date_column(self, written):
        """The column this story added. A typo here is invisible until runtime."""
        assert written["end_date"] == "2026-11-02T21:30"

    def test_the_attendance_is_written_as_a_number(self, written):
        assert written["expected_attendance"] == 120

    def test_it_is_written_already_submitted(self, written):
        assert written["status"] == str(EventStatus.SUBMITTED)

    def test_submitted_at_is_set_rather_than_left_null(self, written):
        """A request is submitted at the moment it is made, so the column says so."""
        assert written["submitted_at"] == written["created_at"]

    def test_the_organiser_is_the_one_passed_in(self, written):
        assert written["organiser_id"] == ORGANISER_ID

    def test_created_and_updated_start_out_equal(self, written):
        assert written["created_at"] == written["updated_at"]


class TestTheAuditRow:
    def test_a_status_change_is_written_too(self, recorder, written):
        assert [table for table, _ in recorder.inserts] == [
            "events",
            "status_changes",
        ]

    def test_it_reads_draft_to_submitted(self, recorder, written):
        """`status_changes.old_status` is NOT NULL, so Draft is the honest `from`."""
        _, change = recorder.inserts[1]

        assert change["old_status"] == str(EventStatus.DRAFT)
        assert change["new_status"] == str(EventStatus.SUBMITTED)

    def test_it_points_at_the_event_that_was_just_made(self, recorder, written):
        assert recorder.inserts[1][1]["event_id"] == EVENT_ID

    def test_it_is_attributed_to_the_organiser(self, recorder, written):
        assert recorder.inserts[1][1]["changed_by_id"] == ORGANISER_ID

    def test_it_is_stamped_with_the_creation_time(self, recorder, written):
        assert recorder.inserts[1][1]["changed_at"] == written["created_at"]


class TestWhatComesBack:
    def test_the_row_is_read_back_rather_than_assembled(self, recorder):
        """The insert response carries no joined organiser name; the read does."""
        event = SupabaseEvents().create_event_request(
            name="Faculty Welcome Night",
            purpose="Welcome the new intake.",
            description="Talks.",
            starts_at="2026-11-02T18:00",
            ends_at="2026-11-02T21:30",
            expected_attendance=120,
            organiser_id=ORGANISER_ID,
        )

        assert event.id == EVENT_ID
        assert event.organiser_name == "Dylan"
        assert event.status is EventStatus.SUBMITTED

    def test_the_end_date_column_is_read_back_into_ends_at(self, recorder):
        event = SupabaseEvents().create_event_request(
            name="Faculty Welcome Night",
            purpose="Welcome the new intake.",
            description="Talks.",
            starts_at="2026-11-02T18:00",
            ends_at="2026-11-02T21:30",
            expected_attendance=120,
            organiser_id=ORGANISER_ID,
        )

        assert event.ends_at == "2026-11-02T21:30"

    def test_end_date_is_among_the_columns_selected(self, recorder, written):
        """A column the select never asks for comes back as None, silently."""
        assert "end_date" in recorder.selected[event_store.EVENTS_TABLE]


class TestReadingAnEventWithoutAnEndDate:
    """Every event made before this story has `end_date` NULL, and must still load."""

    def test_a_null_end_date_becomes_an_empty_string(self):
        event = event_store.to_event({**STORED_ROW, "end_date": None})

        assert event.ends_at == ""

    def test_a_row_with_no_end_date_key_at_all_still_loads(self):
        row = {key: value for key, value in STORED_ROW.items() if key != "end_date"}

        assert event_store.to_event(row).ends_at == ""

    def test_an_end_date_that_is_present_is_kept(self):
        assert event_store.to_event(STORED_ROW).ends_at == "2026-11-02T21:30"
