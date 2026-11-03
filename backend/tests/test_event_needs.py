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
            id=1,
            title="",
            purpose="",
            description="",
            starts_at="",
            ends_at="",
            expected_attendance=None,
            status=EventStatus.DRAFT,
            organiser_id=1,
            organiser_name="",
            created_at="",
            updated_at="",
            **SUBMITTABLE_NEED_ATTRS,
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

