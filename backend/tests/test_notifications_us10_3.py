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

from app import users
from tests.conftest import SUBMITTABLE_NEEDS

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




    def test_a_failed_notice_does_not_fail_the_submission(
        self, client, auth_headers, notification_repository, monkeypatch
    ):
        def broken(**_kwargs):
            raise RuntimeError("notifications table missing")

        monkeypatch.setattr(notification_repository, "create", broken)

        submitted = submit(client, auth_headers)

        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "Submitted"

    def test_an_unreadable_directory_does_not_fail_the_submission(
        self, client, auth_headers, notification_repository, monkeypatch
    ):
        organiser = auth_headers("Event Organiser")
        created = client.post("/events", json=DRAFT, headers=organiser)

        def unreachable():
            raise RuntimeError("users table unreachable")

        monkeypatch.setattr(users, "list_users", unreachable)
        submitted = client.post(f"/events/{created.json()['id']}/submit", headers=organiser)

        assert submitted.status_code == 200, submitted.text
        assert notification_repository.notifications == []


class TestTheLeadsList:
    def test_the_lead_reads_it_and_marks_it_read(self, client, auth_headers):
        submit(client, auth_headers)
        lead = auth_headers(LEAD)

        [notice] = client.get("/notifications", headers=lead).json()
        assert (notice["status"], notice["message"], notice["read"]) == (
            "Submitted",
            MESSAGE,
            False,
        )
        assert notice["eventTitle"] == "Faculty Welcome Night"

        marked = client.patch(f"/notifications/{notice['id']}", json={"read": True}, headers=lead)
        assert marked.status_code == 200, marked.text
        assert marked.json()["read"] is True

        unmarked = client.patch(
            f"/notifications/{notice['id']}", json={"read": False}, headers=lead
        )
        assert unmarked.json()["read"] is False

