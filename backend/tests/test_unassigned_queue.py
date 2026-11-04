"""US8.2 — Unassigned event queue for Coordinator Lead.

The Lead needs to see which events are Submitted but have no Coordinator assigned
(coordinator_id IS NULL), so they can manually assign them to Coordinators via US8.3.
"""

from app.event_status import EventStatus
from tests.conftest import ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "endsAt": "2026-11-15T17:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}


class TestUnassignedQueueAccess:
    """AC1: Only Coordinator Lead can access the unassigned queue."""

    def test_lead_can_list_unassigned_events(self, client, auth_headers):
        """GET /events/unassigned shows Submitted events with coordinator_id=NULL."""
        # Create and submit an event (US8.2: remains unassigned)
        organiser = auth_headers("Event Organiser")
        created = client.post("/events", json=DRAFT, headers=organiser)
        event_id = created.json()["id"]
        client.post(f"/events/{event_id}/submit", headers=organiser)

        # Lead can access the unassigned queue
        response = client.get("/events/unassigned", headers=auth_headers("Event Coordinator Lead"))

        assert response.status_code == 200
        events = response.json()
        assert len(events) == 1
        assert events[0]["id"] == event_id
        assert events[0]["coordinatorId"] is None
        assert events[0]["status"] == "Submitted"

    def test_regular_coordinator_cannot_access_unassigned_queue(self, client, auth_headers):
        """Regular Coordinators get 403 when trying to access /events/unassigned."""
        response = client.get("/events/unassigned", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"



class TestUnassignedQueueFiltering:
    """AC2: The unassigned queue only shows Submitted events with coordinator_id=NULL."""

    def test_unassigned_queue_oldest_first(self, client, auth_headers, event_repository):
        """Unassigned events are ordered oldest first (submission order)."""
        from app.event_store import Event

        # Seed three unassigned Submitted events
        event_repository.events.extend([
            Event(
                id=501,
                title="Oldest Event",
                purpose="Testing",
                description="First submitted",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=None,
            ),
            Event(
                id=502,
                title="Middle Event",
                purpose="Testing",
                description="Second submitted",
                starts_at="2026-11-16T14:00",
                ends_at="2026-11-16T16:00",
                expected_attendance=40,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T10:00:00",
                updated_at="2026-01-10T10:00:00",
                coordinator_id=None,
            ),
            Event(
                id=503,
                title="Newest Event",
                purpose="Testing",
                description="Third submitted",
                starts_at="2026-11-17T14:00",
                ends_at="2026-11-17T16:00",
                expected_attendance=50,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T11:00:00",
                updated_at="2026-01-10T11:00:00",
                coordinator_id=None,
            ),
        ])

        response = client.get("/events/unassigned", headers=auth_headers("Event Coordinator Lead"))

        assert response.status_code == 200
        events = response.json()
        assert len(events) == 3
        # Oldest first
        assert events[0]["id"] == "501"
        assert events[1]["id"] == "502"
        assert events[2]["id"] == "503"

    def test_unassigned_queue_only_shows_submitted_status(
        self, client, auth_headers, event_repository
    ):
        """Only Submitted events appear in the unassigned queue, not Draft or other statuses."""
        from app.event_store import Event

        # Seed events with different statuses, all unassigned
        event_repository.events.extend([
            Event(
                id=501,
                title="Draft Event",
                purpose="Testing",
                description="Draft status",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.DRAFT,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=None,
            ),
            Event(
                id=502,
                title="Submitted Event",
                purpose="Testing",
                description="Submitted status",
                starts_at="2026-11-16T14:00",
                ends_at="2026-11-16T16:00",
                expected_attendance=40,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T10:00:00",
                updated_at="2026-01-10T10:00:00",
                coordinator_id=None,
            ),
            Event(
                id=503,
                title="Approved Event",
                purpose="Testing",
                description="Approved status",
                starts_at="2026-11-17T14:00",
                ends_at="2026-11-17T16:00",
                expected_attendance=50,
                status=EventStatus.APPROVED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T11:00:00",
                updated_at="2026-01-10T11:00:00",
                coordinator_id=None,
            ),
        ])

        response = client.get("/events/unassigned", headers=auth_headers("Event Coordinator Lead"))

        assert response.status_code == 200
        events = response.json()
        assert len(events) == 1
        assert events[0]["id"] == "502"
        assert events[0]["status"] == "Submitted"



class TestLeadReadsTheEvent:
    """US8.2 AC3: the Lead opens a queued event and sees its basic info, read-only."""

    def test_the_lead_opens_a_queued_event_but_cannot_edit_it(self, client, auth_headers):
        organiser = auth_headers("Event Organiser")
        event_id = client.post("/events", json=DRAFT, headers=organiser).json()["id"]
        client.post(f"/events/{event_id}/submit", headers=organiser)
        lead = auth_headers("Event Coordinator Lead")

        opened = client.get(f"/events/{event_id}", headers=lead)
        edited = client.put(f"/events/{event_id}", json={**DRAFT, "title": "Renamed"}, headers=lead)

        assert opened.status_code == 200
        body = opened.json()
        assert (body["title"], body["status"], body["coordinatorId"]) == (
            DRAFT["title"],
            "Submitted",
            None,
        )
        assert body["expectedAttendance"] == DRAFT["expectedAttendance"]
        assert edited.status_code == 403
        assert client.get(f"/events/{event_id}", headers=lead).json()["title"] == DRAFT["title"]
