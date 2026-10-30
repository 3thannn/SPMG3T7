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

from datetime import date

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

    def test_a_whitespace_note_is_stored_as_no_note(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(ORGANISER), event["id"], "   ", title="New")

        assert response.json()["changeRequestNote"] == ""

    def test_a_note_of_exactly_the_limit_is_accepted(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(
            client, auth_headers(ORGANISER), event["id"], "n" * CHANGE_NOTE_MAX, title="New"
        )

        assert response.status_code == 200, response.text

    def test_an_answer_to_a_clarification_stays_under_review(self, client, auth_headers):
        # US7.3 hands the Organiser's reply to this story.
        event = under_review_event(client, auth_headers)

        response = propose(
            client, auth_headers(ORGANISER), event["id"], startsAt="2027-11-02T19:00"
        )

        assert response.status_code == 200, response.text
        latest = response.json()["history"][-1]
        assert (latest["from"], latest["to"]) == ("Under Review", "Under Review")
        assert response.json()["changeRequested"] is True

    def test_a_clarification_entry_is_not_labelled_as_a_change_request(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        assert all(entry["kind"] == "" for entry in event["history"])

    def test_the_organiser_sees_their_own_pending_request(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(ORGANISER)).json()

        assert fetched["changeRequested"] is True
        assert fetched["pendingChanges"] == event["pendingChanges"]

    def test_an_event_without_a_request_reports_none(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        assert event["changeRequested"] is False
        assert event["pendingChanges"] == []


class TestDirectEditsAreRefused:
    @pytest.mark.parametrize("make", [submitted_event, under_review_event])
    def test_the_owner_cannot_save_a_submitted_event_directly(self, client, auth_headers, make):
        event = make(client, auth_headers)

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Sneaky"},
            headers=auth_headers(ORGANISER),
        )

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "change-request-required"
        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(ORGANISER)).json()
        assert fetched["title"] == DRAFT["title"]

    def test_the_owner_still_edits_a_draft_directly(self, client, auth_headers):
        created = client.post("/events", json=DRAFT, headers=auth_headers(ORGANISER)).json()

        response = client.put(
            f"/events/{created['id']}",
            json={**DRAFT, "title": "Still a draft"},
            headers=auth_headers(ORGANISER),
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Still a draft"


class TestWhoMayPropose:
    def test_a_coordinator_cannot_propose(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(COORDINATOR), event["id"], title="New")

        assert response.status_code == 403

    def test_venue_staff_cannot_propose(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(VENUE_STAFF), event["id"], title="New")

        assert response.status_code == 403

    def test_a_signed_out_caller_cannot_propose(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, {}, event["id"], title="New")

        assert response.status_code == 401

    def test_another_organiser_is_told_the_event_does_not_exist(
        self, client, auth_headers, user_store
    ):
        event = submitted_event(client, auth_headers)
        other = add_user(user_store, client, OTHER_ORGANISER_ID, Role.ORGANISER)

        response = propose(client, other, event["id"], title="New")

        assert response.status_code == 404

    @pytest.mark.parametrize("event_id", ["99999", "not-a-number"])
    def test_an_unknown_event_is_not_found(self, client, auth_headers, event_id):
        response = propose(client, auth_headers(ORGANISER), event_id, title="New")

        assert response.status_code == 404


class TestWhenAProposalIsRefused:
    def test_a_draft_is_refused(self, client, auth_headers):
        created = client.post("/events", json=DRAFT, headers=auth_headers(ORGANISER)).json()

        response = propose(client, auth_headers(ORGANISER), created["id"], title="New")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-submitted"

    @pytest.mark.parametrize("status", [EventStatus.REJECTED, EventStatus.UNDER_REVIEW])
    def test_a_decided_event_is_refused(self, client, auth_headers, event_repository, status):
        seeded = seed(event_repository, status=status)

        response = propose(client, auth_headers(ORGANISER), str(seeded.id), title="New")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "already-decided"

    def test_a_second_request_waits_for_the_first(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = propose(client, auth_headers(ORGANISER), event["id"], title="Another")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "already-pending"
        assert (
            response.json()["detail"]["message"]
            == (CHANGE_REQUEST_REFUSAL_MESSAGES[ChangeRequestRefusal.ALREADY_PENDING])
        )

    def test_a_request_that_changes_nothing_is_refused(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(ORGANISER), event["id"])

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Change at least one detail before requesting a change."
        )

    def test_the_same_time_without_seconds_changes_nothing(
        self, client, auth_headers, event_repository
    ):
        # What the database hands back has seconds; the form's input does not.
        seeded = seed(
            event_repository,
            status=EventStatus.SUBMITTED,
            title=DRAFT["title"],
            purpose=DRAFT["purpose"],
            description=DRAFT["description"],
            starts_at="2027-11-02T18:00:00",
            ends_at="2027-11-02T21:00:00",
            expected_attendance=DRAFT["expectedAttendance"],
            **SUBMITTABLE_NEED_ATTRS,
        )

        response = propose(client, auth_headers(ORGANISER), str(seeded.id))

        assert response.status_code == 400

    def test_a_refused_request_leaves_the_event_alone(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        propose(client, auth_headers(ORGANISER), event["id"], expectedAttendance=0)

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(ORGANISER)).json()
        assert fetched["status"] == "Under Review"
        assert fetched["changeRequested"] is False
        assert len(fetched["history"]) == len(event["history"])

    def test_a_note_over_the_limit_is_refused(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = propose(
            client, auth_headers(ORGANISER), event["id"], "n" * (CHANGE_NOTE_MAX + 1), title="New"
        )

        assert response.status_code == 400

    def test_a_concurrent_request_is_reported_as_stale(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = submitted_event(client, auth_headers)
        original = event_repository.submit_change_request

        def another_request_lands_first(event_id, **kwargs):
            original(event_id, **kwargs)
            return original(event_id, **kwargs)

        monkeypatch.setattr(event_repository, "submit_change_request", another_request_lands_first)

        response = propose(client, auth_headers(ORGANISER), event["id"], title="New")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"


class TestProposalValidation:
    """A submitted event has to stay complete, so a proposal is validated as a submission."""

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"title": ""}, "Give the event a title."),
            ({"title": "   "}, "Give the event a title."),
            ({"purpose": ""}, "Give the event a purpose."),
            ({"startsAt": "", "endsAt": None}, "Give the event a date."),
            ({"expectedAttendance": None}, "Give the expected attendance."),
            ({"expectedAttendance": 0}, "Expected attendance must be at least 1."),
            ({"expectedAttendance": -1}, "Expected attendance cannot be negative."),
            (
                {"startsAt": "2020-01-01T10:00", "endsAt": None},
                "The start date cannot be in the past.",
            ),
            ({"endsAt": "2027-11-02T18:00"}, "The end date must be after the start date."),
            ({"endsAt": "2027-11-02T17:00"}, "The end date must be after the start date."),
            ({"startsAt": "not-a-date", "endsAt": None}, "Give the event a valid date."),
            # US2.1 (Sprint 3): the end time, description and every need are
            # now required to submit, so a proposal cannot clear them either.
            ({"endsAt": None}, "Give the event an end date."),
            ({"description": ""}, "Give the event a description."),
            ({"description": "  "}, "Give the event a description."),
            (
                {"venueRequirements": ""},
                "Choose the venue requirements, or None / Not required.",
            ),
            ({"preferredLayout": ""}, "Choose a preferred layout, or None / Not required."),
            (
                {"accessibilityNeeds": ""},
                "Choose the accessibility needs, or None / Not required.",
            ),
            (
                {"equipmentNeeds": " "},
                "Describe the equipment needs, or choose None / Not required.",
            ),
            (
                {"registrationNeeds": ""},
                "Describe the registration needs, or choose None / Not required.",
            ),
            (
                {"preferredLayout": "Ballroom"},
                "Choose a preferred layout from the list. Ballroom is not one of the options.",
            ),
            (
                {"title": "t" * (TITLE_MAX + 1)},
                f"Keep the title to {TITLE_MAX} characters or fewer.",
            ),
            (
                {"purpose": "p" * (PURPOSE_MAX + 1)},
                f"Keep the purpose to {PURPOSE_MAX} characters or fewer.",
            ),
            (
                {
                    "title": "",
                    "purpose": "",
                    "description": "",
                    "startsAt": "",
                    "endsAt": None,
                    "expectedAttendance": None,
                    "venueRequirements": "",
                    "preferredLayout": "",
                    "accessibilityNeeds": "",
                    "equipmentNeeds": "",
                    "registrationNeeds": "",
                },
                "Enter at least one letter or number in any field to save a draft.",
            ),
        ],
    )
    def test_an_incomplete_or_invalid_proposal_is_refused(
        self, client, auth_headers, changes, message
    ):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(ORGANISER), event["id"], **changes)

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == message

    @pytest.mark.parametrize(
        "changes",
        [
            {"expectedAttendance": 1},
            {"title": "t" * TITLE_MAX},
            {"purpose": "p" * PURPOSE_MAX},
            {"endsAt": "2027-11-02T18:01"},
            {
                "startsAt": f"{date.today().isoformat()}T23:00",
                "endsAt": f"{date.today().isoformat()}T23:59",
            },
            {"venueRequirements": "None / Not required", "preferredLayout": "Banquet"},
        ],
        ids=[
            "attendance-at-least-one",
            "title-at-limit",
            "purpose-at-limit",
            "end-one-minute-after-start",
            "starts-today",
            "needs-changed",
        ],
    )
    def test_a_proposal_at_the_boundary_is_accepted(self, client, auth_headers, changes):
        event = submitted_event(client, auth_headers)

        response = propose(client, auth_headers(ORGANISER), event["id"], **changes)

        assert response.status_code == 200, response.text


