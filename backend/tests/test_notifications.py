"""US10.1: Organisers are notified of status changes and can manage read state.

Test case ids (TC-N…) match the US10.1 test report.
"""


from app.event_status import EventStatus
from app.notification_store import Notification
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}


def submitted_event(client, auth_headers) -> str:
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text
    return event_id


def ask(client, auth_headers, event_id: str, message: str = "Please confirm catering."):
    response = client.post(
        f"/events/{event_id}/clarification",
        json={"message": message},
        headers=auth_headers("Event Coordinator"),
    )
    assert response.status_code == 200, response.text
    return response


def assigned_event(client, auth_headers) -> str:
    """US8.3: assigning a Coordinator moves the event to Under Review."""
    event_id = submitted_event(client, auth_headers)
    assigned = client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert assigned.status_code == 200, assigned.text
    return event_id


def under_review_event(client, auth_headers) -> str:
    event_id = assigned_event(client, auth_headers)
    ask(client, auth_headers, event_id)
    return event_id


def notices(client, auth_headers) -> list[dict]:
    response = client.get("/notifications", headers=auth_headers("Event Organiser"))
    assert response.status_code == 200, response.text
    return response.json()


def stored(notification_id: int, user_id: int, created_at: str, *, is_read=False) -> Notification:
    return Notification(
        id=notification_id,
        user_id=user_id,
        event_id=1,
        status=EventStatus.APPROVED,
        message=f"notice {notification_id}",
        is_read=is_read,
        created_at=created_at,
    )


class TestNotificationIsCreated:
    def test_tc_n01_approval_notifies_the_organiser(self, client, auth_headers):
        event_id = under_review_event(client, auth_headers)
        approved = client.post(
            f"/events/{event_id}/approve", headers=auth_headers("Event Coordinator")
        )
        assert approved.status_code == 200, approved.text

        latest = notices(client, auth_headers)[0]
        assert latest["eventId"] == event_id
        assert latest["eventTitle"] == "Faculty Welcome Night"
        assert latest["status"] == "Approved"
        assert latest["message"] == '"Faculty Welcome Night" was approved.'
        assert latest["read"] is False
        assert latest["readAt"] == ""

    def test_tc_n02_rejection_notifies_with_the_reason(self, client, auth_headers):
        event_id = under_review_event(client, auth_headers)
        rejected = client.post(
            f"/events/{event_id}/reject",
            json={"reason": "The hall is booked that week."},
            headers=auth_headers("Event Coordinator"),
        )
        assert rejected.status_code == 200, rejected.text

        latest = notices(client, auth_headers)[0]
        assert latest["status"] == "Rejected"
        assert "The hall is booked that week." in latest["message"]

    def test_tc_n03_assignment_moves_under_review_and_notifies(self, client, auth_headers):
        assigned_event(client, auth_headers)

        [notice] = notices(client, auth_headers)
        assert notice["status"] == "Under Review"
        assert notice["message"] == '"Faculty Welcome Night" is under review.'



    def test_tc_n06_a_refused_decision_does_not_notify(self, client, auth_headers):
        event_id = under_review_event(client, auth_headers)
        coordinator = auth_headers("Event Coordinator")
        client.post(f"/events/{event_id}/approve", headers=coordinator)
        before = notices(client, auth_headers)

        refused = client.post(f"/events/{event_id}/approve", headers=coordinator)
        assert refused.status_code == 409
        assert notices(client, auth_headers) == before

    def test_tc_n07_a_failed_notice_does_not_fail_the_decision(
        self, client, auth_headers, notification_repository, monkeypatch
    ):
        event_id = under_review_event(client, auth_headers)

        def broken(**_kwargs):
            raise RuntimeError("notifications table missing")

        monkeypatch.setattr(notification_repository, "create", broken)
        approved = client.post(
            f"/events/{event_id}/approve", headers=auth_headers("Event Coordinator")
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "Approved"



class TestListAndReadState:
    def test_tc_n09_unread_come_first_then_newest(
        self, client, auth_headers, notification_repository
    ):
        notification_repository.notifications = [
            stored(1, ORGANISER_ID, "2026-10-01T09:00:00"),
            stored(2, ORGANISER_ID, "2026-10-02T09:00:00", is_read=True),
            stored(3, ORGANISER_ID, "2026-10-03T09:00:00"),
            stored(4, ORGANISER_ID, "2026-09-30T09:00:00", is_read=True),
        ]
        assert [item["id"] for item in notices(client, auth_headers)] == ["3", "1", "2", "4"]


    def test_tc_n11_mark_read_then_unread(self, client, auth_headers):
        under_review_event(client, auth_headers)
        organiser = auth_headers("Event Organiser")
        notice_id = notices(client, auth_headers)[0]["id"]

        read = client.patch(f"/notifications/{notice_id}", json={"read": True}, headers=organiser)
        assert read.status_code == 200, read.text
        assert read.json()["read"] is True
        assert read.json()["readAt"] != ""

        unread = client.patch(
            f"/notifications/{notice_id}", json={"read": False}, headers=organiser
        )
        assert unread.status_code == 200
        assert unread.json()["read"] is False
        assert unread.json()["readAt"] == ""



class TestAccess:
    def test_tc_n13_another_users_notice_reads_as_missing(
        self, client, auth_headers, notification_repository
    ):
        notification_repository.notifications = [stored(7, 99, "2026-10-01T09:00:00")]
        response = client.patch(
            "/notifications/7", json={"read": True}, headers=auth_headers("Event Organiser")
        )
        assert response.status_code == 404
        assert notification_repository.notifications[0].is_read is False


    # US4.6 gave Venue Staff notifications: they are told when a cancelled
    # event's bookings are released. US10.3 gave the Lead them, for submissions.




