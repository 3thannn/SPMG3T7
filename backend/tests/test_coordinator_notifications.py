"""US10.2: Coordinators are notified about events that need their attention.

Test case ids (TC-CN…) match the US10.2 test report. Only assignment (US8.3)
exists as a route; the other triggers are exercised through the `notify_*`
functions US8.4, US14.4, US12.2/US15.2 and US17.2 will call.
"""

from dataclasses import dataclass, field

import pytest

from app import notifications, supabase_client
from app.event_status import EventStatus
from app.event_store import Event
from app.notification_store import TABLE, SupabaseNotifications
from app.notifications import CoordinatorNotice
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

OTHER_COORDINATOR_ID = 99

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    # US2.1: an event cannot be submitted without its needs.
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


def assign(client, auth_headers, event_id: str):
    return client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )


def coordinator_notices(client, auth_headers) -> list[dict]:
    response = client.get("/notifications", headers=auth_headers("Event Coordinator"))
    assert response.status_code == 200, response.text
    return response.json()


def event(coordinator_id: int | None = COORDINATOR_ID, title: str = "Careers Fair") -> Event:
    return Event(
        id=1,
        organiser_id=ORGANISER_ID,
        organiser_name="Olivia Organiser",
        title=title,
        purpose="",
        description="",
        starts_at="2027-11-02T18:00",
        ends_at="2027-11-02T21:00",
        expected_attendance=100,
        status=EventStatus.APPROVED,
        created_at="2027-10-01T09:00:00",
        updated_at="2027-10-01T09:00:00",
        coordinator_id=coordinator_id,
    )


class TestAssignment:
    def test_tc_cn01_assignment_notifies_the_coordinator(self, client, auth_headers):
        event_id = submitted_event(client, auth_headers)
        assert assign(client, auth_headers, event_id).status_code == 200

        [notice] = coordinator_notices(client, auth_headers)
        assert notice["kind"] == "assigned"
        assert notice["eventId"] == event_id
        assert notice["eventTitle"] == "Faculty Welcome Night"
        assert notice["message"] == 'You were assigned "Faculty Welcome Night".'
        assert notice["status"] is None
        assert notice["read"] is False

    def test_tc_cn02_the_organiser_gets_their_own_notice_not_this_one(
        self, client, auth_headers, notification_repository
    ):
        event_id = submitted_event(client, auth_headers)
        assign(client, auth_headers, event_id)

        by_recipient = {item.user_id: item.kind for item in notification_repository.notifications}
        assert by_recipient == {ORGANISER_ID: "event-status", COORDINATOR_ID: "assigned"}

    def test_tc_cn03_a_refused_assignment_does_not_notify(self, client, auth_headers):
        event_id = submitted_event(client, auth_headers)
        assign(client, auth_headers, event_id)

        again = assign(client, auth_headers, event_id)
        assert again.status_code == 409
        assert len(coordinator_notices(client, auth_headers)) == 1

    def test_tc_cn04_a_failed_notice_does_not_fail_the_assignment(
        self, client, auth_headers, notification_repository, monkeypatch
    ):
        def broken(**_kwargs):
            raise RuntimeError("kind check rejected the row")

        monkeypatch.setattr(notification_repository, "create_notice", broken)
        event_id = submitted_event(client, auth_headers)

        assigned = assign(client, auth_headers, event_id)
        assert assigned.status_code == 200
        assert assigned.json()["status"] == "Under Review"


class TestReassignment:
    def test_tc_cn05_reassignment_tells_both_coordinators(self, notification_repository):
        notifications.notify_reassigned(event(), COORDINATOR_ID, OTHER_COORDINATOR_ID)

        by_recipient = {
            item.user_id: (item.kind, item.message)
            for item in notification_repository.notifications
        }
        assert by_recipient == {
            COORDINATOR_ID: ("unassigned", '"Careers Fair" is no longer assigned to you.'),
            OTHER_COORDINATOR_ID: ("assigned", 'You were assigned "Careers Fair".'),
        }

    def test_tc_cn06_reassigning_to_the_same_coordinator_is_silent(
        self, notification_repository
    ):
        notifications.notify_reassigned(event(), COORDINATOR_ID, COORDINATOR_ID)
        assert notification_repository.notifications == []

    def test_tc_cn07_a_first_assignment_through_reassign_only_notifies_the_new_one(
        self, notification_repository
    ):
        notifications.notify_reassigned(event(coordinator_id=None), None, COORDINATOR_ID)

        [notice] = notification_repository.notifications
        assert (notice.user_id, notice.kind) == (COORDINATOR_ID, "assigned")