# --- AC3: visible to the Coordinator -------------------------------------------


class TestCoordinatorSees:
    def test_the_assigned_coordinator_sees_the_proposed_changes(self, client, auth_headers):
        event = pending_event(client, auth_headers, startsAt="2027-11-02T17:00")

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(COORDINATOR)).json()

        assert fetched["changeRequested"] is True
        assert fetched["pendingChanges"] == [
            {
                "field": "proposed_date",
                "label": "Starts",
                "oldValue": DRAFT["startsAt"],
                "newValue": "2027-11-02T17:00",
                "important": True,
            }
        ]

    def test_the_request_is_in_the_coordinator_s_review_queue(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        listed = client.get("/events", headers=auth_headers(COORDINATOR)).json()

        flagged = [item for item in listed if item["changeRequested"]]
        assert [item["id"] for item in flagged] == [event["id"]]
        assert flagged[0]["pendingChanges"] == event["pendingChanges"]

    def test_the_organiser_s_note_is_visible_to_the_coordinator(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        propose(client, auth_headers(ORGANISER), event["id"], "Venue moved.", title="New")

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(COORDINATOR)).json()

        assert fetched["changeRequestNote"] == "Venue moved."

    def test_an_unassigned_coordinator_cannot_see_it(self, client, auth_headers, user_store):
        event = pending_event(client, auth_headers, title="Welcome Night")
        other = add_user(user_store, client, OTHER_COORDINATOR_ID, Role.COORDINATOR)

        assert client.get(f"/events/{event['id']}", headers=other).status_code == 404
        assert client.get("/events", headers=other).json() == []


# --- AC4: important changes ------------------------------------------------------


class TestImportance:
    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"startsAt": "2027-11-03T18:00", "endsAt": "2027-11-03T21:00"}, "proposed_date"),
            ({"endsAt": "2027-11-02T22:00"}, "end_date"),
            ({"expectedAttendance": 150}, "expected_attendance"),
        ],
    )
    def test_date_time_and_attendance_changes_are_important(
        self, client, auth_headers, changes, field
    ):
        event = pending_event(client, auth_headers, **changes)

        assert changes_by_field(event)[field]["important"] is True

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"title": "Renamed"}, "name"),
            ({"purpose": "New purpose"}, "purpose"),
            ({"description": "New description"}, "description"),
        ],
    )
    def test_wording_changes_are_routine(self, client, auth_headers, changes, field):
        event = pending_event(client, auth_headers, **changes)

        assert changes_by_field(event)[field]["important"] is False

    def test_a_mixed_request_flags_each_field_on_its_own(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Renamed", expectedAttendance=150)

        flags = {field: change["important"] for field, change in changes_by_field(event).items()}
        assert flags == {"name": False, "expected_attendance": True}

    def test_approved_changes_are_logged_as_important_or_routine(
        self, client, auth_headers, event_repository
    ):
        # US5.2's logging rule: the applied rows keep their classification.
        event = pending_event(client, auth_headers, title="Renamed", expectedAttendance=150)

        approve(client, auth_headers(COORDINATOR), event["id"])

        logged = [
            (change.field, change_requests.change_type(change))
            for _, change in event_repository.change_log
        ]
        assert logged == [("name", "routine"), ("expected_attendance", "important")]


class TestWhereRequestsAreStored:
    """A request is not a change: `event_changes` only ever holds applied changes."""

    def test_a_pending_request_is_not_logged_as_a_change(
        self, client, auth_headers, event_repository
    ):
        pending_event(client, auth_headers, title="Renamed", expectedAttendance=150)

        assert event_repository.change_log == []

    def test_a_pending_request_is_kept_as_a_request(self, client, auth_headers, event_repository):
        event = pending_event(client, auth_headers, title="Renamed", expectedAttendance=150)

        assert [
            (event_id, change.field, change.important, status)
            for event_id, change, status in event_repository.change_requests
        ] == [
            (int(event["id"]), "name", False, "pending"),
            (int(event["id"]), "expected_attendance", True, "pending"),
        ]

    def test_approving_marks_the_request_and_logs_the_change(
        self, client, auth_headers, event_repository
    ):
        event = pending_event(client, auth_headers, title="Renamed")

        approve(client, auth_headers(COORDINATOR), event["id"])

        assert [status for _, _, status in event_repository.change_requests] == ["approved"]
        assert [change.field for _, change in event_repository.change_log] == ["name"]

    def test_rejecting_marks_the_request_and_logs_nothing(
        self, client, auth_headers, event_repository
    ):
        event = pending_event(client, auth_headers, title="Renamed")

        reject(client, auth_headers(COORDINATOR), event["id"])

        assert [status for _, _, status in event_repository.change_requests] == ["rejected"]
        assert event_repository.change_log == []

    def test_answering_one_request_leaves_earlier_and_other_requests_alone(
        self, client, auth_headers, event_repository
    ):
        first = pending_event(client, auth_headers, title="Renamed")
        reject(client, auth_headers(COORDINATOR), first["id"])
        client.post(
            f"/events/{first['id']}/clarification",
            json={"message": "Please amend again."},
            headers=auth_headers(COORDINATOR),
        )
        propose(client, auth_headers(ORGANISER), first["id"], purpose="Second ask.")
        other = pending_event(client, auth_headers, description="Another event.")

        approve(client, auth_headers(COORDINATOR), first["id"])

        assert [
            (event_id, change.field, status)
            for event_id, change, status in event_repository.change_requests
        ] == [
            (int(first["id"]), "name", "rejected"),
            (int(first["id"]), "purpose", "approved"),
            (int(other["id"]), "description", "pending"),
        ]
        assert [change.field for _, change in event_repository.change_log] == ["purpose"]


# --- AC5: the Coordinator reviews, then decides ----------------------------------


class TestApproving:
    def test_approving_applies_the_proposed_values(self, client, auth_headers):
        event = pending_event(
            client,
            auth_headers,
            title="Welcome Night",
            startsAt="2027-11-03T18:00",
            endsAt="2027-11-03T21:00",
            expectedAttendance=150,
        )

        response = approve(client, auth_headers(COORDINATOR), event["id"])

        assert response.status_code == 200, response.text
        approved = response.json()
        assert approved["title"] == "Welcome Night"
        assert approved["startsAt"] == "2027-11-03T18:00"
        assert approved["endsAt"] == "2027-11-03T21:00"
        assert approved["expectedAttendance"] == 150

    def test_approving_clears_the_flag_and_the_proposal(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        approved = approve(client, auth_headers(COORDINATOR), event["id"]).json()

        assert approved["changeRequested"] is False
        assert approved["pendingChanges"] == []

    def test_approving_leaves_the_event_under_review_for_a_decision(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        approved = approve(client, auth_headers(COORDINATOR), event["id"]).json()

        assert approved["status"] == "Under Review"

    def test_approving_is_recorded_for_the_organiser(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        approve(client, auth_headers(COORDINATOR), event["id"])

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(ORGANISER)).json()

        review = fetched["lastChangeReview"]
        assert review["outcome"] == "approved"
        assert review["note"] == ""
        assert review["at"]

    def test_answering_adds_no_status_history_entry(self, client, auth_headers):
        # The status does not move, so there is no status change to record.
        event = pending_event(client, auth_headers, title="Welcome Night")

        approved = approve(client, auth_headers(COORDINATOR), event["id"]).json()

        assert approved["history"] == event["history"]

    def test_an_event_never_asked_about_has_no_review(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        assert event["lastChangeReview"] is None

    def test_a_new_request_keeps_the_previous_answer_visible(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        reject(client, auth_headers(COORDINATOR), event["id"], "Keep the name.")

        client.post(
            f"/events/{event['id']}/clarification",
            json={"message": "Please amend again."},
            headers=auth_headers(COORDINATOR),
        )
        again = propose(client, auth_headers(ORGANISER), event["id"], purpose="New").json()

        assert again["changeRequested"] is True
        assert again["lastChangeReview"]["outcome"] == "rejected"
        assert again["lastChangeReview"]["note"] == "Keep the name."

    def test_a_changed_need_is_applied(self, client, auth_headers):
        """US2.1 (Sprint 3): the needs are proposed and applied like any field."""
        event = pending_event(
            client, auth_headers, preferredLayout="Banquet", equipmentNeeds="None / Not required"
        )
        assert [(change["field"], change["important"]) for change in event["pendingChanges"]] == [
            ("preferred_layout", True),
            ("equipment_needs", True),
        ]

        approved = approve(client, auth_headers(COORDINATOR), event["id"]).json()

        assert approved["preferredLayout"] == "Banquet"
        assert approved["equipmentNeeds"] == "None / Not required"

    def test_the_organiser_may_ask_again_once_answered(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        approve(client, auth_headers(COORDINATOR), event["id"])

        client.post(
            f"/events/{event['id']}/clarification",
            json={"message": "Please amend again."},
            headers=auth_headers(COORDINATOR),
        )
        response = propose(
            client, auth_headers(ORGANISER), event["id"], title="Welcome Night", purpose="New"
        )

        assert response.status_code == 200, response.text
        # Diffed against the approved values, so the title is no longer a change.
        assert [change["field"] for change in response.json()["pendingChanges"]] == ["purpose"]


class TestRejecting:
    def test_rejecting_keeps_the_current_values(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night", expectedAttendance=150)

        response = reject(client, auth_headers(COORDINATOR), event["id"])

        assert response.status_code == 200, response.text
        rejected = response.json()
        assert rejected["title"] == DRAFT["title"]
        assert rejected["expectedAttendance"] == DRAFT["expectedAttendance"]
        assert rejected["changeRequested"] is False
        assert rejected["pendingChanges"] == []
        assert rejected["status"] == "Under Review"

    def test_the_reason_is_visible_to_the_organiser(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        reject(client, auth_headers(COORDINATOR), event["id"], "  Keep the original name.  ")

        fetched = client.get(f"/events/{event['id']}", headers=auth_headers(ORGANISER)).json()

        assert fetched["lastChangeReview"]["outcome"] == "rejected"
        assert fetched["lastChangeReview"]["note"] == "Keep the original name."

    def test_rejected_requests_are_kept_as_rejected(self, client, auth_headers, event_repository):
        event = pending_event(client, auth_headers, title="Welcome Night")

        reject(client, auth_headers(COORDINATOR), event["id"])

        assert [status for _, _, status in event_repository.change_requests] == ["rejected"]

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_reason_is_required(self, client, auth_headers, reason):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = reject(client, auth_headers(COORDINATOR), event["id"], reason)

        assert response.status_code == 400
        still = client.get(f"/events/{event['id']}", headers=auth_headers(COORDINATOR)).json()
        assert still["changeRequested"] is True

    def test_a_reason_of_exactly_the_limit_is_accepted(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = reject(client, auth_headers(COORDINATOR), event["id"], "r" * DECISION_REASON_MAX)

        assert response.status_code == 200

    def test_a_reason_over_the_limit_is_refused(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = reject(
            client, auth_headers(COORDINATOR), event["id"], "r" * (DECISION_REASON_MAX + 1)
        )

        assert response.status_code == 400


class TestWhoMayReview:
    @pytest.mark.parametrize("action", [approve, reject])
    def test_the_organiser_cannot_answer_their_own_request(self, client, auth_headers, action):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert action(client, auth_headers(ORGANISER), event["id"]).status_code == 403

    @pytest.mark.parametrize("action", [approve, reject])
    def test_venue_staff_cannot_answer(self, client, auth_headers, action):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert action(client, auth_headers(VENUE_STAFF), event["id"]).status_code == 403

    @pytest.mark.parametrize("action", [approve, reject])
    def test_an_unassigned_coordinator_cannot_answer(
        self, client, auth_headers, user_store, action
    ):
        event = pending_event(client, auth_headers, title="Welcome Night")
        other = add_user(user_store, client, OTHER_COORDINATOR_ID, Role.COORDINATOR)

        assert action(client, other, event["id"]).status_code == 404

    @pytest.mark.parametrize("make", [submitted_event, under_review_event])
    @pytest.mark.parametrize("action", [approve, reject])
    def test_there_must_be_a_request_to_answer(self, client, auth_headers, make, action):
        event = make(client, auth_headers)

        response = action(client, auth_headers(COORDINATOR), event["id"])

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "nothing-pending"
        assert response.json()["detail"]["message"] == NOTHING_PENDING_MESSAGE

    def test_a_request_cannot_be_answered_twice(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        approve(client, auth_headers(COORDINATOR), event["id"])

        response = reject(client, auth_headers(COORDINATOR), event["id"])

        assert response.status_code == 409

    def test_a_concurrent_answer_is_reported_as_stale(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = pending_event(client, auth_headers, title="Welcome Night")
        original = event_repository.resolve_change_request

        def another_coordinator_answers_first(event_id, **kwargs):
            original(event_id, **kwargs)
            return original(event_id, **kwargs)

        monkeypatch.setattr(
            event_repository, "resolve_change_request", another_coordinator_answers_first
        )

        response = approve(client, auth_headers(COORDINATOR), event["id"])

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"


class TestReviewBeforeDeciding:
    @pytest.mark.parametrize(
        ("decision", "body"), [("approve", None), ("reject", {"reason": "No."})]
    )
    def test_the_event_cannot_be_decided_while_a_request_is_pending(
        self, client, auth_headers, decision, body
    ):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = client.post(
            f"/events/{event['id']}/{decision}", json=body, headers=auth_headers(COORDINATOR)
        )

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "change-pending"

    def test_the_event_can_be_decided_once_the_request_is_answered(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")
        approve(client, auth_headers(COORDINATOR), event["id"])

        response = client.post(f"/events/{event['id']}/approve", headers=auth_headers(COORDINATOR))

        assert response.status_code == 200
        assert response.json()["status"] == "Approved"
        assert response.json()["title"] == "Welcome Night"


# --- the stores ----------------------------------------------------------------


class TestInMemoryStore:
    def test_answering_with_nothing_pending_is_stale(self):
        store = InMemoryEvents(events=[_event(status=EventStatus.UNDER_REVIEW)])

        with pytest.raises(StaleEventStatus):
            store.resolve_change_request(1, actor_id=COORDINATOR_ID, approve=True, note="")

    def test_answering_after_the_event_moved_on_is_stale(self):
        store = InMemoryEvents(events=[_event(status=EventStatus.COMPLETED, change_requested=True)])

        with pytest.raises(StaleEventStatus):
            store.resolve_change_request(1, actor_id=COORDINATOR_ID, approve=False, note="No")

    def test_requesting_from_a_status_that_changed_is_stale(self):
        store = InMemoryEvents(events=[_event(status=EventStatus.APPROVED)])

        with pytest.raises(StaleEventStatus):
            store.submit_change_request(
                1,
                actor_id=ORGANISER_ID,
                from_status=EventStatus.SUBMITTED,
                changes=(FieldChange("name", "a", "b", False),),
                note="",
            )


class FakeRpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeQuery:
    def __init__(self, admin: "FakeAdmin", table: str) -> None:
        self.admin = admin
        self.table_name = table
        self.filters: list[tuple] = []

    def select(self, _columns):
        return self

    def eq(self, *args):
        self.filters.append(("eq", *args))
        return self

    def neq(self, *args):
        self.filters.append(("neq", *args))
        return self

    def in_(self, *args):
        self.filters.append(("in", *args))
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.admin.queries.append((self.table_name, self.filters))
        return FakeRpc(self.admin.rows.get(self.table_name, []))


class FakeAdmin:
    """Records RPC calls and table reads; answers reads from `rows`."""

    def __init__(self, rpc_result=True, rows: dict[str, list[dict]] | None = None) -> None:
        self.rpc_result = rpc_result
        self.rows = rows or {}
        self.calls: list[tuple[str, dict]] = []
        self.queries: list[tuple[str, list[tuple]]] = []

    def rpc(self, name: str, params: dict):
        self.calls.append((name, params))
        return FakeRpc(self.rpc_result)

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


EVENT_ROW = {
    "id": 42,
    "name": "Faculty Welcome Night",
    "purpose": "Welcome",
    "description": "Talks.",
    "proposed_date": "2027-11-02T18:00:00",
    "end_date": "2027-11-02T21:00:00",
    "expected_attendance": 120,
    "status": "Under Review",
    "organiser_id": ORGANISER_ID,
    "coordinator_id": COORDINATOR_ID,
    "created_at": "2026-09-15T09:00:00",
    "updated_at": "2026-09-15T09:00:00",
    "users": {"name": "Dylan"},
}

PROPOSAL_ROWS = [
    {
        "event_id": 42,
        "changed_field": "expected_attendance",
        "old_value": "120",
        "new_value": "150",
        "change_type": "important",
        "status": "pending",
        "reviewed_at": None,
        "review_note": None,
    },
    {
        "event_id": 42,
        "changed_field": "name",
        "old_value": "Faculty Welcome Night",
        "new_value": None,
        "change_type": "routine",
        "status": "pending",
        "reviewed_at": None,
        "review_note": None,
    },
]


def answered_row(status: str, reviewed_at: str, note: str | None = None) -> dict:
    return {
        "event_id": 42,
        "changed_field": "purpose",
        "old_value": "a",
        "new_value": "b",
        "change_type": "routine",
        "status": status,
        "reviewed_at": reviewed_at,
        "review_note": note,
    }


class TestSupabaseStore:
    def test_a_request_is_one_rpc_carrying_every_change(self, monkeypatch):
        admin = FakeAdmin(True)
        store = SupabaseEvents()
        returned = _event(status=EventStatus.UNDER_REVIEW)
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _event_id: returned)

        result = store.submit_change_request(
            42,
            actor_id=ORGANISER_ID,
            from_status=EventStatus.SUBMITTED,
            changes=(
                FieldChange("name", "Old", "New", False),
                FieldChange("expected_attendance", "120", "150", True),
            ),
            note="Updated numbers.",
        )

        assert result is returned
        assert admin.calls == [
            (
                "us11_review",
                {
                    "p_event_id": 42,
                    "p_action": "submit",
                    "p_revision": 0,
                    "p_actor_id": ORGANISER_ID,
                    "p_payload": {
                        "changes": [
                            {
                                "changed_field": "name",
                                "old_value": "Old",
                                "new_value": "New",
                                "change_type": "routine",
                            },
                            {
                                "changed_field": "expected_attendance",
                                "old_value": "120",
                                "new_value": "150",
                                "change_type": "important",
                            },
                        ],
                        "note": "Updated numbers.",
                    },
                },
            )
        ]

    def test_an_empty_note_is_sent_as_null(self, monkeypatch):
        admin = FakeAdmin(True)
        store = SupabaseEvents()
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _event_id: _event())

        store.submit_change_request(
            42, actor_id=ORGANISER_ID, from_status=EventStatus.SUBMITTED, changes=(), note=""
        )

        assert admin.calls[0][1]["p_payload"]["note"] == ""

    def test_a_failed_compare_and_set_on_request_is_stale(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "admin", lambda: FakeAdmin(False))

        with pytest.raises(StaleEventStatus):
            SupabaseEvents().submit_change_request(
                42, actor_id=ORGANISER_ID, from_status=EventStatus.SUBMITTED, changes=(), note=""
            )

    @pytest.mark.parametrize(("approve_it", "note"), [(True, ""), (False, "No.")])
    def test_an_answer_is_one_rpc(self, monkeypatch, approve_it, note):
        admin = FakeAdmin(True)
        store = SupabaseEvents()
        returned = _event(status=EventStatus.UNDER_REVIEW)
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _event_id: returned)

        result = store.resolve_change_request(
            42, actor_id=COORDINATOR_ID, approve=approve_it, note=note
        )

        assert result is returned
        assert admin.calls == [
            (
                "us11_review",
                {
                    "p_event_id": 42,
                    "p_action": "approve" if approve_it else "reject",
                    "p_revision": 0,
                    "p_actor_id": COORDINATOR_ID,
                    "p_payload": {"note": note},
                },
            )
        ]

    def test_a_failed_compare_and_set_on_answer_is_stale(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "admin", lambda: FakeAdmin(False))

        with pytest.raises(StaleEventStatus):
            SupabaseEvents().resolve_change_request(
                42, actor_id=COORDINATOR_ID, approve=True, note=""
            )

    def test_pending_rows_are_the_request_and_set_the_flag(self, monkeypatch):
        admin = FakeAdmin(rows={"events": [EVENT_ROW], CHANGE_REQUESTS_TABLE: PROPOSAL_ROWS})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        event = SupabaseEvents().get_event(42)

        assert event is not None
        assert event.change_requested is True
        assert event.pending_changes == (
            FieldChange("name", "Faculty Welcome Night", "", False),
            FieldChange("expected_attendance", "120", "150", True),
        )
        assert event.last_change_review is None
        request_query = next(q for q in admin.queries if q[0] == CHANGE_REQUESTS_TABLE)
        assert ("in", "event_id", [42]) in request_query[1]

    def test_an_event_with_no_request_rows_has_no_flag(self, monkeypatch):
        admin = FakeAdmin(rows={"events": [EVENT_ROW]})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        event = SupabaseEvents().get_event(42)

        assert event is not None
        assert event.change_requested is False
        assert event.pending_changes == ()
        assert event.last_change_review is None

    def test_only_answered_rows_is_no_flag_but_a_review(self, monkeypatch):
        admin = FakeAdmin(
            rows={
                "events": [EVENT_ROW],
                CHANGE_REQUESTS_TABLE: [answered_row("rejected", "2026-09-16T09:00:00", "No.")],
            }
        )
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        event = SupabaseEvents().get_event(42)

        assert event is not None
        assert event.change_requested is False
        assert event.last_change_review == ChangeReview("rejected", "2026-09-16T09:00:00", "No.")

    def test_a_list_reads_requests_for_the_whole_page_in_one_query(self, monkeypatch):
        quiet = {**EVENT_ROW, "id": 43}
        admin = FakeAdmin(rows={"events": [EVENT_ROW, quiet], CHANGE_REQUESTS_TABLE: PROPOSAL_ROWS})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        events = SupabaseEvents().list_events(organiser_id=None, include_drafts=False)

        assert [event.change_requested for event in events] == [True, False]
        request_queries = [q for q in admin.queries if q[0] == CHANGE_REQUESTS_TABLE]
        assert len(request_queries) == 1
        assert ("in", "event_id", [42, 43]) in request_queries[0][1]

    def test_an_empty_list_reads_no_requests(self, monkeypatch):
        admin = FakeAdmin(rows={"events": []})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        assert SupabaseEvents().list_events(organiser_id=None, include_drafts=False) == []
        assert all(table != CHANGE_REQUESTS_TABLE for table, _ in admin.queries)

    def test_pending_requests_are_never_read_from_the_change_log(self, monkeypatch):
        # event_changes holds applied changes only; a request must not be looked for there.
        admin = FakeAdmin(rows={"events": [EVENT_ROW], EVENT_CHANGES_TABLE: PROPOSAL_ROWS})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        event = SupabaseEvents().get_event(42)

        assert event is not None
        assert event.pending_changes == ()
        assert all(table != EVENT_CHANGES_TABLE for table, _ in admin.queries)

    def test_an_event_with_no_requests_reads_as_none(self):
        event = to_event(EVENT_ROW)

        assert event.change_requested is False
        assert event.pending_changes == ()
        assert event.last_change_review is None

    def test_the_latest_answer_wins(self):
        review = latest_review(
            [
                answered_row("rejected", "2026-09-16T09:00:00", "First, no."),
                answered_row("approved", "2026-09-18T09:00:00"),
                answered_row("rejected", "2026-09-17T09:00:00", "Second, no."),
                PROPOSAL_ROWS[0],
            ]
        )

        assert review == ChangeReview("approved", "2026-09-18T09:00:00", "")

    def test_a_row_answered_without_a_time_is_ignored(self):
        assert latest_review([answered_row("approved", None)]) is None

    def test_no_rows_means_no_review(self):
        assert latest_review([]) is None

    def test_a_status_change_with_no_note_reads_as_empty(self):
        change = to_change(
            {
                "old_status": "Submitted",
                "new_status": "Under Review",
                "changed_at": "2026-09-15T09:00:00",
                "changed_by_id": ORGANISER_ID,
                "notes": None,
            }
        )

        assert change.notes == ""

    def test_a_proposal_row_with_nulls_reads_as_empty_text(self):
        change = to_field_change(
            {
                "changed_field": "end_date",
                "old_value": None,
                "new_value": None,
                "change_type": "routine",
            }
        )

        assert change == FieldChange("end_date", "", "", False)
