"""US10.3: Leads hear of new submissions, Organisers of confirmation.

Acceptance criteria, and the tests that hold each one:

* Submitting an event notifies every Lead account: "New event waiting for
  assignment: <name>" -> `TestSubmission`.
* The Coordinator confirming the event (US4.7) notifies the Organiser, and
  nobody else -> `test_confirm_event_us4_7.py`, `TestConfirm`.
* An event going back to Planning (US11.3) notifies the Organiser ->
  `test_reconfirm_us11_3.py`, `TestNotices`. US12.4 does not exist yet.
* US10.1's list and read/unread toggle, in-app only -> `TestTheLeadsList`.

The story's tests: `test_submit_with_two_leads_notifies_both` and
`test_nobody_else_is_told`, here and in the US4.7 file.
"""

from app.event_status import EventStatus
from app.permissions import Role
from tests.conftest import COORDINATOR_LEAD_ID, SUBMITTABLE_NEEDS
from tests.test_change_requests import add_user

SECOND_LEAD_ID = 30
LEAD = "Event Coordinator Lead"

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}
MESSAGE = "New event waiting for assignment: Faculty Welcome Night"


def submit(client, auth_headers):
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    return client.post(f"/events/{created.json()['id']}/submit", headers=organiser)


class TestSubmission:
    def test_submit_with_two_leads_notifies_both(
        self, client, auth_headers, user_store, notification_repository
    ):
        add_user(user_store, client, SECOND_LEAD_ID, Role.COORDINATOR_LEAD)

        assert submit(client, auth_headers).status_code == 200

        told = {
            notice.user_id: (notice.kind, notice.status, notice.message)
            for notice in notification_repository.notifications
        }
        notice = ("event-status", EventStatus.SUBMITTED, MESSAGE)
        assert told == {COORDINATOR_LEAD_ID: notice, SECOND_LEAD_ID: notice}


    def test_a_draft_saved_but_not_submitted_tells_nobody(
        self, client, auth_headers, notification_repository
    ):
        client.post("/events", json=DRAFT, headers=auth_headers("Event Organiser"))

        assert notification_repository.notifications == []





