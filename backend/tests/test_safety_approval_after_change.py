"""An important change during the safety check sends the event back to Planning.

Found by the code audit (CODE_AUDIT.md, D1): the Safety Officer approved an event
for 50 people, the Coordinator then edited the attendance to 90 and confirmed it.
The event became Confirmed on an approval for different numbers.

The rule these tests hold, from the customer's own answers:

* The Coordinator may still change an event before it is Confirmed (Week 9:
  "The co-ordinator can make changes before the final confirmed status").
* But the Safety Officer must approve before confirmation (Week 7 change #6), and
  a date, time or attendance change needs every check again (Week 9).
* So an important change (US5.2's rule: date, time, attendance, venue or
  equipment) made while the event is Pending Safety Check sends it back to
  Planning, as US11.3 already does for a Confirmed event. It then needs a fresh
  safety check and a fresh decision before the Coordinator can confirm it.
* A routine change, such as the title, leaves the event and its approval alone.

The SQL half is SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql.
"""

import pytest

from app.change_requests import FieldChange, reopens_planning
from app.event_status import EventStatus
from tests.conftest import ORGANISER_ID, SUBMITTABLE_NEEDS
from tests.test_confirm_event_us4_7 import (
    COORDINATOR,
    EVENT_ID,
    approve,
    confirm,
    waiting,  # noqa: F401 - used through usefixtures
)

PSC = EventStatus.PENDING_SAFETY_CHECK
ORGANISER = "Event Organiser"

#: The event `waiting` seeds, as the edit form sends it.
FORM = {
    "title": "Open House",
    "purpose": "Welcome visitors",
    "description": "Tours and talks.",
    "startsAt": "2099-11-02T09:00",
    "endsAt": "2099-11-02T17:00",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}


def edit(client, auth_headers, **changes):
    response = client.put(
        f"/events/{EVENT_ID}", json={**FORM, **changes}, headers=auth_headers(COORDINATOR)
    )
    assert response.status_code == 200, response.text
    return response.json()


def change_request(client, auth_headers, **changes):
    proposed = client.post(
        f"/events/{EVENT_ID}/change-request",
        json={**FORM, **changes, "note": "Numbers changed."},
        headers=auth_headers(ORGANISER),
    )
    assert proposed.status_code == 200, proposed.text
    accepted = client.post(
        f"/events/{EVENT_ID}/change-request/approve", headers=auth_headers(COORDINATOR)
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


class TestTheRule:
    def test_an_important_change_during_the_safety_check_reopens_planning(self):
        attendance = FieldChange("expected_attendance", "30", "40", important=True)

        assert reopens_planning(status=PSC, changes=[attendance]) is True

    def test_a_routine_change_during_the_safety_check_does_not(self):
        title = FieldChange("name", "Open House", "Open Day", important=False)

        assert reopens_planning(status=PSC, changes=[title]) is False

    def test_planning_is_unchanged_the_checks_are_still_to_come(self):
        attendance = FieldChange("expected_attendance", "30", "40", important=True)

        assert reopens_planning(status=EventStatus.PLANNING, changes=[attendance]) is False


@pytest.mark.usefixtures("waiting")
class TestDirectEditAfterSafetyApproval:
    def test_an_attendance_edit_sends_the_event_back_to_planning(self, client, auth_headers):
        approve(client, auth_headers)

        edited = edit(client, auth_headers, expectedAttendance=40)

        assert edited["status"] == "Planning"
        last = edited["history"][-1]
        assert (last["from"], last["to"]) == ("Pending Safety Check", "Planning")
        assert "attendance" in last["notes"].lower()

    def test_the_old_approval_can_no_longer_confirm_it(self, client, auth_headers):
        approve(client, auth_headers)
        edit(client, auth_headers, expectedAttendance=40)

        response = confirm(client, auth_headers(COORDINATOR))

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-pending-safety-check"

    def test_a_date_edit_before_any_decision_also_goes_back(self, client, auth_headers):
        """The Safety Officer must not review numbers that have since changed."""
        edited = edit(client, auth_headers, startsAt="2099-11-03T09:00", endsAt="2099-11-03T17:00")

        assert edited["status"] == "Planning"

    def test_a_title_edit_keeps_the_approval(self, client, auth_headers):
        approve(client, auth_headers)

        edited = edit(client, auth_headers, title="Open Day")

        assert edited["status"] == "Pending Safety Check"
        assert confirm(client, auth_headers(COORDINATOR)).json()["status"] == "Confirmed"

    def test_the_organiser_is_told_it_is_back_in_planning(
        self, client, auth_headers, notification_repository
    ):
        approve(client, auth_headers)

        edit(client, auth_headers, expectedAttendance=40)

        kinds = {(n.user_id, n.kind) for n in notification_repository.notifications}
        assert (ORGANISER_ID, "back-in-planning") in kinds


@pytest.mark.usefixtures("waiting")
class TestChangeRequestDuringSafetyCheck:
    def test_accepting_an_attendance_change_sends_it_back_to_planning(self, client, auth_headers):
        approve(client, auth_headers)

        accepted = change_request(client, auth_headers, expectedAttendance=40)

        assert accepted["status"] == "Planning"
        last = accepted["history"][-1]
        assert (last["from"], last["to"]) == ("Pending Safety Check", "Planning")

    def test_accepting_a_title_change_keeps_it_pending(self, client, auth_headers):
        approve(client, auth_headers)

        accepted = change_request(client, auth_headers, title="Open Day")

        assert accepted["status"] == "Pending Safety Check"
