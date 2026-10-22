"""US2.1 reopened in Sprint 3 — the customer's mandatory fields for an event request.

On Submit these are required: name, description, purpose, date, start/end time,
expected attendance, venue requirements, preferred layout, accessibility needs,
equipment needs and registration needs. Layout, facilities and accessibility
come from fixed lists matching the venue catalogue; a field that may not apply
can be answered "None / Not required". Missing fields block submit with a clear
error, and drafts (US2.2) still save without these checks.
"""

import re
from pathlib import Path

import pytest

from app import supabase_client
from app.event_needs import (
    ACCESSIBILITY_OPTIONS,
    FACILITY_OPTIONS,
    FREE_TEXT_MAX,
    LAYOUT_OPTIONS,
    MISSING_MESSAGES,
    NEED_FIELDS,
    NO_NEEDS,
    NOT_REQUIRED,
    EventNeeds,
    format_error,
    listed,
    missing_error,
)
from app.event_status import EventStatus
from app.event_store import EVENT_COLUMNS, Event, SupabaseEvents, to_event
from app.events import ATTENDANCE_TOO_LARGE
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
    @pytest.mark.parametrize("options", [LAYOUT_OPTIONS, FACILITY_OPTIONS, ACCESSIBILITY_OPTIONS])
    def test_no_option_contains_the_separator_or_repeats(self, options):
        """A joined answer must read back as the options that were chosen."""
        assert all("," not in option for option in options)
        assert len(set(options)) == len(options)
        assert NOT_REQUIRED not in options

    def test_the_lists_use_the_venue_catalogue_s_words(self):
        """US9.1a's seeded venues list these; suitability matches them case-insensitively."""
        assert {"Theatre", "Classroom", "Boardroom", "Banquet", "Cabaret"} <= set(LAYOUT_OPTIONS)
        assert {"Stage", "Projector", "AV system", "Whiteboard"} <= set(FACILITY_OPTIONS)
        assert {"Wheelchair access", "Hearing loop", "Accessible toilets"} <= set(
            ACCESSIBILITY_OPTIONS
        )

    def test_the_fields_are_named_as_the_columns(self):
        assert NEED_FIELDS == (
            "venue_requirements",
            "preferred_layout",
            "accessibility_needs",
            "equipment_needs",
            "registration_needs",
        )
        assert tuple(MISSING_MESSAGES) == NEED_FIELDS


#: The browser's copy of the lists. The server refuses any value off its own
#: lists, so a drift between the two would show as a form that cannot submit.
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "eventNeeds.ts"


def _frontend_list(source: str, name: str) -> tuple[str, ...]:
    match = re.search(rf"export const {name} = \[(.*?)\] as const", source, re.S)
    assert match, f"{name} not found in {FRONTEND.name}"
    return tuple(re.findall(r"'([^']*)'", match.group(1)))


@pytest.mark.skipif(not FRONTEND.exists(), reason="the frontend is not checked out")
class TestFrontendParity:
    @pytest.mark.parametrize(
        ("name", "options"),
        [
            ("LAYOUT_OPTIONS", LAYOUT_OPTIONS),
            ("FACILITY_OPTIONS", FACILITY_OPTIONS),
            ("ACCESSIBILITY_OPTIONS", ACCESSIBILITY_OPTIONS),
        ],
    )
    def test_the_browser_offers_the_same_list_in_the_same_order(self, name, options):
        assert _frontend_list(FRONTEND.read_text(encoding="utf-8"), name) == options

    def test_the_browser_uses_the_same_answers_and_messages(self):
        source = FRONTEND.read_text(encoding="utf-8")
        assert f"export const NOT_REQUIRED = '{NOT_REQUIRED}'" in source
        assert f"export const FREE_TEXT_MAX = {FREE_TEXT_MAX}" in source
        for message in MISSING_MESSAGES.values():
            template = message.replace(NOT_REQUIRED, "${NOT_REQUIRED}")
            assert f"`{template}`" in source


