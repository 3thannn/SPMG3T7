"""US10.1: Organisers are notified of status changes and can manage read state.

Test case ids (TC-N…) match the US10.1 test report.
"""

import pytest

from app import notification_store
from app.event_status import EventStatus
from app.event_store import Event
from app.notification_store import Notification, ordered, to_notification
from app.notifications import message_for
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

    def test_tc_n04_a_question_notifies_with_the_request(self, client, auth_headers):
        event_id = assigned_event(client, auth_headers)
        ask(client, auth_headers, event_id, "How many vegetarian meals?")

        listed = notices(client, auth_headers)
        assert len(listed) == 2
        assert listed[0]["status"] == "Under Review"
        assert "How many vegetarian meals?" in listed[0]["message"]

    def test_tc_n05_submitting_does_not_notify(self, client, auth_headers):
        submitted_event(client, auth_headers)
        assert notices(client, auth_headers) == []

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

    def test_tc_n08_the_notice_goes_to_the_owner_only(
        self, client, auth_headers, notification_repository
    ):
        under_review_event(client, auth_headers)
        # US10.2's assignment notice goes to the Coordinator; status notices don't.
        status_notices = [
            item for item in notification_repository.notifications if item.kind == "event-status"
        ]
        assert status_notices
        assert all(item.user_id == ORGANISER_ID for item in status_notices)


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

    def test_tc_n10_only_the_callers_notices_are_listed(
        self, client, auth_headers, notification_repository
    ):
        notification_repository.notifications = [
            stored(1, ORGANISER_ID, "2026-10-01T09:00:00"),
            stored(2, 99, "2026-10-02T09:00:00"),
        ]
        assert [item["id"] for item in notices(client, auth_headers)] == ["1"]

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

    def test_tc_n12_a_read_notice_drops_below_unread_ones(self, client, auth_headers):
        event_id = under_review_event(client, auth_headers)
        ask(client, auth_headers, event_id, "Second question")
        organiser = auth_headers("Event Organiser")
        newest = notices(client, auth_headers)[0]["id"]

        client.patch(f"/notifications/{newest}", json={"read": True}, headers=organiser)
        listed = notices(client, auth_headers)
        assert listed[-1]["id"] == newest
        assert [item["read"] for item in listed] == [False, False, True]


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

    @pytest.mark.parametrize("notification_id", ["999", "abc"])
    def test_tc_n14_unknown_ids_are_404(self, client, auth_headers, notification_id):
        response = client.patch(
            f"/notifications/{notification_id}",
            json={"read": True},
            headers=auth_headers("Event Organiser"),
        )
        assert response.status_code == 404

    # US4.6 gave Venue Staff notifications: they are told when a cancelled
    # event's bookings are released.
    @pytest.mark.parametrize("role", ["Event Coordinator Lead", "Safety Officer"])
    def test_tc_n15_other_roles_are_refused(self, client, auth_headers, role):
        response = client.get("/notifications", headers=auth_headers(role))
        assert response.status_code == 403

    def test_tc_n16_signed_out_is_refused(self, client):
        assert client.get("/notifications").status_code == 401
        assert client.patch("/notifications/1", json={"read": True}).status_code == 401

    def test_tc_n17_read_state_must_be_given(self, client, auth_headers, notification_repository):
        notification_repository.notifications = [stored(1, ORGANISER_ID, "2026-10-01T09:00:00")]
        response = client.patch(
            "/notifications/1", json={}, headers=auth_headers("Event Organiser")
        )
        assert response.status_code == 422


class TestUnits:
    def event(self, title: str = "Gala") -> Event:
        return Event(
            id=5,
            title=title,
            purpose="",
            description="",
            starts_at="",
            ends_at="",
            expected_attendance=None,
            status=EventStatus.UNDER_REVIEW,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="",
            updated_at="",
        )

    def test_tc_n18_messages(self):
        assert message_for(self.event(), EventStatus.APPROVED) == '"Gala" was approved.'
        assert message_for(self.event(), EventStatus.REJECTED, "Clash") == (
            '"Gala" was rejected. Reason: Clash'
        )
        assert message_for(self.event(), EventStatus.UNDER_REVIEW, "Budget?") == (
            'A Coordinator asked for more information about "Gala": Budget?'
        )
        assert message_for(self.event("  "), EventStatus.APPROVED) == ('"Your event" was approved.')

    def test_tc_n19_row_mapping(self):
        row = {
            "id": 3,
            "user_id": 1,
            "event_id": 5,
            "status": "Rejected",
            "message": "m",
            "is_read": False,
            "created_at": "2026-10-02T09:00:00",
            "read_at": None,
            "events": {"name": "Gala"},
        }
        notice = to_notification(row)
        assert notice.status is EventStatus.REJECTED
        assert notice.event_title == "Gala"
        assert notice.read_at == ""
        assert to_notification({**row, "events": None}).event_title == ""

    def test_tc_n20_ordering_breaks_same_second_ties_by_id(self):
        same = "2026-10-02T09:00:00"
        result = ordered([stored(1, 1, same), stored(2, 1, same)])
        assert [item.id for item in result] == [2, 1]

    def test_store_is_swappable(self, notification_repository):
        assert notification_store.repository() is notification_repository
