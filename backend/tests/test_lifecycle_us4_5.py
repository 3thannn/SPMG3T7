"""US4.5 lifecycle behavior through the public routes and the status rule."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import supabase_client
from app.booking_store import SupabaseBookings
from app.event_status import CompletionRefusal, EventStatus, check_completion
from app.event_store import Event, StaleEventStatus, SupabaseEvents, to_event
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

EVENT = {
    "title": "Welcome Night",
    "purpose": "Meet the cohort",
    "description": "Games and introductions.",
    "startsAt": "2099-11-02T09:00",
    "endsAt": "2099-11-02T17:00",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}
BOOKING = {"venueId": "1", "startsAt": EVENT["startsAt"], "endsAt": EVENT["endsAt"]}


def create_and_submit(client, auth_headers):
    organiser = auth_headers("Event Organiser")
    draft = client.post("/events", json=EVENT, headers=organiser)
    assert draft.status_code == 201
    assert draft.json()["status"] == "Draft"
    submitted = client.post(f"/events/{draft.json()['id']}/submit", headers=organiser)
    assert submitted.status_code == 200
    return submitted.json()


def assign(client, auth_headers, event_id):
    return client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )


def seeded(event_repository, status, *, ends_at="2020-01-01T17:00", coordinator_id=COORDINATOR_ID):
    starts_at = f"{ends_at[:10]}T09:00" if ends_at else "2020-01-01T09:00"
    event = Event(
        id=991, title="Ended event", purpose="Purpose", description="",
        starts_at=starts_at, ends_at=ends_at, expected_attendance=30,
        status=status, organiser_id=ORGANISER_ID, organiser_name="Dylan",
        created_at="2019-01-01T09:00", updated_at="2019-01-01T09:00",
        coordinator_id=coordinator_id,
    )
    event_repository.events.append(event)
    return event


def test_draft_submission_assignment_decision_and_first_booking(
    client, auth_headers, event_repository, booking_repository
):
    submitted = create_and_submit(client, auth_headers)
    assert submitted["coordinatorId"] is None
    assert [(h["from"], h["to"]) for h in submitted["history"][1:]] == [
        ("Draft", "Submitted")
    ]
    assigned = assign(client, auth_headers, submitted["id"])
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "Under Review"
    lead_change = assigned.json()["history"][-1]
    assert (lead_change["from"], lead_change["to"], lead_change["byId"]) == (
        "Submitted", "Under Review", "3"
    )
    coordinator = auth_headers("Event Coordinator")
    approved = client.post(f"/events/{submitted['id']}/approve", headers=coordinator)
    assert approved.status_code == 200
    assert approved.json()["status"] == "Approved"
    first = client.post(f"/events/{submitted['id']}/bookings", json=BOOKING, headers=coordinator)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "Requested"
    planned = event_repository.get_event(int(submitted["id"]))
    assert planned.status is EventStatus.PLANNING
    assert [(h.from_status, h.to_status, h.by_id) for h in planned.history[-1:]] == [
        (EventStatus.APPROVED, EventStatus.PLANNING, COORDINATOR_ID)
    ]
    # US15.1: the first booking holds the Great Hall for this slot, so the
    # second one is for another venue.
    second = client.post(
        f"/events/{submitted['id']}/bookings", json={**BOOKING, "venueId": "3"},
        headers=coordinator,
    )
    assert second.status_code == 201
    assert len(booking_repository.bookings) == 2
    assert len(event_repository.get_event(int(submitted["id"])).history) == len(planned.history)
    cancelled = client.post(
        f"/events/{submitted['id']}/bookings/{first.json()['id']}/cancel",
        json={"reason": "Using the other venue"}, headers=coordinator,
    )
    assert cancelled.status_code == 200
    assert event_repository.get_event(int(submitted["id"])).status is EventStatus.PLANNING
    assert len(event_repository.get_event(int(submitted["id"])).history) == len(planned.history)


def test_unassigned_change_request_stays_in_lead_queue(client, auth_headers):
    submitted = create_and_submit(client, auth_headers)
    response = client.post(
        f"/events/{submitted['id']}/change-request",
        json={**EVENT, "title": "Updated title", "note": "Please update"},
        headers=auth_headers("Event Organiser"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Submitted"
    assert response.json()["changeRequested"] is True
    assert response.json()["changeRequestNote"] == "Please update"
    assert len(response.json()["history"]) == len(submitted["history"])
    queue = client.get("/events/unassigned", headers=auth_headers("Event Coordinator Lead"))
    assert [item["id"] for item in queue.json()] == [submitted["id"]]
    assigned = assign(client, auth_headers, submitted["id"])
    assert assigned.json()["status"] == "Under Review"
    assert assigned.json()["changeRequested"] is True


@pytest.mark.parametrize("event_status", [EventStatus.APPROVED, EventStatus.PLANNING])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_post_review_change_requests_keep_status(
    client, auth_headers, event_repository, event_status, decision
):
    event = seeded(event_repository, event_status, ends_at="2099-11-02T17:00")
    response = client.post(
        f"/events/{event.id}/change-request",
        json={**EVENT, "startsAt": event.starts_at, "endsAt": event.ends_at,
              "title": "Updated title", "note": "New plan"},
        headers=auth_headers("Event Organiser"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == event_status
    assert response.json()["changeRequested"] is True
    assert response.json()["changeRequestNote"] == "New plan"
    assert response.json()["history"] == []
    resolved = client.post(
        f"/events/{event.id}/change-request/{decision}",
        json={"reason": "Keep the original plan."} if decision == "reject" else None,
        headers=auth_headers("Event Coordinator"),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == event_status
    assert resolved.json()["changeRequested"] is False
    assert resolved.json()["changeRequestNote"] == ""
    assert resolved.json()["lastChangeReview"]["requestNote"] == "New plan"
    assert resolved.json()["history"] == []
    fetched = client.get(f"/events/{event.id}", headers=auth_headers("Event Organiser"))
    assert fetched.json()["lastChangeReview"]["requestNote"] == "New plan"


def test_real_store_pairs_last_review_note_with_that_request():
    row = {
        "id": 42, "name": "Example", "purpose": "Purpose", "description": "",
        "proposed_date": "2099-01-01T09:00", "end_date": "2099-01-01T17:00",
        "expected_attendance": 10, "status": "Planning", "organiser_id": ORGANISER_ID,
        "created_at": "2026-01-01T09:00", "updated_at": "2026-01-01T09:00",
    }
    requests = [
        {"changed_field": "name", "old_value": "A", "new_value": "B",
         "change_type": "routine", "status": "approved",
         "reviewed_at": "2026-01-02T09:00", "review_note": "",
         "request_note": "First request"},
        {"changed_field": "name", "old_value": "B", "new_value": "C",
         "change_type": "routine", "status": "rejected",
         "reviewed_at": "2026-01-03T09:00", "review_note": "No",
         "request_note": "Second request"},
        {"changed_field": "purpose", "old_value": "Purpose", "new_value": "New",
         "change_type": "routine", "status": "pending", "reviewed_at": None,
         "request_note": "Current request"},
    ]
    event = to_event(row, requests=requests)
    assert event.change_request_note == "Current request"
    assert event.last_change_review is not None
    assert event.last_change_review.request_note == "Second request"
    assert event.last_change_review.note == "No"


def test_completion_time_boundary():
    end = datetime(2026, 10, 11, 18, 0)
    assert (
        check_completion(end.isoformat(), now=end - timedelta(microseconds=1))
        is CompletionRefusal.EVENT_NOT_ENDED
    )
    assert check_completion(end.isoformat(), now=end) is CompletionRefusal.EVENT_NOT_ENDED
    assert check_completion(end.isoformat(), now=end + timedelta(microseconds=1)) is None
    assert check_completion("", now=end) is CompletionRefusal.MISSING_END_TIME
    assert check_completion("not-a-time", now=end) is CompletionRefusal.INVALID_END_TIME


def test_only_assigned_coordinator_completes_ended_confirmed_event(
    client, auth_headers, event_repository
):
    event = seeded(event_repository, EventStatus.CONFIRMED)
    path = f"/events/{event.id}/complete"
    assert client.post(path, headers=auth_headers("Event Organiser")).status_code == 403
    assert client.post(path, headers=auth_headers("Event Coordinator Lead")).status_code == 403
    completed = client.post(path, headers=auth_headers("Event Coordinator"))
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "Completed"
    assert completed.json()["history"][-1]["byId"] == str(COORDINATOR_ID)
    assert completed.json()["history"][-1]["at"]
    second = client.post(path, headers=auth_headers("Event Coordinator"))
    assert second.status_code == 409
    assert len(event_repository.get_event(event.id).history) == 1


@pytest.mark.parametrize(
    ("status", "ends_at", "reason"),
    [
        (EventStatus.PLANNING, "2020-01-01T17:00", "invalid-transition"),
        (EventStatus.CONFIRMED, "", "missing-end-time"),
        (EventStatus.CONFIRMED, "2099-01-01T17:00", "event-not-ended"),
    ],
)
def test_completion_refusals_leave_event_unchanged(
    client, auth_headers, event_repository, status, ends_at, reason
):
    event = seeded(event_repository, status, ends_at=ends_at)
    response = client.post(
        f"/events/{event.id}/complete", headers=auth_headers("Event Coordinator")
    )
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == reason
    assert event_repository.get_event(event.id) == event


def test_other_coordinator_cannot_complete(client, auth_headers, event_repository):
    event = seeded(event_repository, EventStatus.CONFIRMED, coordinator_id=999)
    response = client.post(
        f"/events/{event.id}/complete", headers=auth_headers("Event Coordinator")
    )
    assert response.status_code == 404
    assert event_repository.get_event(event.id) == event


@pytest.mark.parametrize(
    "status", [EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW, EventStatus.CONFIRMED]
)
def test_venue_request_before_or_after_planning_is_refused(
    client, auth_headers, event_repository, booking_repository, status
):
    event = seeded(event_repository, status, ends_at="2099-11-02T17:00")
    response = client.post(
        f"/events/{event.id}/bookings", json=BOOKING,
        headers=auth_headers("Event Coordinator"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["message"]
    assert booking_repository.bookings == []
    assert event_repository.get_event(event.id) == event


class RpcAdmin:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def rpc(self, name, arguments):
        self.calls.append((name, arguments))
        return self

    def execute(self):
        return SimpleNamespace(data=self.result)


def test_real_store_uses_atomic_assignment_rpc(monkeypatch):
    admin = RpcAdmin(True)
    event = Event(
        id=42, title="Example", purpose="Purpose", description="",
        starts_at="2099-01-01T09:00", ends_at="2099-01-01T17:00",
        expected_attendance=10, status=EventStatus.UNDER_REVIEW,
        organiser_id=ORGANISER_ID, organiser_name="Dylan",
        created_at="2026-01-01T09:00", updated_at="2026-01-01T09:00",
        coordinator_id=COORDINATOR_ID,
    )
    store = SupabaseEvents()
    monkeypatch.setattr(supabase_client, "admin", lambda: admin)
    monkeypatch.setattr(store, "get_event", lambda _id: event)
    assert store.assign_coordinator(42, COORDINATOR_ID, 3) is event
    assert admin.calls == [
        ("assign_event_coordinator", {
            "p_event_id": 42, "p_coordinator_id": COORDINATOR_ID,
            "p_assigned_by_id": 3,
        })
    ]
    admin.result = False
    with pytest.raises(StaleEventStatus):
        store.assign_coordinator(42, COORDINATOR_ID, 3)


def test_real_store_uses_atomic_booking_and_completion_rpcs(monkeypatch):
    admin = RpcAdmin(77)
    monkeypatch.setattr(supabase_client, "admin", lambda: admin)
    bookings = SupabaseBookings()
    marker = object()
    monkeypatch.setattr(bookings, "get_booking", lambda _id: marker)
    result = bookings.create(
        event_id=42, venue_id=1, starts_at="2099-01-01T09:00",
        ends_at="2099-01-01T17:00", requested_by_id=COORDINATOR_ID,
        headcount=10, expected_status=EventStatus.APPROVED,
    )
    assert result is marker
    assert [name for name, _args in admin.calls] == ["request_venue_and_plan"]
    assert admin.calls[0][1]["p_expected_status"] == "Approved"
    assert admin.calls[0][1]["p_requested_by_id"] == COORDINATOR_ID

    admin.result = True
    events = SupabaseEvents()
    monkeypatch.setattr(events, "get_event", lambda _id: marker)
    assert events.complete_event(42, actor_id=COORDINATOR_ID) is marker
    assert admin.calls[-1] == (
        "complete_event_status", {"p_event_id": 42, "p_coordinator_id": COORDINATOR_ID}
    )