class TestEventNeeds:
    def test_nothing_is_answered_by_default(self):
        assert NO_NEEDS == EventNeeds()
        assert set(NO_NEEDS.as_attrs().values()) == {""}

    def test_attrs_keep_the_values_exactly(self):
        needs = EventNeeds(**SUBMITTABLE_NEED_ATTRS)
        assert needs.as_attrs() == SUBMITTABLE_NEED_ATTRS

    def test_an_unanswered_column_is_written_null(self):
        needs = EventNeeds(preferred_layout="Theatre")
        assert needs.as_columns() == {
            "venue_requirements": None,
            "preferred_layout": "Theatre",
            "accessibility_needs": None,
            "equipment_needs": None,
            "registration_needs": None,
        }

    def test_an_event_exposes_its_needs(self):
        event = Event(
            id=1, title="", purpose="", description="", starts_at="", ends_at="",
            expected_attendance=None, status=EventStatus.DRAFT, organiser_id=1,
            organiser_name="", created_at="", updated_at="", **SUBMITTABLE_NEED_ATTRS,
        )
        assert event.needs == EventNeeds(**SUBMITTABLE_NEED_ATTRS)


class TestListed:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", ()),
            ("   ", ()),
            ("Stage", ("Stage",)),
            ("Stage, Projector", ("Stage", "Projector")),
            (" Stage ,, Projector ,", ("Stage", "Projector")),
        ],
    )
    def test_reads_the_joined_options(self, value, expected):
        assert listed(value) == expected


class TestFormatError:
    """Applies to drafts too: blanks are fine, values off the lists are not."""

    @pytest.mark.parametrize(
        "needs",
        [
            NO_NEEDS,
            EventNeeds(**SUBMITTABLE_NEED_ATTRS),
            EventNeeds(**{name: NOT_REQUIRED for name in NEED_FIELDS}),
            EventNeeds(venue_requirements=", ".join(FACILITY_OPTIONS)),
            EventNeeds(accessibility_needs=", ".join(ACCESSIBILITY_OPTIONS)),
            EventNeeds(preferred_layout="  "),
            EventNeeds(equipment_needs="e" * FREE_TEXT_MAX),
            EventNeeds(registration_needs="r" * FREE_TEXT_MAX),
        ],
        ids=[
            "blank",
            "answered",
            "all-not-required",
            "every-facility",
            "every-accessibility-need",
            "blank-layout",
            "equipment-at-limit",
            "registration-at-limit",
        ],
    )
    def test_acceptable_answers(self, needs):
        assert format_error(needs) is None

    @pytest.mark.parametrize(
        ("needs", "message"),
        [
            (
                EventNeeds(venue_requirements="Stage, Helipad"),
                "Choose the venue requirements from the list. "
                "Helipad is not one of the options.",
            ),
            (
                EventNeeds(venue_requirements=f"Stage, {NOT_REQUIRED}"),
                f"Choose the venue requirements, or {NOT_REQUIRED} — not both.",
            ),
            (
                EventNeeds(accessibility_needs="ramp"),
                "Choose the accessibility needs from the list. ramp is not one of the options.",
            ),
            (
                EventNeeds(accessibility_needs=f"{NOT_REQUIRED}, Lift"),
                f"Choose the accessibility needs, or {NOT_REQUIRED} — not both.",
            ),
            (
                EventNeeds(preferred_layout="theatre"),
                "Choose a preferred layout from the list. theatre is not one of the options.",
            ),
            (
                EventNeeds(preferred_layout="Theatre, Banquet"),
                "Choose a preferred layout from the list. "
                "Theatre, Banquet is not one of the options.",
            ),
            (
                EventNeeds(equipment_needs="e" * (FREE_TEXT_MAX + 1)),
                f"Keep the equipment needs to {FREE_TEXT_MAX} characters or fewer.",
            ),
            (
                EventNeeds(registration_needs="r" * (FREE_TEXT_MAX + 1)),
                f"Keep the registration needs to {FREE_TEXT_MAX} characters or fewer.",
            ),
        ],
    )
    def test_refused_answers(self, needs, message):
        assert format_error(needs) == message


