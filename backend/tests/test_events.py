"""The event endpoints — US4.1 (SPMG3T7-28) and US4.2 (SPMG3T7-29).

These rules used to live only in the browser's event store, where anyone with
devtools could edit around them. The point of these tests is that the server now
refuses on its own account: every "cannot" here is asserted against a request,
not against a disabled button.
"""

from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "startsAt": "2026-11-02T18:00",
    "endsAt": "2026-11-02T21:00",
    "description": "Talks.",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}


def create(client, headers, **overrides) -> dict:
    """Create an event and return it, failing the test if creation itself broke."""
    response = client.post("/events", json={**DRAFT, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestCreating:
    def test_a_new_event_starts_as_a_draft(self, client, auth_headers):
        event = create(client, auth_headers("Event Organiser"))

        assert event["status"] == "Draft"
        assert event["title"] == "Faculty Welcome Night"
        assert event["organiserId"] == str(ORGANISER_ID)
















class TestVisibility:
    """US4.1: Organisers see their events; Coordinators see submitted requests."""

    def test_an_organiser_sees_their_own_event(self, client, auth_headers):
        create(client, auth_headers("Event Organiser"))

        listed = client.get("/events", headers=auth_headers("Event Organiser")).json()

        assert [event["title"] for event in listed] == ["Faculty Welcome Night"]

    def test_an_organiser_does_not_see_another_organisers_event(
        self, client, auth_headers, event_repository
    ):
        create(client, auth_headers("Event Organiser"))
        # Reassign it, standing in for a second Organiser the fixtures do not have.
        event_repository.events = [
            event.__class__(**{**event.__dict__, "organiser_id": 999})
            for event in event_repository.events
        ]

        listed = client.get("/events", headers=auth_headers("Event Organiser")).json()

        assert listed == []


    def test_a_coordinator_cannot_open_a_draft_directly(self, client, auth_headers):
        event = create(client, auth_headers("Event Organiser"))

        response = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "event_not_found"

    # --- Added for SPMG3T7-33 (US5.1) ---
    def test_a_coordinator_can_open_a_submitted_event_and_see_every_field(
        self, client, auth_headers
    ):
        """US5.1: a Coordinator opens a submitted request and reads it whole.
        US8.6: Coordinator must be assigned to the event first."""
        event = create(client, auth_headers("Event Organiser"))
        client.post(f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser"))

        # US8.6: Assign the event to the coordinator
        client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=auth_headers("Event Coordinator Lead"),
        )

        fetched = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Coordinator")
        )

        assert fetched.status_code == 200
        body = fetched.json()
        assert body["title"] == "Faculty Welcome Night"
        assert body["purpose"] == "Welcome the new intake."
        assert body["description"] == "Talks."
        assert body["startsAt"] == "2026-11-02T18:00"
        assert body["expectedAttendance"] == 120
        assert body["status"] == "Under Review"
        assert body["organiserId"] == str(ORGANISER_ID)
        assert body["organiserName"] == "Dylan"
        assert len(body["history"]) >= 2  # At least creation and submission





class TestSaving:
    """US4.2: "Draft stays Draft on save." A save is not a status change."""

    def test_saving_edits_content_and_leaves_the_status_alone(self, client, auth_headers):
        event = create(client, auth_headers())

        saved = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Renamed"},
            headers=auth_headers(),
        ).json()

        assert saved["title"] == "Renamed"
        assert saved["status"] == "Draft"






    def test_owner_cannot_edit_their_submitted_event_directly(self, client, auth_headers):
        """US11.1: once submitted, the owner requests a change instead of editing."""
        event = create(client, auth_headers("Event Organiser"))
        client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        )

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Renamed by Owner"},
            headers=auth_headers("Event Organiser"),
        )

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "change-request-required"


    def test_non_owner_without_edit_permission_cannot_edit(
        self, client, auth_headers, event_repository
    ):
        """Someone who is neither owner nor coordinator cannot edit."""
        event = create(client, auth_headers("Event Organiser"))
        # Reassign to simulate another user's event
        event_repository.events = [
            item.__class__(**{**item.__dict__, "organiser_id": 999})
            for item in event_repository.events
        ]

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Hijacked"},
            headers=auth_headers("Event Organiser"),
        )

        # Returns 404 because user can't see the event (same as read behavior)
        assert response.status_code == 404


class TestSubmitting:
    """US4.2: Draft -> Submitted, exactly once, timestamped and attributable."""

    def test_an_organiser_submits_their_draft(self, client, auth_headers):
        event = create(client, auth_headers())

        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers()
        ).json()

        assert submitted["status"] == "Submitted"

    def test_submission_still_needs_a_title(self, client, auth_headers):
        event = create(client, auth_headers(), title="", description="Planning notes")

        response = client.post(f"/events/{event['id']}/submit", headers=auth_headers())

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give the event a title."







    def test_editing_an_event_rejects_equal_start_and_end_times(self, client, auth_headers):
        event = create(
            client,
            auth_headers(),
            startsAt="2026-11-02T18:00",
            endsAt="2026-11-02T19:00",
        )

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "startsAt": "2026-11-02T18:00", "endsAt": "2026-11-02T18:00"},
            headers=auth_headers(),
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "The end date must be after the start date."

    def test_the_submission_is_recorded_with_who_and_when(self, client, auth_headers):
        event = create(client, auth_headers())

        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers()
        ).json()

        entry = submitted["history"][-1]
        assert entry["from"] == "Draft"
        assert entry["to"] == "Submitted"
        assert entry["byId"] == str(ORGANISER_ID)
        assert entry["byName"] == "Dylan"
        assert entry["at"]


    def test_submitting_twice_is_refused_with_a_reason(self, client, auth_headers):
        event = create(client, auth_headers())
        client.post(f"/events/{event['id']}/submit", headers=auth_headers())

        second = client.post(f"/events/{event['id']}/submit", headers=auth_headers())

        assert second.status_code == 409
        detail = second.json()["detail"]
        assert detail["reason"] == "already-submitted"
        assert detail["message"] == (
            "This event has already been submitted. An event can only be submitted once."
        )



class TestCoordinatorEditing:
    """US5.2: Coordinators can edit events with change tracking (important vs routine).
    US8.6: Coordinators must be assigned to events to edit them."""


    def test_coordinator_edit_logs_each_change_as_important_or_routine(
        self, client, auth_headers, event_repository
    ):
        """US5.2 AC2: an attendance edit is logged important, a title edit routine."""
        event = create(client, auth_headers("Event Organiser"))
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()
        client.post(
            f"/events/{submitted['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=auth_headers("Event Coordinator Lead"),
        )

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "title": "Welcome Night", "expectedAttendance": 200},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["expectedAttendance"] == 200
        logged = {
            change.field: change.important
            for event_id, change in event_repository.change_log
            if event_id == int(submitted["id"])
        }
        assert logged == {"name": False, "expected_attendance": True}





    def test_coordinator_can_edit_submitted_event(self, client, auth_headers):
        """Coordinators can edit assigned events after review begins."""
        event = create(client, auth_headers("Event Organiser"))
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        # US8.6: Assign to coordinator
        client.post(
            f"/events/{submitted['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=auth_headers("Event Coordinator Lead"),
        )

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "title": "Edited After Submission"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["title"] == "Edited After Submission"
        assert saved["status"] == "Under Review"  # Status unchanged




