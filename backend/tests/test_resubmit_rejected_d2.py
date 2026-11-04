"""D2 (CODE_AUDIT.md): a Rejected event can be revised and resubmitted.

Week 4 customer answers: "Rejected events may be resubmitted after appropriate
changes are made; rejection is not necessarily final." The Week 4 project
instructions list Rejected among the statuses without making it final, so the
answer stands. The owning Organiser edits the Rejected event and submits it
again; it goes back to the Leads' unassigned queue like any new submission.
"""

from tests.conftest import COORDINATOR_LEAD_ID
from tests.test_notifications import DRAFT, under_review_event

ORGANISER = "Event Organiser"


def rejected_event(client, auth_headers) -> str:
    event_id = under_review_event(client, auth_headers)
    rejected = client.post(
        f"/events/{event_id}/reject",
        json={"reason": "The hall is booked that week."},
        headers=auth_headers("Event Coordinator"),
    )
    assert rejected.status_code == 200, rejected.text
    return event_id


def test_the_organiser_revises_a_rejected_event(client, auth_headers):
    event_id = rejected_event(client, auth_headers)

    saved = client.put(
        f"/events/{event_id}",
        json={**DRAFT, "startsAt": "2027-11-09T18:00", "endsAt": "2027-11-09T21:00"},
        headers=auth_headers(ORGANISER),
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "Rejected"
    assert saved.json()["startsAt"] == "2027-11-09T18:00"


def test_resubmitting_returns_it_to_the_leads_queue(
    client, auth_headers, notification_repository
):
    event_id = rejected_event(client, auth_headers)

    resubmitted = client.post(f"/events/{event_id}/submit", headers=auth_headers(ORGANISER))

    assert resubmitted.status_code == 200, resubmitted.text
    body = resubmitted.json()
    assert body["status"] == "Submitted"
    assert body["coordinatorId"] in (None, "")
    last = body["history"][-1]
    assert (last["from"], last["to"]) == ("Rejected", "Submitted")
    queue = client.get("/events/unassigned", headers=auth_headers("Event Coordinator Lead"))
    assert event_id in [event["id"] for event in queue.json()]
    assert any(
        notice.user_id == COORDINATOR_LEAD_ID and notice.event_id == int(event_id)
        for notice in notification_repository.notifications
        if notice.kind == "event-status" and str(notice.status) == "Submitted"
    )


def test_a_resubmission_must_still_be_complete(client, auth_headers):
    event_id = rejected_event(client, auth_headers)
    client.put(
        f"/events/{event_id}", json={**DRAFT, "description": ""}, headers=auth_headers(ORGANISER)
    )

    response = client.post(f"/events/{event_id}/submit", headers=auth_headers(ORGANISER))

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Give the event a description."


def test_only_the_owner_resubmits(client, auth_headers):
    event_id = rejected_event(client, auth_headers)

    response = client.post(
        f"/events/{event_id}/submit", headers=auth_headers("Event Coordinator")
    )

    assert response.status_code == 403
