"""The event request endpoint — Event Request Creation.

`POST /event-requests` is the whole story: an Event Organiser fills in a
complete proposal and it is submitted in one step, with a row written to
`events`. These tests assert it against a request rather than against a form,
for the reason the rest of the suite gives — a browser check is a courtesy and
a refused request is the rule.

`test_event_request_rules.py` pins the rules down one at a time. This file
covers the route: who may call it, what comes back, what is actually stored,
and that a refusal arrives in the envelope the form knows how to read.
"""

from datetime import date, timedelta

from app.event_status import EventStatus
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

#: Far enough ahead that the "not in the past" rule never trips on it, whenever
#: the suite runs. The one test that cares about today computes its own.
FUTURE = (date.today() + timedelta(days=60)).isoformat()

REQUEST = {
    "name": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks, then supper.",
    "proposedDate": FUTURE,
    "startTime": "18:00",
    "endTime": "21:30",
    "expectedAttendance": 120,
}


def submit(client, headers, **overrides):
    """POST a request with some fields swapped out, and return the response."""
    return client.post(
        "/event-requests", json={**REQUEST, **overrides}, headers=headers
    )


def created(client, headers, **overrides) -> dict:
    """Submit a request and return the event, failing the test if that broke."""
    response = submit(client, headers, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


class TestSubmittingARequest:
    def test_it_is_submitted_rather_than_left_as_a_draft(self, client, auth_headers):
        """The point of the story: no second step, no draft to come back to."""
        event = created(client, auth_headers("Event Organiser"))

        assert event["status"] == EventStatus.SUBMITTED

    def test_it_answers_201_with_the_created_event(self, client, auth_headers):
        response = submit(client, auth_headers("Event Organiser"))

        assert response.status_code == 201
        assert response.json()["id"]

    def test_every_field_comes_back(self, client, auth_headers):
        event = created(client, auth_headers())

        assert event["title"] == "Faculty Welcome Night"
        assert event["purpose"] == "Welcome the new intake."
        assert event["description"] == "Talks, then supper."
        assert event["expectedAttendance"] == 120

    def test_the_date_and_times_are_stored_as_two_timestamps(self, client, auth_headers):
        """The form asks three questions; `events` answers with two columns."""
        event = created(client, auth_headers())

        assert event["startsAt"] == f"{FUTURE}T18:00"
        assert event["endsAt"] == f"{FUTURE}T21:30"

    def test_the_organiser_is_taken_from_the_session(self, client, auth_headers):
        """Otherwise an Organiser could file a request under someone else's name."""
        event = created(client, auth_headers(), organiserId="999", organiser_id=999)

        assert event["organiserId"] == str(ORGANISER_ID)
        assert event["organiserName"] == "Dylan"

    def test_the_description_may_be_left_out_entirely(self, client, auth_headers):
        """Five fields are required; description is not one of them."""
        body = {key: value for key, value in REQUEST.items() if key != "description"}
        response = client.post("/event-requests", json=body, headers=auth_headers())

        assert response.status_code == 201, response.text
        assert response.json()["description"] == ""


class TestTheRowThatIsWritten:
    def test_a_row_is_written_to_the_events_table(
        self, client, auth_headers, event_repository
    ):
        """"Row written to events table on success" — asserted against the store."""
        assert event_repository.events == []

        created(client, auth_headers())

        assert len(event_repository.events) == 1

    def test_the_stored_row_holds_what_was_submitted(
        self, client, auth_headers, event_repository
    ):
        created(client, auth_headers())
        stored = event_repository.events[0]

        assert stored.title == "Faculty Welcome Night"
        assert stored.purpose == "Welcome the new intake."
        assert stored.starts_at == f"{FUTURE}T18:00"
        assert stored.ends_at == f"{FUTURE}T21:30"
        assert stored.expected_attendance == 120
        assert stored.status is EventStatus.SUBMITTED
        assert stored.organiser_id == ORGANISER_ID

    def test_no_row_is_written_when_the_request_is_refused(
        self, client, auth_headers, event_repository
    ):
        """A rejected request must leave nothing behind to clean up."""
        response = submit(client, auth_headers(), name="")

        assert response.status_code == 400
        assert event_repository.events == []

    def test_the_history_records_the_submission(self, client, auth_headers):
        """`status_changes.old_status` is NOT NULL, so the trail reads Draft -> Submitted."""
        event = created(client, auth_headers())

        assert [entry["to"] for entry in event["history"]] == ["Draft", "Submitted"]

    def test_the_submission_is_attributed_to_the_organiser(self, client, auth_headers):
        event = created(client, auth_headers())
        submission = event["history"][-1]

        assert submission["from"] == "Draft"
        assert submission["byId"] == str(ORGANISER_ID)
        assert submission["byName"] == "Dylan"

    def test_the_request_appears_in_the_organisers_own_event_list(
        self, client, auth_headers
    ):
        """US4.1 still owns the list; a request is an event like any other."""
        created(client, auth_headers())
        listed = client.get("/events", headers=auth_headers()).json()

        assert [event["title"] for event in listed] == ["Faculty Welcome Night"]
        assert listed[0]["status"] == EventStatus.SUBMITTED

    def test_the_request_can_be_read_back_on_its_own(self, client, auth_headers):
        event = created(client, auth_headers())
        fetched = client.get(f"/events/{event['id']}", headers=auth_headers())

        assert fetched.status_code == 200
        assert fetched.json()["endsAt"] == f"{FUTURE}T21:30"


class TestWhoMaySubmitOne:
    def test_an_organiser_may(self, client, auth_headers):
        assert submit(client, auth_headers("Event Organiser")).status_code == 201

    def test_a_coordinator_may_not(self, client, auth_headers):
        """Coordinators review events; they do not raise them (US1.3)."""
        response = submit(client, auth_headers("Event Coordinator"))

        assert response.status_code == 403
        assert "create events" in response.json()["detail"]["message"]

    def test_a_request_without_a_session_is_refused(self, client):
        response = client.post("/event-requests", json=REQUEST)

        assert response.status_code == 401

    def test_a_request_with_a_bad_token_is_refused(self, client):
        response = client.post(
            "/event-requests", json=REQUEST, headers={"Authorization": "Bearer nope"}
        )

        assert response.status_code == 401


class TestRefusals:
    def test_a_refusal_carries_a_code_a_client_can_branch_on(self, client, auth_headers):
        detail = submit(client, auth_headers(), name="").json()["detail"]

        assert detail["code"] == "invalid_event_request"

    def test_a_refusal_names_the_field_so_the_form_can_place_it(
        self, client, auth_headers
    ):
        detail = submit(client, auth_headers(), endTime="17:00").json()["detail"]

        assert detail["field"] == "endTime"
        assert detail["message"] == "The end time must be after the start time."

    def test_a_missing_name_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), name="   ")

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give the event a name."

    def test_a_missing_purpose_is_refused(self, client, auth_headers):
        """Optional for a US4.2 draft, required for a request."""
        response = submit(client, auth_headers(), purpose="")

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "purpose"

    def test_a_missing_date_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), proposedDate="")

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "proposedDate"

    def test_a_missing_start_time_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), startTime="")

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "startTime"

    def test_a_missing_end_time_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), endTime="")

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "endTime"

    def test_a_missing_attendance_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), expectedAttendance=None)

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "expectedAttendance"

    def test_an_attendance_of_zero_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), expectedAttendance=0)

        assert response.status_code == 400
        assert "at least 1" in response.json()["detail"]["message"]

    def test_a_negative_attendance_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), expectedAttendance=-5)

        assert response.status_code == 400

    def test_an_attendance_that_is_not_a_number_is_refused(self, client, auth_headers):
        """`Any` on the model means this is our sentence, not a Pydantic 422."""
        response = submit(client, auth_headers(), expectedAttendance="lots")

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Expected attendance must be a whole number."
        )

    def test_an_attendance_sent_as_a_string_of_digits_is_accepted(
        self, client, auth_headers
    ):
        """An HTML form posts strings; that should not be a rejection."""
        event = created(client, auth_headers(), expectedAttendance="45")

        assert event["expectedAttendance"] == 45

    def test_a_date_in_the_past_is_refused(self, client, auth_headers):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = submit(client, auth_headers(), proposedDate=yesterday)

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "The proposed date cannot be in the past."
        )

    def test_today_is_not_in_the_past(self, client, auth_headers):
        event = created(client, auth_headers(), proposedDate=date.today().isoformat())

        assert event["startsAt"].startswith(date.today().isoformat())

    def test_an_end_time_equal_to_the_start_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), startTime="18:00", endTime="18:00")

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "endTime"

    def test_a_name_longer_than_the_column_is_refused(self, client, auth_headers):
        response = submit(client, auth_headers(), name="x" * 256)

        assert response.status_code == 400
        assert "255 characters" in response.json()["detail"]["message"]

    def test_an_empty_body_is_refused_with_the_first_missing_field(
        self, client, auth_headers
    ):
        """Every field defaults, so nothing at all reads as "the name is blank"."""
        response = client.post("/event-requests", json={}, headers=auth_headers())

        assert response.status_code == 400
        assert response.json()["detail"]["field"] == "name"


class TestItLeavesTheDraftFlowAlone:
    """The story adds a path; it does not take one away."""

    def test_the_draft_endpoint_still_creates_drafts(self, client, auth_headers):
        response = client.post(
            "/events",
            json={"title": "Still a draft", "startsAt": f"{FUTURE}T18:00"},
            headers=auth_headers(),
        )

        assert response.status_code == 201
        assert response.json()["status"] == EventStatus.DRAFT

    def test_a_draft_has_no_end_time(self, client, auth_headers):
        """`end_date` is only asked for by a request, so a draft leaves it empty."""
        response = client.post(
            "/events",
            json={"title": "Still a draft", "startsAt": f"{FUTURE}T18:00"},
            headers=auth_headers(),
        )

        assert response.json()["endsAt"] == ""

    def test_a_coordinator_sees_a_submitted_request_in_their_list(
        self, client, auth_headers
    ):
        """US4.1's Coordinator view, unchanged and now with a request in it."""
        created(client, auth_headers("Event Organiser"))
        listed = client.get("/events", headers=auth_headers("Event Coordinator")).json()

        assert len(listed) == 1
        assert listed[0]["organiserId"] == str(ORGANISER_ID)
        assert listed[0]["organiserId"] != str(COORDINATOR_ID)
