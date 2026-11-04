"""US2.1 reopened in Sprint 3 — the customer's mandatory fields for an event request.

On Submit these are required: name, description, purpose, date, start/end time,
expected attendance, venue requirements, preferred layout, accessibility needs,
equipment needs and registration needs. Layout, facilities and accessibility
come from fixed lists matching the venue catalogue; a field that may not apply
can be answered "None / Not required". Missing fields block submit with a clear
error, and drafts (US2.2) still save without these checks.
"""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from app import supabase_client
from app.event_needs import (
    ACCESSIBILITY_OPTIONS,
    FACILITY_OPTIONS,
    LAYOUT_OPTIONS,
    MISSING_MESSAGES,
    NOT_REQUIRED,
    EventNeeds,
    layout_choices,
)
from app.event_store import SupabaseEvents, to_event
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEED_ATTRS,
    SUBMITTABLE_NEEDS,
)

ORGANISER = "Event Organiser"

#: Every original field a submission needs, filled in and valid.
DETAILS = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks and a campus tour.",
    "startsAt": "2099-11-02T18:00",
    "endsAt": "2099-11-02T21:00",
    "expectedAttendance": 120,
}
REQUEST = {**DETAILS, **SUBMITTABLE_NEEDS}

ALL_NOT_REQUIRED = {
    "venueRequirements": NOT_REQUIRED,
    "preferredLayout": NOT_REQUIRED,
    "accessibilityNeeds": NOT_REQUIRED,
    "equipmentNeeds": NOT_REQUIRED,
    "registrationNeeds": NOT_REQUIRED,
}

NEED_KEYS = {
    "venue_requirements": "venueRequirements",
    "preferred_layout": "preferredLayout",
    "accessibility_needs": "accessibilityNeeds",
    "equipment_needs": "equipmentNeeds",
    "registration_needs": "registrationNeeds",
}


def create(client, headers, **fields):
    response = client.post("/events", json=fields, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, headers, event_id):
    return client.post(f"/events/{event_id}/submit", headers=headers)


# --- the fixed lists and rules, as plain functions -------------------------------


class TestFixedLists:

    def test_the_lists_use_the_venue_catalogue_s_words(self):
        """US9.1a's seeded venues list these; suitability matches them case-insensitively."""
        assert {"Theatre", "Classroom", "Boardroom", "Banquet", "Cabaret"} <= set(LAYOUT_OPTIONS)
        assert {"Stage", "Projector", "AV system", "Whiteboard"} <= set(FACILITY_OPTIONS)
        assert {"Wheelchair access", "Hearing loop", "Accessible toilets"} <= set(
            ACCESSIBILITY_OPTIONS
        )



#: The browser's copy of the lists. The server refuses any value off its own
#: lists, so a drift between the two would show as a form that cannot submit.
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "eventNeeds.ts"


class TestLayoutsFromTheCatalogue:
    """Week 9 (G7/A7): Venue Staff add, edit and delete layouts through the
    catalogue, and the Organiser's choices follow it."""

    def test_a_layout_a_venue_lists_is_added_after_the_standard_ones(self):
        choices = layout_choices(["Theatre", "Ballroom", "ballroom", "  ", "Amphitheatre"])
        assert choices == (*LAYOUT_OPTIONS, "Amphitheatre", "Ballroom")

    def test_a_standard_name_in_another_case_is_not_repeated(self):
        assert layout_choices(["THEATRE", "theatre"]) == LAYOUT_OPTIONS

    def test_the_route_lists_what_the_catalogue_holds_now(
        self, client, auth_headers, venue_repository
    ):
        venue_repository.venues[0] = replace(
            venue_repository.venues[0], supported_layouts="Theatre, Ballroom"
        )
        response = client.get("/venues/layouts", headers=auth_headers(ORGANISER))

        assert response.status_code == 200, response.text
        assert response.json()[-1] == "Ballroom"

    def test_an_organiser_can_choose_a_layout_venue_staff_added(
        self, client, auth_headers, venue_repository
    ):
        venue_repository.venues[0] = replace(
            venue_repository.venues[0], supported_layouts="Ballroom"
        )
        body = {**REQUEST, "preferredLayout": "Ballroom"}
        created = create(client, auth_headers(ORGANISER), **body)
        assert created["preferredLayout"] == "Ballroom"

    def test_a_layout_no_venue_lists_is_still_refused(self, client, auth_headers):
        response = client.post(
            "/events", json={**REQUEST, "preferredLayout": "Ballroom"},
            headers=auth_headers(ORGANISER),
        )
        assert response.status_code == 400
        assert "Ballroom is not one of the options" in response.json()["detail"]["message"]


def _frontend_list(source: str, name: str) -> tuple[str, ...]:
    match = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.S)
    assert match, f"{name} not found in {FRONTEND.name}"
    return tuple(re.findall(r"'([^']*)'", match.group(1)))












# --- AC: drafts still save without these checks (US2.2) --------------------------


class TestDrafts:
    def test_a_draft_saves_with_no_needs(self, client, auth_headers):
        event = create(client, auth_headers(ORGANISER), title="Ideas for later")

        assert event["status"] == "Draft"
        assert {event[key] for key in NEED_KEYS.values()} == {""}








