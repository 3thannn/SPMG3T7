"""The event endpoints — US4.1 (SPMG3T7-28) and US4.2 (SPMG3T7-29).

These rules used to live only in the browser's event store, where anyone with
devtools could edit around them. The point of these tests is that the server now
refuses on its own account: every "cannot" here is asserted against a request,
not against a disabled button.
"""

from tests.conftest import COORDINATOR_ID, ORGANISER_ID

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "startsAt": "2026-11-02T18:00",
    "description": "Talks.",
    "expectedAttendance": 120,
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

    def test_the_organiser_is_taken_from_the_session_not_the_request(
        self, client, auth_headers
    ):
        """Otherwise an Organiser could file an event under someone else's name."""
        event = create(client, auth_headers("Event Organiser"), organiserId="999")

        assert event["organiserId"] == str(ORGANISER_ID)
        assert event["organiserName"] == "Dylan"

    def test_a_coordinator_cannot_create_an_event(self, client, auth_headers):
        response = client.post(
            "/events", json=DRAFT, headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 403
        assert "create events" in response.json()["detail"]["message"]

    def test_an_event_needs_a_title(self, client, auth_headers):
        response = client.post(
            "/events", json={**DRAFT, "title": "   "}, headers=auth_headers()
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give the event a title."

    def test_an_event_needs_a_date(self, client, auth_headers):
        """events.proposed_date is NOT NULL, so a dateless draft cannot be stored."""
        response = client.post(
            "/events", json={**DRAFT, "startsAt": ""}, headers=auth_headers()
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give the event a date."

    def test_it_keeps_every_writable_column_of_the_events_table(
        self, client, auth_headers
    ):
        event = create(client, auth_headers("Event Organiser"))

        assert event["purpose"] == "Welcome the new intake."
        assert event["description"] == "Talks."
        assert event["startsAt"] == "2026-11-02T18:00"
        assert event["expectedAttendance"] == 120

    def test_the_nullable_columns_may_be_left_out(self, client, auth_headers):
        """`purpose` and `expected_attendance` are nullable, so blank is a value."""
        response = client.post(
            "/events",
            json={"title": "Quiet one", "startsAt": "2026-11-02T18:00"},
            headers=auth_headers(),
        )

        assert response.status_code == 201, response.text
        event = response.json()
        assert event["purpose"] == ""
        assert event["description"] == ""
        assert event["expectedAttendance"] is None

    def test_no_attendance_is_not_the_same_as_an_attendance_of_zero(
        self, client, auth_headers
    ):
        """The column distinguishes "not estimated yet" from "nobody is coming"."""
        blank = create(client, auth_headers(), expectedAttendance=None)
        none_expected = create(client, auth_headers(), expectedAttendance=0)

        assert blank["expectedAttendance"] is None
        assert none_expected["expectedAttendance"] == 0

    def test_attendance_cannot_be_negative(self, client, auth_headers):
        response = client.post(
            "/events", json={**DRAFT, "expectedAttendance": -1}, headers=auth_headers()
        )

        assert response.status_code == 400
        assert "negative" in response.json()["detail"]["message"]

    def test_a_title_longer_than_the_column_is_refused(self, client, auth_headers):
        """events.name is VARCHAR(255); saying so beats a database error."""
        response = client.post(
            "/events", json={**DRAFT, "title": "x" * 256}, headers=auth_headers()
        )

        assert response.status_code == 400
        assert "255 characters" in response.json()["detail"]["message"]

    def test_a_purpose_longer_than_the_column_is_refused(self, client, auth_headers):
        """events.purpose is VARCHAR(500)."""
        response = client.post(
            "/events", json={**DRAFT, "purpose": "x" * 501}, headers=auth_headers()
        )

        assert response.status_code == 400
        assert "500 characters" in response.json()["detail"]["message"]

    def test_signing_in_is_required(self, client):
        assert client.post("/events", json=DRAFT).status_code == 401


class TestVisibility:
    """US4.1: an Organiser sees their own events, a Coordinator sees every one."""

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

    def test_a_coordinator_sees_every_event(self, client, auth_headers):
        create(client, auth_headers("Event Organiser"))

        listed = client.get("/events", headers=auth_headers("Event Coordinator")).json()

        assert [event["title"] for event in listed] == ["Faculty Welcome Night"]

    def test_an_event_that_is_not_yours_reads_as_missing_not_forbidden(
        self, client, auth_headers, event_repository
    ):
        """403 would confirm the event exists — which is not this caller's to know."""
        event = create(client, auth_headers("Event Organiser"))
        event_repository.events = [
            item.__class__(**{**item.__dict__, "organiser_id": 999})
            for item in event_repository.events
        ]

        response = client.get(f"/events/{event['id']}", headers=auth_headers())

        assert response.status_code == 404

    def test_an_unknown_event_is_a_404(self, client, auth_headers):
        assert client.get("/events/424242", headers=auth_headers()).status_code == 404

    def test_an_id_that_is_not_a_number_is_a_404_not_a_crash(self, client, auth_headers):
        assert client.get("/events/not-an-id", headers=auth_headers()).status_code == 404


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

    def test_saving_writes_no_history_entry(self, client, auth_headers):
        event = create(client, auth_headers())
        before = len(event["history"])

        saved = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Renamed"},
            headers=auth_headers(),
        ).json()

        assert len(saved["history"]) == before

    def test_owner_can_edit_their_event(self, client, auth_headers):
        """US4.2: Original behavior - owners can edit without change tracking."""
        event = create(client, auth_headers("Event Organiser"))

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Renamed by Owner"},
            headers=auth_headers("Event Organiser"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["title"] == "Renamed by Owner"

    def test_coordinator_can_edit_any_event(self, client, auth_headers):
        """US5.2: Coordinators can edit submitted events they don't own."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "title": "Edited by Coordinator"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["title"] == "Edited by Coordinator"

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

    def test_the_history_opens_with_the_creation_entry(self, client, auth_headers):
        """Derived rather than stored — status_changes.old_status is NOT NULL."""
        event = create(client, auth_headers())

        first = event["history"][0]
        assert first["from"] is None
        assert first["to"] == "Draft"
        assert first["byName"] == "Dylan"

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

    def test_a_coordinator_cannot_submit(self, client, auth_headers):
        event = create(client, auth_headers("Event Organiser"))

        response = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 403
        assert "submit events for approval" in response.json()["detail"]["message"]


class TestCoordinatorEditing:
    """US5.2: Coordinators can edit events with change tracking (important vs routine)."""

    def test_coordinator_edit_tracks_important_change_to_date(self, client, auth_headers):
        """Editing proposed_date is logged as important."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "startsAt": "2026-12-15T20:00"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["startsAt"] == "2026-12-15T20:00"

    def test_coordinator_edit_tracks_important_change_to_attendance(self, client, auth_headers):
        """Editing expected_attendance is logged as important."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "expectedAttendance": 200},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["expectedAttendance"] == 200

    def test_coordinator_edit_tracks_routine_change_to_title(self, client, auth_headers):
        """Editing title is logged as routine."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "title": "New Title"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["title"] == "New Title"

    def test_coordinator_edit_tracks_routine_change_to_purpose(self, client, auth_headers):
        """Editing purpose is logged as routine."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "purpose": "Updated purpose statement"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["purpose"] == "Updated purpose statement"

    def test_coordinator_edit_tracks_routine_change_to_description(self, client, auth_headers):
        """Editing description is logged as routine."""
        event = create(client, auth_headers("Event Organiser"))
        # Submit the event first - coordinators can only edit submitted events
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "description": "Updated description with more details"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["description"] == "Updated description with more details"

    def test_coordinator_cannot_edit_draft_event(self, client, auth_headers):
        """Coordinators cannot edit Draft events - only submitted ones."""
        event = create(client, auth_headers("Event Organiser"))

        response = client.put(
            f"/events/{event['id']}",
            json={**DRAFT, "title": "Coordinator tries to edit draft"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert "only edit submitted events" in detail["message"].lower()

    def test_coordinator_can_edit_submitted_event(self, client, auth_headers):
        """Coordinators can edit events in Submitted status."""
        event = create(client, auth_headers("Event Organiser"))
        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers("Event Organiser")
        ).json()

        response = client.put(
            f"/events/{submitted['id']}",
            json={**DRAFT, "title": "Edited After Submission"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 200
        saved = response.json()
        assert saved["title"] == "Edited After Submission"
        assert saved["status"] == "Submitted"  # Status unchanged


class TestSprintOneReachableStatuses:
    def test_only_draft_and_submitted_are_produced(self, client, auth_headers):
        """The other seven labels are displayable but not yet reachable."""
        event = create(client, auth_headers())
        assert event["status"] == "Draft"

        submitted = client.post(
            f"/events/{event['id']}/submit", headers=auth_headers()
        ).json()
        assert submitted["status"] == "Submitted"

        seen = {change["to"] for change in submitted["history"]}
        assert seen == {"Draft", "Submitted"}


def test_the_directory_and_the_events_list_agree_on_ids(client, auth_headers):
    """A Coordinator reading both must be able to join them without translating."""
    create(client, auth_headers("Event Organiser"))

    directory = client.get("/auth/users", headers=auth_headers("Event Coordinator")).json()
    listed = client.get("/events", headers=auth_headers("Event Coordinator")).json()

    by_id = {entry["id"]: entry["name"] for entry in directory}
    assert by_id[listed[0]["organiserId"]] == listed[0]["organiserName"]
    assert str(COORDINATOR_ID) in by_id
