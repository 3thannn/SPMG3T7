"""US5.3: a Confirmed event's details are locked.

Acceptance criteria, and the tests that hold each one:

* Once Confirmed, nobody edits its details directly: refused with "This event
  is confirmed. Changes need to go through a change request." (409) ->
  `TestConfirmedIsLocked`.
* Before Confirmed, US5.2's editing rules are unchanged -> `TestBeforeConfirmed`.
  The team locks Confirmed only (Pending Safety Check still edits).
* The event page hides the editing and points to a change request ->
  frontend/src/pages/EventDetailPage.test.tsx.
* Changes go through US11.1 -> US11.2 -> US11.3 -> `TestTheChangeProcess`
  (and test_reconfirm_us11_3.py).

The story's tests: `test_direct_edit_on_confirmed_is_refused` and
`test_edit_on_planning_is_still_allowed`.
"""

import pytest

from app.event_status import EventStatus
from app.event_store import Event
from app.events import CONFIRMED_EDIT_MESSAGE
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEED_ATTRS, SUBMITTABLE_NEEDS

EVENT_ID = 990
COORDINATOR = "Event Coordinator"
ORGANISER = "Event Organiser"

FORM = {
    "title": "Open House",
    "purpose": "Welcome visitors",
    "description": "Tours and talks.",
    "startsAt": "2099-11-02T09:00",
    "endsAt": "2099-11-02T17:00",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}


def seed(event_repository, status: EventStatus) -> None:
    event_repository.events.append(
        Event(
            id=EVENT_ID,
            title=FORM["title"],
            purpose=FORM["purpose"],
            description=FORM["description"],
            starts_at=FORM["startsAt"],
            ends_at=FORM["endsAt"],
            expected_attendance=FORM["expectedAttendance"],
            status=status,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="2099-01-01T09:00:00",
            updated_at="2099-01-02T12:00:00",
            coordinator_id=COORDINATOR_ID,
            **SUBMITTABLE_NEED_ATTRS,
        )
    )


def edit(client, headers, **changes):
    return client.put(f"/events/{EVENT_ID}", json={**FORM, **changes}, headers=headers)


class TestConfirmedIsLocked:
    def test_direct_edit_on_confirmed_is_refused(self, client, auth_headers, event_repository):
        seed(event_repository, EventStatus.CONFIRMED)

        response = edit(client, auth_headers(COORDINATOR), title="Open House 2099")

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "rule_refused",
            "message": "This event is confirmed. Changes need to go through a change request.",
            "reason": "confirmed-locked",
        }
        assert event_repository.get_event(EVENT_ID).title == "Open House"

    def test_the_organiser_is_refused_the_same_way(self, client, auth_headers, event_repository):
        seed(event_repository, EventStatus.CONFIRMED)

        response = edit(client, auth_headers(ORGANISER), expectedAttendance=35)

        assert response.status_code == 409
        assert response.json()["detail"]["message"] == CONFIRMED_EDIT_MESSAGE
        assert event_repository.get_event(EVENT_ID).expected_attendance == 30

    def test_an_important_field_is_refused_too(self, client, auth_headers, event_repository):
        seed(event_repository, EventStatus.CONFIRMED)

        response = edit(client, auth_headers(COORDINATOR), startsAt="2099-11-02T10:00")

        assert response.status_code == 409
        assert event_repository.get_event(EVENT_ID).starts_at == FORM["startsAt"]


class TestBeforeConfirmed:
    def test_edit_on_planning_is_still_allowed(self, client, auth_headers, event_repository):
        seed(event_repository, EventStatus.PLANNING)

        response = edit(client, auth_headers(COORDINATOR), title="Open House 2099")

        assert response.status_code == 200, response.text
        assert response.json()["title"] == "Open House 2099"

    @pytest.mark.parametrize(
        "status",
        [EventStatus.UNDER_REVIEW, EventStatus.APPROVED, EventStatus.PENDING_SAFETY_CHECK],
    )
    def test_every_earlier_status_still_edits(self, client, auth_headers, event_repository, status):
        """Team decision: only Confirmed locks, as the customer said."""
        seed(event_repository, status)

        response = edit(client, auth_headers(COORDINATOR), description="Tours, talks and lunch.")

        assert response.status_code == 200, response.text
        assert response.json()["description"] == "Tours, talks and lunch."


class TestTheChangeProcess:
    def test_the_organiser_can_still_request_a_change(self, client, auth_headers, event_repository):
        seed(event_repository, EventStatus.CONFIRMED)

        response = client.post(
            f"/events/{EVENT_ID}/change-request",
            json={**FORM, "title": "Open House 2099"},
            headers=auth_headers(ORGANISER),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Confirmed"
        assert [c["field"] for c in response.json()["pendingChanges"]] == ["name"]