class TestMissingError:
    def test_every_answer_given(self):
        assert missing_error(EventNeeds(**SUBMITTABLE_NEED_ATTRS)) is None

    def test_not_required_counts_as_an_answer(self):
        assert missing_error(EventNeeds(**{name: NOT_REQUIRED for name in NEED_FIELDS})) is None

    @pytest.mark.parametrize("name", NEED_FIELDS)
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_each_unanswered_field_is_named(self, name, blank):
        needs = EventNeeds(**{**SUBMITTABLE_NEED_ATTRS, name: blank})
        assert missing_error(needs) == MISSING_MESSAGES[name]

    def test_the_first_unanswered_field_in_form_order_is_reported(self):
        assert missing_error(NO_NEEDS) == (
            f"Choose the venue requirements, or {NOT_REQUIRED}."
        )

    @pytest.mark.parametrize(
        ("name", "message"),
        [
            ("venue_requirements", "Choose the venue requirements, or None / Not required."),
            ("preferred_layout", "Choose a preferred layout, or None / Not required."),
            ("accessibility_needs", "Choose the accessibility needs, or None / Not required."),
            ("equipment_needs", "Describe the equipment needs, or choose None / Not required."),
            (
                "registration_needs",
                "Describe the registration needs, or choose None / Not required.",
            ),
        ],
    )
    def test_the_messages_say_how_to_answer(self, name, message):
        assert MISSING_MESSAGES[name] == message


# --- AC: drafts still save without these checks (US2.2) --------------------------


class TestDrafts:
    def test_a_draft_saves_with_no_needs(self, client, auth_headers):
        event = create(client, auth_headers(ORGANISER), title="Ideas for later")

        assert event["status"] == "Draft"
        assert {event[key] for key in NEED_KEYS.values()} == {""}

    def test_a_draft_saves_with_some_needs_and_no_details(self, client, auth_headers):
        event = create(client, auth_headers(ORGANISER), preferredLayout="Banquet")

        assert event["status"] == "Draft"
        assert event["preferredLayout"] == "Banquet"

    def test_a_draft_keeps_every_answer(self, client, auth_headers, event_repository):
        event = create(client, auth_headers(ORGANISER), **REQUEST)

        for key in NEED_KEYS.values():
            assert event[key] == SUBMITTABLE_NEEDS[key]
        stored = event_repository.get_event(int(event["id"]))
        assert stored.needs == EventNeeds(**SUBMITTABLE_NEED_ATTRS)

    def test_a_not_required_answer_is_draft_content(self, client, auth_headers):
        """It is an answer — letters — so a draft holding only it is worth keeping."""
        event = create(client, auth_headers(ORGANISER), registrationNeeds=NOT_REQUIRED)

        assert event["registrationNeeds"] == NOT_REQUIRED

    def test_a_value_off_the_list_is_refused_even_on_a_draft(self, client, auth_headers):
        response = client.post(
            "/events",
            json={"title": "Gala", "venueRequirements": "Helipad"},
            headers=auth_headers(ORGANISER),
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Choose the venue requirements from the list. Helipad is not one of the options."
        )

    def test_the_owner_saves_needs_on_a_draft(self, client, auth_headers):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, title="Gala")

        response = client.put(
            f"/events/{event['id']}",
            json={"title": "Gala", **ALL_NOT_REQUIRED, "preferredLayout": "Cabaret"},
            headers=organiser,
        )

        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["status"] == "Draft"
        assert saved["preferredLayout"] == "Cabaret"
        assert saved["equipmentNeeds"] == NOT_REQUIRED

    def test_a_save_off_the_list_is_refused(self, client, auth_headers):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, title="Gala")

        response = client.put(
            f"/events/{event['id']}",
            json={"title": "Gala", "preferredLayout": "Ballroom"},
            headers=organiser,
        )

        assert response.status_code == 400
        assert "Ballroom is not one of the options" in response.json()["detail"]["message"]


# --- AC: on Submit, every field is required; missing ones block it ----------------


class TestSubmitting:
    def test_a_complete_request_is_submitted_and_kept(
        self, client, auth_headers, event_repository
    ):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, **REQUEST)

        response = submit(client, organiser, event["id"])

        assert response.status_code == 200, response.text
        submitted = response.json()
        assert submitted["status"] == "Submitted"
        for key in NEED_KEYS.values():
            assert submitted[key] == SUBMITTABLE_NEEDS[key]
        stored = event_repository.get_event(int(event["id"]))
        assert stored.status is EventStatus.SUBMITTED
        assert stored.needs == EventNeeds(**SUBMITTABLE_NEED_ATTRS)

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
            ({"startsAt": "2000-01-01T10:00", "endsAt": "2000-01-01T12:00"},
             "The start date cannot be in the past."),
            *[
                ({key: ""}, MISSING_MESSAGES[name])
                for name, key in NEED_KEYS.items()
            ],
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

    def test_a_draft_with_no_needs_cannot_be_submitted(self, client, auth_headers):
        organiser = auth_headers(ORGANISER)
        event = create(client, organiser, **DETAILS)

        response = submit(client, organiser, event["id"])

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == MISSING_MESSAGES["venue_requirements"]