class TestBookingAndSafety:
    @pytest.mark.parametrize(
        ("notify", "kind", "message"),
        [
            (
                lambda e: notifications.notify_hold_expiring(e, "Main Hall", "in 24 hours"),
                CoordinatorNotice.HOLD_EXPIRING,
                'The tentative hold on Main Hall for "Careers Fair" expires in 24 hours.',
            ),
            (
                lambda e: notifications.notify_hold_expired(e, "Main Hall"),
                CoordinatorNotice.HOLD_EXPIRED,
                'The tentative hold on Main Hall for "Careers Fair" has expired.',
            ),
            (
                lambda e: notifications.notify_booking_conflict(
                    e, "Main Hall", "the venue is closed for repairs that day."
                ),
                CoordinatorNotice.BOOKING_CONFLICT,
                'The booking of Main Hall for "Careers Fair" needs attention: '
                "the venue is closed for repairs that day.",
            ),
            (
                lambda e: notifications.notify_safety_changes(e, "Add a second fire exit."),
                CoordinatorNotice.SAFETY_CHANGES,
                'The Safety Officer requested changes to "Careers Fair": '
                "Add a second fire exit.",
            ),
            (
                lambda e: notifications.notify_safety_changes(e),
                CoordinatorNotice.SAFETY_CHANGES,
                'The Safety Officer requested changes to "Careers Fair".',
            ),
        ],
        ids=["tc_cn08_hold_expiring", "tc_cn09_hold_expired", "tc_cn10_booking_conflict",
             "tc_cn11_safety_changes", "tc_cn12_safety_changes_without_notes"],
    )
    def test_each_trigger_notifies_the_assigned_coordinator(
        self, notification_repository, notify, kind, message
    ):
        notify(event())

        [notice] = notification_repository.notifications
        assert notice.user_id == COORDINATOR_ID
        assert notice.kind == kind
        assert notice.message == message
        assert notice.status is None

    def test_tc_cn13_an_unassigned_event_notifies_nobody(self, notification_repository):
        unassigned = event(coordinator_id=None)
        notifications.notify_hold_expired(unassigned, "Main Hall")
        notifications.notify_booking_conflict(unassigned, "Main Hall", "closed.")
        notifications.notify_safety_changes(unassigned, "Fix it.")
        assert notification_repository.notifications == []

    def test_tc_cn14_a_failed_write_is_logged_not_raised(
        self, notification_repository, monkeypatch, caplog
    ):
        def broken(**_kwargs):
            raise RuntimeError("notifications table missing")

        monkeypatch.setattr(notification_repository, "create_notice", broken)
        notifications.notify_safety_changes(event(), "Fix it.")
        assert "US10.2 safety-changes notification" in caplog.text

    def test_tc_cn15_an_untitled_event_still_reads_sensibly(self, notification_repository):
        notifications.notify_hold_expired(event(title="  "), "Main Hall")
        [notice] = notification_repository.notifications
        assert notice.message == (
            'The tentative hold on Main Hall for "an untitled event" has expired.'
        )


class TestTheCoordinatorsList:
    def test_tc_cn16_a_coordinator_can_mark_a_notice_read_and_unread(self, client, auth_headers):
        assign(client, auth_headers, submitted_event(client, auth_headers))
        coordinator = auth_headers("Event Coordinator")
        notice_id = coordinator_notices(client, auth_headers)[0]["id"]

        read = client.patch(f"/notifications/{notice_id}", json={"read": True}, headers=coordinator)
        assert read.status_code == 200, read.text
        assert read.json()["read"] is True

        unread = client.patch(
            f"/notifications/{notice_id}", json={"read": False}, headers=coordinator
        )
        assert unread.json()["read"] is False

    def test_tc_cn17_unread_first_then_newest(self, client, auth_headers):
        notifications.notify_hold_expiring(event(), "Main Hall", "tomorrow")
        notifications.notify_hold_expired(event(), "Main Hall")
        coordinator = auth_headers("Event Coordinator")
        oldest, newest = sorted(item["id"] for item in coordinator_notices(client, auth_headers))
        client.patch(f"/notifications/{newest}", json={"read": True}, headers=coordinator)

        assert [item["id"] for item in coordinator_notices(client, auth_headers)] == [
            oldest,
            newest,
        ]

    def test_tc_cn18_a_coordinator_sees_only_their_own_notices(self, client, auth_headers):
        notifications.notify_safety_changes(event(coordinator_id=OTHER_COORDINATOR_ID), "x")
        assert coordinator_notices(client, auth_headers) == []

    def test_tc_cn19_a_coordinator_cannot_toggle_someone_elses_notice(
        self, client, auth_headers
    ):
        notifications.notify_safety_changes(event(coordinator_id=OTHER_COORDINATOR_ID), "x")
        response = client.patch(
            "/notifications/1", json={"read": True}, headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 404


STORED_ROW = {
    "id": 41,
    "user_id": COORDINATOR_ID,
    "event_id": 7,
    "status": None,
    "kind": "hold-expired",
    "equipment_request_id": None,
    "message": "The tentative hold on Main Hall for \"Careers Fair\" has expired.",
    "is_read": False,
    "created_at": "2027-10-01T09:00:00",
    "read_at": None,
    "events": {"name": "Careers Fair"},
}


@dataclass
class FakeQuery:
    """Records each PostgREST builder call and answers with one stored row."""

    calls: list[tuple] = field(default_factory=list)

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, *args))
            return self

        return record

    def execute(self):
        self.calls.append(("execute",))
        return type("Response", (), {"data": [dict(STORED_ROW)]})()


@dataclass
class FakeClient:
    query: FakeQuery

    def table(self, name: str) -> FakeQuery:
        self.query.calls.append(("table", name))
        return self.query


class TestTheSupabaseStore:
    def test_tc_cn20_create_notice_writes_a_coordinator_row(self, monkeypatch):
        query = FakeQuery()
        monkeypatch.setattr(supabase_client, "admin", lambda: FakeClient(query))

        created = SupabaseNotifications().create_notice(
            user_id=COORDINATOR_ID, event_id=7, kind="hold-expired", message="m"
        )

        assert query.calls[0] == ("table", TABLE)
        [(_, inserted)] = [call for call in query.calls if call[0] == "insert"]
        assert inserted["user_id"] == COORDINATOR_ID
        assert inserted["event_id"] == 7
        assert inserted["kind"] == "hold-expired"
        # The kind check requires both of these to be empty for a Coordinator notice.
        assert inserted["status"] is None
        assert "equipment_request_id" not in inserted
        assert created.kind == "hold-expired"
        assert created.event_title == "Careers Fair"
        assert created.status is None
