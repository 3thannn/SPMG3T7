"""US11.1 — an Organiser requests changes to a submitted event; the Coordinator reviews.

Acceptance criteria, and where each is asserted:

AC1  The Organiser can open the existing edit form to propose changes to their
     submitted event — the request takes the same fields the form sends
     (TestProposing), and a direct edit is refused once submitted
     (TestDirectEditsAreRefused).
AC2  They can edit the permitted details and submit them for Coordinator
     review, and the status changes to Under Review (TestProposing,
     TestWhoMayPropose, TestWhenAProposalIsRefused, TestProposalValidation).
AC3  The proposed changes are visible to the Coordinator (TestCoordinatorSees).
AC4  Date/time, attendance, venue and equipment changes are identified as
     important, following US5.2's logging rule (TestImportance, TestRules).
AC5  The Coordinator can review the proposed changes before deciding whether to
     approve or reject them (TestApproving, TestRejecting,
     TestReviewBeforeDeciding).

The pure rules in `app.change_requests` are tested as functions; the routes are
tested as requests; the Supabase store is tested against a fake client, so
every line of the feature runs without a database.
"""

import pytest

from app import change_requests, supabase_client
from app.change_requests import (
    CHANGE_REQUEST_REFUSAL_MESSAGES,
    EDITABLE_FIELDS,
    IMPORTANT_FIELDS,
    NOTHING_PENDING_MESSAGE,
    ChangeRequestRefusal,
    ChangeReview,
    FieldChange,
    applied_values,
    change_request_refusal_message,
    check_change_request,
    diff,
    has_pending_request,
    history_kind,
    is_important,
    label_for,
    ordered,
    reopen_reason,
)
from app.event_status import EventStatus
from app.event_store import (
    CHANGE_REQUESTS_TABLE,
    EVENT_CHANGES_TABLE,
    Event,
    InMemoryEvents,
    StaleEventStatus,
    SupabaseEvents,
    latest_review,
    to_change,
    to_event,
    to_field_change,
)
from app.events import CHANGE_NOTE_MAX, DECISION_REASON_MAX, PURPOSE_MAX, TITLE_MAX
from app.permissions import Role
from app.users import User
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    PASSWORD,
    SUBMITTABLE_NEED_ATTRS,
    SUBMITTABLE_NEEDS,
    TODAY,
)

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}

ORGANISER = "Event Organiser"
COORDINATOR = "Event Coordinator"
VENUE_STAFF = "Venue Staff"

OTHER_ORGANISER_ID = 7
OTHER_COORDINATOR_ID = 8


# --- helpers -----------------------------------------------------------------


