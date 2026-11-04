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
    IMPORTANT_FIELDS,
    ChangeRequestRefusal,
    FieldChange,
    is_important,
    reopen_reason,
)
from app.event_status import EventStatus
from app.event_store import (
    CHANGE_REQUESTS_TABLE,
    Event,
    SupabaseEvents,
)
from app.events import PURPOSE_MAX, TITLE_MAX
from app.permissions import Role
from app.users import User
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    PASSWORD,
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
























# --- AC1/AC2: proposing changes --------------------------------------------------


class TestProposing:


    def test_the_change_requested_flag_is_set(self, client, auth_headers):
        event = pending_event(client, auth_headers, title="Welcome Night")

        assert event["changeRequested"] is True

    def test_the_event_itself_is_not_edited(self, client, auth_headers):
        # The point of the story: reviewed, not applied.
        event = pending_event(client, auth_headers, title="Welcome Night", expectedAttendance=200)

        assert event["title"] == DRAFT["title"]
        assert event["expectedAttendance"] == DRAFT["expectedAttendance"]


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













class TestWhoMayPropose:



    def test_another_organiser_is_told_the_event_does_not_exist(
        self, client, auth_headers, user_store
    ):
        event = submitted_event(client, auth_headers)
        other = add_user(user_store, client, OTHER_ORGANISER_ID, Role.ORGANISER)

        response = propose(client, other, event["id"], title="New")

        assert response.status_code == 404



class TestWhenAProposalIsRefused:


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
                "startsAt": f"{TODAY.isoformat()}T23:00",
                "endsAt": f"{TODAY.isoformat()}T23:59",
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



    def test_an_unassigned_coordinator_cannot_see_it(self, client, auth_headers, user_store):
        event = pending_event(client, auth_headers, title="Welcome Night")
        other = add_user(user_store, client, OTHER_COORDINATOR_ID, Role.COORDINATOR)

        assert client.get(f"/events/{event['id']}", headers=other).status_code == 404
        assert client.get("/events", headers=other).json() == []


# --- AC4: important changes ------------------------------------------------------


class TestImportance:


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



    def test_the_organiser_is_notified_of_the_acceptance(
        self, client, auth_headers, notification_repository
    ):
        """US11.2 AC2: accepting notifies the Organiser, and only them.

        The proposal renamed the event, so the notice already uses the new name.
        """
        event = pending_event(client, auth_headers, title="Welcome Night")
        approve(client, auth_headers(COORDINATOR), event["id"])

        told = [
            (notice.user_id, notice.message)
            for notice in notification_repository.notifications
            if notice.kind == "change-accepted"
        ]
        assert told == [(ORGANISER_ID, 'The change request for "Welcome Night" was accepted.')]







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


    def test_the_organiser_is_notified_of_the_rejection_and_why(
        self, client, auth_headers, notification_repository
    ):
        """US11.2 AC3: rejecting notifies the Organiser with the trimmed reason."""
        event = pending_event(client, auth_headers, title="Welcome Night")
        reject(client, auth_headers(COORDINATOR), event["id"], "  Keep the original name.  ")

        told = [
            (notice.user_id, notice.message)
            for notice in notification_repository.notifications
            if notice.kind == "change-rejected"
        ]
        assert told == [
            (
                ORGANISER_ID,
                'The change request for "Faculty Welcome Night" was rejected. '
                "Reason: Keep the original name.",
            )
        ]


    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_reason_is_required(self, client, auth_headers, reason):
        event = pending_event(client, auth_headers, title="Welcome Night")

        response = reject(client, auth_headers(COORDINATOR), event["id"], reason)

        assert response.status_code == 400
        still = client.get(f"/events/{event['id']}", headers=auth_headers(COORDINATOR)).json()
        assert still["changeRequested"] is True








# --- the stores ----------------------------------------------------------------




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




    def test_an_approval_is_one_rpc_carrying_the_us11_3_reason(self, monkeypatch):
        """US11.3: the database decides whether the event goes back to Planning;
        the API sends the words its history entry would carry."""
        admin = FakeAdmin(True)
        store = SupabaseEvents()
        attendance = FieldChange("expected_attendance", "50", "75", important=True)
        returned = _event(status=EventStatus.CONFIRMED, pending_changes=(attendance,))
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _event_id: returned)

        result = store.resolve_change_request(42, actor_id=COORDINATOR_ID, approve=True, note="")

        assert result is returned
        assert admin.calls == [
            (
                "us11_approve_change",
                {
                    "p_event_id": 42,
                    "p_revision": 0,
                    "p_actor_id": COORDINATOR_ID,
                    "p_payload": {"note": ""},
                    "p_reason": reopen_reason((attendance,)),
                },
            )
        ]






    def test_an_empty_list_reads_no_requests(self, monkeypatch):
        admin = FakeAdmin(rows={"events": []})
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        assert SupabaseEvents().list_events(organiser_id=None, include_drafts=False) == []
        assert all(table != CHANGE_REQUESTS_TABLE for table, _ in admin.queries)