class TestAttendanceUpperBound:
    """`events.expected_attendance` is INTEGER: past its maximum the write would fail."""

    def test_the_column_maximum_is_accepted(self, client, auth_headers):
        event = create(client, auth_headers(ORGANISER), title="Big", expectedAttendance=2147483647)

        assert event["expectedAttendance"] == 2147483647

    @pytest.mark.parametrize("attendance", [2147483648, 10**20])
    def test_one_past_it_is_refused_with_a_sentence(self, client, auth_headers, attendance):
        response = client.post(
            "/events",
            json={"title": "Big", "expectedAttendance": attendance},
            headers=auth_headers(ORGANISER),
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == ATTENDANCE_TOO_LARGE
        assert ATTENDANCE_TOO_LARGE == "Expected attendance must be 2,147,483,647 or fewer."


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


class TestCoordinator:
    def test_the_assigned_coordinator_sees_the_needs(self, client, auth_headers):
        event = _submitted_and_assigned(client, auth_headers)

        fetched = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Coordinator")
        ).json()

        for key in NEED_KEYS.values():
            assert fetched[key] == SUBMITTABLE_NEEDS[key]

    def test_a_coordinator_edit_saves_the_needs(self, client, auth_headers):
        event = _submitted_and_assigned(client, auth_headers)

        response = client.put(
            f"/events/{event['id']}",
            json={**REQUEST, "accessibilityNeeds": "Hearing loop, Lift"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["accessibilityNeeds"] == "Hearing loop, Lift"


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
    def test_every_read_selects_the_new_columns(self):
        for name in NEED_FIELDS:
            assert name in EVENT_COLUMNS

    def test_a_row_reads_back_its_needs(self, recorder):
        assert to_event(recorder.stored_row).needs == EventNeeds(**SUBMITTABLE_NEED_ATTRS)

    def test_a_null_column_reads_as_unanswered(self, recorder):
        row = {**recorder.stored_row, **{name: None for name in NEED_FIELDS}}
        assert to_event(row).needs == NO_NEEDS

    def test_create_writes_the_needs(self, recorder):
        SupabaseEvents().create_event(
            **DETAIL_KWARGS, organiser_id=ORGANISER_ID,
            needs=EventNeeds(preferred_layout="Theatre"),
        )

        _, written = recorder.inserts[0]
        assert written["preferred_layout"] == "Theatre"
        assert written["venue_requirements"] is None

    def test_create_without_needs_writes_nulls(self, recorder):
        SupabaseEvents().create_event(**DETAIL_KWARGS, organiser_id=ORGANISER_ID)

        _, written = recorder.inserts[0]
        assert all(written[name] is None for name in NEED_FIELDS)

    def test_save_writes_the_needs(self, recorder):
        SupabaseEvents().save_event(
            42, **DETAIL_KWARGS, needs=EventNeeds(**SUBMITTABLE_NEED_ATTRS)
        )

        _, written = recorder.updates[0]
        for name, value in SUBMITTABLE_NEED_ATTRS.items():
            assert written[name] == value

    def test_a_tracked_save_logs_each_changed_need(self, recorder):
        previous = to_event(recorder.stored_row)
        needs = EventNeeds(
            **{
                **SUBMITTABLE_NEED_ATTRS,
                "preferred_layout": "Banquet",
                "equipment_needs": NOT_REQUIRED,
            }
        )

        SupabaseEvents().save_event_with_tracking(
            42, **{**DETAIL_KWARGS, "starts_at": previous.starts_at, "ends_at": previous.ends_at},
            editor_id=COORDINATOR_ID, previous_event=previous, needs=needs,
        )

        (_, written), = recorder.updates
        assert written["preferred_layout"] == "Banquet"
        assert written["equipment_needs"] == NOT_REQUIRED
        (_, logged), = [item for item in recorder.inserts if item[0] == "event_changes"]
        assert [
            (row["changed_field"], row["old_value"], row["new_value"], row["change_type"])
            for row in logged
        ] == [
            ("preferred_layout", "Theatre", "Banquet", "routine"),
            ("equipment_needs", "Two wireless microphones", NOT_REQUIRED, "important"),
        ]