# --- AC: on Submit, every field is required; missing ones block it ----------------


class TestSubmitting:

    def test_none_not_required_answers_every_need(self, client, auth_headers):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, **DETAILS, **ALL_NOT_REQUIRED)

        response = submit(client, organiser, event["id"])

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Submitted"

    @pytest.mark.parametrize(
        ("missing", "message"),
        [
            ({"title": "  "}, "Give the event a title."),
            ({"description": ""}, "Give the event a description."),
            ({"description": " \n "}, "Give the event a description."),
            ({"purpose": ""}, "Give the event a purpose."),
            ({"startsAt": ""}, "Give the event a date."),
            ({"endsAt": None}, "Give the event an end date."),
            ({"endsAt": "  "}, "Give the event an end date."),
            ({"expectedAttendance": None}, "Give the expected attendance."),
            ({"expectedAttendance": 0}, "Expected attendance must be at least 1."),
            (
                {"startsAt": "2000-01-01T10:00", "endsAt": "2000-01-01T12:00"},
                "The start date cannot be in the past.",
            ),
            *[({key: ""}, MISSING_MESSAGES[name]) for name, key in NEED_KEYS.items()],
        ],
    )
    def test_a_missing_field_blocks_submit_with_a_clear_error(
        self, client, auth_headers, missing, message
    ):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, **{**REQUEST, **missing})

        response = submit(client, organiser, event["id"])

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == message
        fetched = client.get(f"/events/{event['id']}", headers=organiser).json()
        assert fetched["status"] == "Draft"





# --- Coordinator edits and reads -------------------------------------------------


def _submitted_and_assigned(client, auth_headers) -> dict:
    organiser = auth_headers(ORGANISER)
    event = create(client, organiser, **REQUEST)
    assert submit(client, organiser, event["id"]).status_code == 200
    assigned = client.post(
        f"/events/{event['id']}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert assigned.status_code == 200, assigned.text
    return assigned.json()




# --- the Supabase store writes and reads the new columns -------------------------


class FakeQuery:
    def __init__(self, recorder: "FakeClient", table: str) -> None:
        self.recorder = recorder
        self.table_name = table
        self.rows: list[dict] = []

    def insert(self, payload):
        self.recorder.inserts.append((self.table_name, payload))
        self.rows = [{"id": 42}]
        return self

    def update(self, payload):
        self.recorder.updates.append((self.table_name, payload))
        return self

    def select(self, _columns):
        if self.table_name == "events":
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
        self.inserts: list[tuple[str, object]] = []
        self.updates: list[tuple[str, dict]] = []
        self.stored_row = {
            "id": 42,
            "name": "Gala",
            "purpose": "Celebrate",
            "description": "Dinner",
            "proposed_date": "2099-11-02T18:00:00",
            "end_date": "2099-11-02T21:00:00",
            "expected_attendance": 80,
            "status": "Submitted",
            "organiser_id": ORGANISER_ID,
            "coordinator_id": COORDINATOR_ID,
            "created_at": "2026-09-15T09:00:00",
            "updated_at": "2026-09-15T09:00:00",
            "submitted_at": None,
            "users": {"name": "Dylan"},
            **SUBMITTABLE_NEED_ATTRS,
        }

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


@pytest.fixture
def recorder(monkeypatch) -> FakeClient:
    fake = FakeClient()
    monkeypatch.setattr(supabase_client, "admin", lambda: fake)
    return fake


DETAIL_KWARGS = {
    "title": "Gala",
    "purpose": "Celebrate",
    "description": "Dinner",
    "starts_at": "2099-11-02T18:00",
    "ends_at": "2099-11-02T21:00",
    "expected_attendance": 80,
}


class TestSupabaseStore:





    def test_save_writes_the_needs(self, recorder):
        SupabaseEvents().save_event(42, **DETAIL_KWARGS, needs=EventNeeds(**SUBMITTABLE_NEED_ATTRS))

        _, written = recorder.updates[0]
        for name, value in SUBMITTABLE_NEED_ATTRS.items():
            assert written[name] == value

    def test_a_tracked_save_logs_each_changed_need(self, recorder, monkeypatch):
        previous = to_event(recorder.stored_row)
        needs = EventNeeds(
            **{
                **SUBMITTABLE_NEED_ATTRS,
                "preferred_layout": "Banquet",
                "equipment_needs": NOT_REQUIRED,
            }
        )

        calls = []

        def rpc(name, payload):
            calls.append((name, payload))
            return type("Rpc", (), {"execute": lambda self: type("Result", (), {"data": True})()})()

        monkeypatch.setattr(recorder, "rpc", rpc, raising=False)

        SupabaseEvents().save_event_with_tracking(
            42,
            **{**DETAIL_KWARGS, "starts_at": previous.starts_at, "ends_at": previous.ends_at},
            editor_id=COORDINATOR_ID,
            previous_event=previous,
            needs=needs,
        )

        name, payload = calls[0]
        assert name == "us11_edit"
        assert [
            (row["changed_field"], row["old_value"], row["new_value"], row["change_type"])
            for row in payload["p_changes"]
        ] == [
            ("preferred_layout", "Theatre", "Banquet", "important"),
            ("equipment_needs", "Two wireless microphones", NOT_REQUIRED, "important"),
        ]