def submitted_event(client, auth_headers) -> dict:
    """The state US11.1 starts from: submitted and assigned to the Coordinator."""
    organiser = auth_headers(ORGANISER)
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    submitted = client.post(f"/events/{created.json()['id']}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text
    lead = auth_headers("Event Coordinator Lead")
    assigned = client.post(
        f"/events/{submitted.json()['id']}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=lead,
    )
    assert assigned.status_code == 200, assigned.text
    asked = client.post(
        f"/events/{assigned.json()['id']}/clarification",
        json={"message": "Please amend the request."},
        headers=auth_headers(COORDINATOR),
    )
    assert asked.status_code == 200, asked.text
    return asked.json()


def under_review_event(client, auth_headers) -> dict:
    """A submitted event the Coordinator has already asked a question about (US7.3)."""
    event = submitted_event(client, auth_headers)
    asked = client.post(
        f"/events/{event['id']}/clarification",
        json={"message": "Can the start move to 19:00?"},
        headers=auth_headers(COORDINATOR),
    )
    assert asked.status_code == 200, asked.text
    return asked.json()


def propose(client, headers, event_id: str, note: str = "", **changes):
    return client.post(
        f"/events/{event_id}/change-request",
        json={**DRAFT, **changes, "note": note},
        headers=headers,
    )


def approve(client, headers, event_id: str):
    return client.post(f"/events/{event_id}/change-request/approve", headers=headers)


def reject(client, headers, event_id: str, reason: str = "The hall is booked that night."):
    return client.post(
        f"/events/{event_id}/change-request/reject", json={"reason": reason}, headers=headers
    )


def pending_event(client, auth_headers, **changes) -> dict:
    event = submitted_event(client, auth_headers)
    response = propose(client, auth_headers(ORGANISER), event["id"], **changes)
    assert response.status_code == 200, response.text
    return response.json()


def seed(event_repository, **overrides) -> Event:
    """Put an event straight into the store, for a status the routes cannot reach."""
    fields = {
        "id": 500,
        "title": "Seeded",
        "purpose": "Purpose",
        "description": "",
        "starts_at": "2027-11-02T18:00",
        "ends_at": "2027-11-02T21:00",
        "expected_attendance": 50,
        "status": EventStatus.APPROVED,
        "organiser_id": ORGANISER_ID,
        "organiser_name": "Dylan",
        "created_at": "2026-01-01T09:00:00",
        "updated_at": "2026-01-01T09:00:00",
        "coordinator_id": COORDINATOR_ID,
    }
    event = Event(**{**fields, **overrides})
    event_repository.events.append(event)
    return event


def add_user(user_store, client, user_id: int, role: Role) -> dict[str, str]:
    """Another account of a role, signed in, for the "not yours" cases."""
    email = f"user{user_id}@spmg3t7.edu"
    user_store.users.append(User(id=user_id, email=email, name=f"User {user_id}", role=role))
    user_store.passwords[email] = PASSWORD
    signed_in = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    return {"Authorization": f"Bearer {signed_in.json()['token']}"}


def changes_by_field(event: dict) -> dict[str, dict]:
    return {change["field"]: change for change in event["pendingChanges"]}


# --- the rules, as functions ---------------------------------------------------


def _event(**overrides) -> Event:
    fields = {
        "id": 1,
        "title": "Title",
        "purpose": "Purpose",
        "description": "Description",
        "starts_at": "2027-11-02T18:00:00",
        "ends_at": "2027-11-02T21:00:00",
        "expected_attendance": 120,
        "status": EventStatus.SUBMITTED,
        "organiser_id": ORGANISER_ID,
        "organiser_name": "Dylan",
        "created_at": "2026-01-01T09:00:00",
        "updated_at": "2026-01-01T09:00:00",
    }
    return Event(**{**fields, **overrides})


class TestRules:
    @pytest.mark.parametrize(
        "column", ["proposed_date", "end_date", "expected_attendance", "venue_id", "equipment"]
    )
    def test_date_time_attendance_venue_and_equipment_are_important(self, column):
        assert is_important(column)

    @pytest.mark.parametrize("column", ["name", "purpose", "description", "unknown"])
    def test_everything_else_is_routine(self, column):
        assert not is_important(column)

    def test_the_important_set_is_exactly_the_story_s_list(self):
        assert IMPORTANT_FIELDS == {
            "proposed_date",
            "end_date",
            "expected_attendance",
            "venue_id",
            "equipment",
            "equipment_needs",
            "venue_requirements",
            "preferred_layout",
            "accessibility_needs",
        }

    def test_change_type_uses_us5_2_s_column_values(self):
        important = FieldChange("proposed_date", "a", "b", important=True)
        routine = FieldChange("name", "a", "b", important=False)
        assert change_requests.change_type(important) == "important"
        assert change_requests.change_type(routine) == "routine"

    def test_labels_match_the_edit_form(self):
        assert [label_for(field.column) for field in EDITABLE_FIELDS] == [
            "Title",
            "Starts",
            "Ends",
            "Purpose",
            "Expected attendance",
            "Description",
            "Venue requirements",
            "Preferred layout",
            "Accessibility needs",
            "Equipment needs",
            "Registration needs",
        ]

    def test_an_unknown_column_is_labelled_by_its_name(self):
        assert label_for("venue_id") == "venue_id"

    def test_identical_values_are_no_change(self):
        assert diff(_event(), _event()) == ()

    @pytest.mark.parametrize(
        ("attr", "value", "column", "old", "new", "important"),
        [
            ("title", "Renamed", "name", "Title", "Renamed", False),
            ("purpose", "New purpose", "purpose", "Purpose", "New purpose", False),
            ("description", "", "description", "Description", "", False),
            (
                "starts_at",
                "2027-11-03T18:00",
                "proposed_date",
                "2027-11-02T18:00:00",
                "2027-11-03T18:00",
                True,
            ),
            (
                "ends_at",
                "2027-11-02T22:00",
                "end_date",
                "2027-11-02T21:00:00",
                "2027-11-02T22:00",
                True,
            ),
            ("expected_attendance", 150, "expected_attendance", "120", "150", True),
            ("expected_attendance", None, "expected_attendance", "120", "", True),
        ],
    )
    def test_each_field_is_diffed_and_classified(self, attr, value, column, old, new, important):
        changes = diff(_event(), _event(**{attr: value}))

        assert changes == (FieldChange(column, old, new, important),)

    def test_the_same_moment_written_without_seconds_is_not_a_change(self):
        # The database returns seconds; a datetime-local input does not.
        assert diff(_event(), _event(starts_at="2027-11-02T18:00")) == ()

    def test_clearing_an_end_date_is_a_change(self):
        assert diff(_event(), _event(ends_at="")) == (
            FieldChange("end_date", "2027-11-02T21:00:00", "", True),
        )

    def test_two_empty_dates_are_the_same(self):
        assert diff(_event(ends_at=""), _event(ends_at="")) == ()

    def test_unparseable_dates_fall_back_to_comparing_text(self):
        assert diff(_event(ends_at="soon"), _event(ends_at="soon")) == ()
        assert diff(_event(ends_at="soon"), _event(ends_at="later")) == (
            FieldChange("end_date", "soon", "later", True),
        )

    def test_text_is_compared_exactly(self):
        # Validation does not trim what an Organiser wrote, so neither does this.
        assert diff(_event(), _event(title="Title ")) == (
            FieldChange("name", "Title", "Title ", False),
        )

    def test_several_changes_come_back_in_form_order(self):
        changes = diff(_event(), _event(description="New", title="New", expected_attendance=1))

        assert [change.field for change in changes] == [
            "name",
            "expected_attendance",
            "description",
        ]

    def test_ordered_puts_unknown_columns_last(self):
        shuffled = [
            FieldChange("venue_id", "1", "2", True),
            FieldChange("description", "a", "b", False),
            FieldChange("name", "a", "b", False),
        ]

        assert [change.field for change in ordered(shuffled)] == [
            "name",
            "description",
            "venue_id",
        ]

    def test_applied_values_are_typed_as_the_event_holds_them(self):
        values = applied_values(
            [
                FieldChange("name", "a", "Renamed", False),
                FieldChange("proposed_date", "a", "2027-11-03T18:00", True),
                FieldChange("expected_attendance", "120", "150", True),
                FieldChange("venue_id", "1", "2", True),
            ]
        )

        assert values == {
            "title": "Renamed",
            "starts_at": "2027-11-03T18:00",
            "expected_attendance": 150,
        }

    def test_a_cleared_attendance_applies_as_none(self):
        values = applied_values([FieldChange("expected_attendance", "120", "", True)])

        assert values == {"expected_attendance": None}

    @pytest.mark.parametrize("status", change_requests.REQUESTABLE)
    def test_the_owner_may_request_on_a_submitted_or_reviewed_event(self, status):
        assert (
            check_change_request(
                status=status,
                organiser_id=ORGANISER_ID,
                actor_id=ORGANISER_ID,
                change_requested=False,
            )
            is None
        )

    def test_someone_else_is_told_it_is_not_theirs_first(self):
        # Even on a Draft with a request pending: ownership is checked first.
        assert (
            check_change_request(
                status=EventStatus.DRAFT,
                organiser_id=ORGANISER_ID,
                actor_id=OTHER_ORGANISER_ID,
                change_requested=True,
            )
            is ChangeRequestRefusal.NOT_OWNER
        )

    def test_a_draft_is_edited_directly_instead(self):
        assert (
            check_change_request(
                status=EventStatus.DRAFT,
                organiser_id=ORGANISER_ID,
                actor_id=ORGANISER_ID,
                change_requested=False,
            )
            is ChangeRequestRefusal.NOT_SUBMITTED
        )

    @pytest.mark.parametrize(
        "status",
        [
            EventStatus.REJECTED,
            EventStatus.UNDER_REVIEW,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        ],
    )
    def test_a_decided_event_cannot_have_changes_requested(self, status):
        assert (
            check_change_request(
                status=status,
                organiser_id=ORGANISER_ID,
                actor_id=ORGANISER_ID,
                change_requested=False,
            )
            is ChangeRequestRefusal.ALREADY_DECIDED
        )

    def test_one_request_at_a_time(self):
        assert (
            check_change_request(
                status=EventStatus.APPROVED,
                organiser_id=ORGANISER_ID,
                actor_id=ORGANISER_ID,
                change_requested=True,
            )
            is ChangeRequestRefusal.ALREADY_PENDING
        )

    @pytest.mark.parametrize("reason", list(ChangeRequestRefusal))
    def test_every_refusal_has_a_message(self, reason):
        assert change_request_refusal_message(reason) == CHANGE_REQUEST_REFUSAL_MESSAGES[reason]
        assert change_request_refusal_message(reason).endswith(".")

    @pytest.mark.parametrize(
        ("by_id", "to_status", "expected"),
        [
            (ORGANISER_ID, EventStatus.UNDER_REVIEW, "change-request"),
            (ORGANISER_ID, EventStatus.SUBMITTED, ""),
            (COORDINATOR_ID, EventStatus.UNDER_REVIEW, ""),
            (COORDINATOR_ID, EventStatus.APPROVED, ""),
        ],
        ids=["organiser-to-review", "organiser-submits", "clarification", "decision"],
    )
    def test_a_change_request_entry_is_recognised_without_a_column(
        self, by_id, to_status, expected
    ):
        assert history_kind(by_id=by_id, organiser_id=ORGANISER_ID, to_status=to_status) == expected

    @pytest.mark.parametrize(
        ("status", "flagged", "expected"),
        [
            (EventStatus.UNDER_REVIEW, True, True),
            (EventStatus.UNDER_REVIEW, False, False),
            (EventStatus.APPROVED, True, True),
            (EventStatus.PLANNING, True, True),
            (EventStatus.SUBMITTED, False, False),
        ],
    )
    def test_a_request_is_pending_at_each_requestable_status(self, status, flagged, expected):
        assert has_pending_request(status=status, change_requested=flagged) is expected


# --- AC1/AC2: proposing changes --------------------------------------------------


class TestProposing:
    def test_the_organiser_can_submit_a_change_request(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(ORGANISER), event["id"], title="Welcome Night")

        assert response.status_code == 200, response.text

    def test_the_status_changes_to_under_review(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert event["status"] == "Under Review"

    def test_the_change_requested_flag_is_set(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert event["changeRequested"] is True

    def test_the_event_itself_is_not_edited(self, client, auth_headers):
        # The point of the story: reviewed, not applied.
        event = pending_event(client, auth_headers, title="Welcome Night", expectedAttendance=200)

        assert event["title"] == DRAFT["title"]
        assert event["expectedAttendance"] == DRAFT["expectedAttendance"]

    def test_only_the_fields_that_differ_are_proposed(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert event["pendingChanges"] == [
            {
                "field": "name",
                "label": "Title",
                "oldValue": DRAFT["title"],
                "newValue": "Welcome Night",
                "important": False,
            }
        ]

    def test_every_permitted_field_can_be_proposed(self, client, auth_headers):
        event = pending_event(
            client,
            auth_headers,
            title="Welcome Night",
            purpose="Meet the cohort.",
            description="Talks and dinner.",
            startsAt="2027-11-03T18:00",
            endsAt="2027-11-03T22:00",
            expectedAttendance=150,
        )

        assert [change["field"] for change in event["pendingChanges"]] == [
            "name",
            "proposed_date",
            "end_date",
            "purpose",
            "expected_attendance",
            "description",
        ]

    def test_the_request_is_recorded_in_the_history(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        latest = event["history"][-1]
        assert latest["from"] == "Under Review"
        assert latest["to"] == "Under Review"
        assert latest["byId"] == "2"
        assert latest["byName"] == "Priya"
        assert latest["kind"] == ""
        assert latest["at"]
        assert event["changeRequested"] is True

    def test_the_note_travels_with_the_request(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(
            client,
            auth_headers(ORGANISER),
            event["id"],
            note="  Moved to 19:00 as you asked.  ",
            startsAt="2027-11-02T19:00",
        )

        assert response.json()["changeRequestNote"] == "Moved to 19:00 as you asked."

    def test_the_note_is_optional(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert event["changeRequestNote"] == ""

