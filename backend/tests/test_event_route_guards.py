"""Event route refusals the story tests do not reach — US4.2, US5.2, US7.1, US8.3, US8.4.

Three kinds of path live here:

* Requests that are simply wrong: an event that does not exist, a coordinator
  id that is not a number, a date that is not a date.
* Races: the store refuses a write because the event moved between the route
  reading it and the store writing it. The route must answer 409, not 500.
* Checks the routes repeat on stored data. Submission re-validates dates even
  though saving already did, so a bad row written some other way is still
  refused. Those are tested on the helper, since no request can create one.
"""

from dataclasses import replace
from datetime import date

import pytest
from fastapi import HTTPException

from app import events
from app.event_status import (
    CompletionRefusal,
    EventStatus,
    SubmitRefusal,
    check_completion,
    check_submit,
)
from app.event_store import StaleEventStatus, to_change
from app.events import _today as real_today
from tests.conftest import COORDINATOR_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}


def create(client, headers, **overrides) -> dict:
    response = client.post("/events", json={**DRAFT, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def submitted(client, auth_headers) -> dict:
    organiser = auth_headers("Event Organiser")
    event = create(client, organiser)
    response = client.post(f"/events/{event['id']}/submit", headers=organiser)
    assert response.status_code == 200, response.text
    return response.json()


def assigned(client, auth_headers) -> dict:
    event = submitted(client, auth_headers)
    response = client.post(
        f"/events/{event['id']}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert response.status_code == 200, response.text
    return response.json()


def stale(*_args, **_kwargs):
    raise StaleEventStatus


def message(response) -> str:
    return response.json()["detail"]["message"]


class TestDates:
    def test_a_draft_whose_dates_are_not_dates_is_refused(self, client, auth_headers):
        response = client.post(
            "/events",
            json={**DRAFT, "startsAt": "next Tuesday", "endsAt": "after lunch"},
            headers=auth_headers(),
        )

        assert response.status_code == 400
        assert message(response) == "Give the event a valid date."

    def test_today_comes_from_the_clock_outside_the_suite(self):
        assert real_today() == date.today()

    @pytest.mark.parametrize(
        ("ends_at", "expected"),
        [
            ("2027-11-02T25:00", "Give the event a valid date."),
            ("2027-11-02T17:00", "The end date must be after the start date."),
        ],
        ids=["end-not-a-time", "end-before-start"],
    )
    def test_submission_rechecks_the_stored_end(
        self, client, auth_headers, event_repository, ends_at, expected
    ):
        event = create(client, auth_headers())
        stored = replace(event_repository.get_event(int(event["id"])), ends_at=ends_at)

        with pytest.raises(HTTPException) as refused:
            events._validate_submission(stored)

        assert refused.value.detail["message"] == expected


class TestAssigning:
    def lead(self, auth_headers):
        return auth_headers("Event Coordinator Lead")

    def test_assigning_a_missing_event_is_not_found(self, client, auth_headers):
        response = client.post(
            "/events/999/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=self.lead(auth_headers),
        )

        assert response.status_code == 404

    def test_a_draft_cannot_be_assigned(self, client, auth_headers):
        draft = create(client, auth_headers())

        response = client.post(
            f"/events/{draft['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=self.lead(auth_headers),
        )

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"

    def test_a_coordinator_id_must_be_a_number(self, client, auth_headers):
        event = submitted(client, auth_headers)

        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": "Priya"},
            headers=self.lead(auth_headers),
        )

        assert response.status_code == 400
        assert message(response) == "The coordinator ID must be a valid number."

    def test_an_assignment_that_lost_a_race_is_a_conflict(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = submitted(client, auth_headers)
        monkeypatch.setattr(event_repository, "assign_coordinator", stale)

        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=self.lead(auth_headers),
        )

        assert response.status_code == 409

    def test_reassigning_needs_a_numeric_coordinator_id_too(self, client, auth_headers):
        event = assigned(client, auth_headers)

        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "Priya"},
            headers=self.lead(auth_headers),
        )

        assert response.status_code == 400
        assert message(response) == "The coordinator ID must be a valid number."


class TestEditing:
    def test_someone_who_can_read_an_event_but_neither_owns_nor_coordinates_it_cannot_edit(
        self, client, auth_headers, event_repository
    ):
        """The Safety Officer reads events waiting for their check (US4.4), nothing more."""
        event = submitted(client, auth_headers)
        stored = event_repository.get_event(int(event["id"]))
        event_repository._replace(replace(stored, status=EventStatus.PENDING_SAFETY_CHECK))

        response = client.put(
            f"/events/{event['id']}", json=DRAFT, headers=auth_headers("Safety Officer")
        )

        assert response.status_code == 403
        assert message(response) == (
            "Only the Organiser who owns this event or a Coordinator can edit it."
        )


class TestDeciding:
    def test_a_decision_that_lost_a_race_is_a_conflict(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = assigned(client, auth_headers)
        monkeypatch.setattr(event_repository, "decide_event", stale)

        response = client.post(
            f"/events/{event['id']}/approve", headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 409


class TestStatusRules:
    def test_only_the_owner_may_submit(self):
        refusal = check_submit(status=EventStatus.DRAFT, organiser_id=1, actor_id=2)

        assert refusal is SubmitRefusal.NOT_OWNER

    def test_an_end_time_with_a_timezone_cannot_be_compared(self):
        """Event times are naive Singapore times; an offset means it came from elsewhere."""
        refusal = check_completion("2026-11-02T18:00:00+08:00")

        assert refusal is CompletionRefusal.INVALID_END_TIME

    def test_completing_an_event_that_has_not_ended_is_stale_in_the_store(
        self, client, auth_headers, event_repository
    ):
        event = assigned(client, auth_headers)
        stored = event_repository.get_event(int(event["id"]))
        event_repository._replace(replace(stored, status=EventStatus.CONFIRMED))

        with pytest.raises(StaleEventStatus):
            event_repository.complete_event(int(event["id"]), actor_id=COORDINATOR_ID)


@pytest.mark.parametrize(
    ("joined", "name"),
    [([{"name": "Dylan"}], "Dylan"), ([], "")],
    ids=["one-row-list", "empty-list"],
)
def test_an_audit_row_reads_its_author_whichever_shape_postgrest_sends(joined, name):
    row = {
        "old_status": "Draft",
        "new_status": "Submitted",
        "changed_at": "2026-10-01T09:00:00",
        "changed_by_id": 1,
        "users": joined,
    }

    assert to_change(row).by_name == name
