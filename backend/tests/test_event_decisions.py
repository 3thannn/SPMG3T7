"""US7.1 decisions and US4.3's status-transition allowlist."""

import pytest

from app import supabase_client
from app.event_status import EventStatus, transition_allowed
from app.event_store import Event, StaleEventStatus, SupabaseEvents
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
}


def under_review_event(client, auth_headers) -> dict:
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text
    reviewed = client.post(
        f"/events/{event_id}/clarification",
        json={"message": "Please confirm the final plan."},
        headers=auth_headers("Event Coordinator"),
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def decide(client, headers, event_id: str, decision: str, reason: str = "Not feasible."):
    body = {"reason": reason} if decision == "reject" else None
    return client.post(f"/events/{event_id}/{decision}", json=body, headers=headers)


def seeded_event(event_repository, status: EventStatus) -> Event:
    event = Event(
        id=900,
        title="Seeded event",
        purpose="Testing",
        description="",
        starts_at="2027-11-02T18:00",
        ends_at="2027-11-02T21:00",
        expected_attendance=20,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2026-01-01T09:00:00",
        updated_at="2026-01-01T09:00:00",
        coordinator_id=COORDINATOR_ID,
    )
    event_repository.events.append(event)
    return event


class TestTransitionRules:
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
        ],
    )
    def test_allowed_transitions(self, before, after):
        assert transition_allowed(from_status=before, to_status=after)

    def test_every_other_real_transition_is_blocked(self):
        allowed = {
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
        }
        for before in EventStatus:
            for after in EventStatus:
                expected = before == after or (before, after) in allowed
                assert transition_allowed(from_status=before, to_status=after) is expected

    def test_same_status_is_not_treated_as_a_transition(self):
        assert transition_allowed(
            from_status=EventStatus.UNDER_REVIEW,
            to_status=EventStatus.UNDER_REVIEW,
        )


class TestDecisionHappyPaths:
    def test_assigned_coordinator_approves_under_review_event(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = decide(client, auth_headers("Event Coordinator"), event["id"], "approve")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Approved"

    def test_assigned_coordinator_rejects_with_reason(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = decide(
            client,
            auth_headers("Event Coordinator"),
            event["id"],
            "reject",
            "The safety plan is incomplete.",
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Rejected"
        assert response.json()["history"][-1]["notes"] == "The safety plan is incomplete."

    @pytest.mark.parametrize(
        ("decision", "expected", "notes"),
        [("approve", "Approved", ""), ("reject", "Rejected", "Not feasible.")],
    )
    def test_decision_is_timestamped_and_attributable(
        self, client, auth_headers, decision, expected, notes
    ):
        event = under_review_event(client, auth_headers)

        response = decide(client, auth_headers("Event Coordinator"), event["id"], decision)

        latest = response.json()["history"][-1]
        assert latest == {
            "from": "Under Review",
            "to": expected,
            "at": latest["at"],
            "byId": str(COORDINATOR_ID),
            "byName": "Priya",
            "notes": notes,
            "kind": "",
        }
        assert latest["at"]

    def test_organiser_can_read_rejection_reason(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        decide(client, auth_headers("Event Coordinator"), event["id"], "reject", "No capacity.")

        response = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Organiser")
        )

        assert response.json()["status"] == "Rejected"
        assert response.json()["history"][-1]["notes"] == "No capacity."


class TestAtomicDecisionStore:
    class FakeRpcCall:
        def __init__(self, data: bool):
            self.data = data

        def execute(self):
            return self

    class FakeAdmin:
        def __init__(self, data: bool):
            self.data = data
            self.calls: list[tuple[str, dict]] = []

        def rpc(self, name: str, params: dict):
            self.calls.append((name, params))
            return TestAtomicDecisionStore.FakeRpcCall(self.data)

        def table(self, _name: str):
            raise AssertionError("decisions must not use separate table requests")

    def test_decision_uses_one_rpc_for_status_and_audit(self, monkeypatch):
        admin = self.FakeAdmin(True)
        decided = Event(
            id=901,
            title="Atomic decision",
            purpose="Testing",
            description="",
            starts_at="2027-11-02T18:00",
            ends_at="2027-11-02T21:00",
            expected_attendance=20,
            status=EventStatus.REJECTED,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="2026-01-01T09:00:00",
            updated_at="2026-01-01T09:01:00",
            coordinator_id=COORDINATOR_ID,
        )
        store = SupabaseEvents()
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _event_id: decided)

        result = store.decide_event(
            decided.id,
            actor_id=COORDINATOR_ID,
            from_status=EventStatus.UNDER_REVIEW,
            to_status=EventStatus.REJECTED,
            reason="No capacity.",
        )

        assert result is decided
        assert admin.calls == [
            (
                "decide_event_status",
                {
                    "p_event_id": decided.id,
                    "p_expected_status": "Under Review",
                    "p_new_status": "Rejected",
                    "p_changed_by_id": COORDINATOR_ID,
                    "p_notes": "No capacity.",
                },
            )
        ]

    def test_rpc_compare_and_set_failure_is_reported_as_stale(self, monkeypatch):
        admin = self.FakeAdmin(False)
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)

        with pytest.raises(StaleEventStatus):
            SupabaseEvents().decide_event(
                901,
                actor_id=COORDINATOR_ID,
                from_status=EventStatus.UNDER_REVIEW,
                to_status=EventStatus.APPROVED,
                reason="",
            )

        assert len(admin.calls) == 1


class TestDecisionNegativeCases:
    def test_draft_is_not_visible_to_a_coordinator(self, client, auth_headers):
        created = client.post("/events", json=DRAFT, headers=auth_headers("Event Organiser"))

        response = decide(
            client,
            auth_headers("Event Coordinator"),
            created.json()["id"],
            "approve",
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "event_status",
        [
            EventStatus.SUBMITTED,
            EventStatus.APPROVED,
            EventStatus.REJECTED,
            EventStatus.PLANNING,
            EventStatus.CONFIRMED,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        ],
    )
    @pytest.mark.parametrize("decision", ["approve", "reject"])
    def test_only_under_review_can_be_decided(
        self, client, auth_headers, event_repository, event_status, decision
    ):
        event = seeded_event(event_repository, event_status)

        response = decide(client, auth_headers("Event Coordinator"), str(event.id), decision)

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"
        assert event_repository.get_event(event.id).status is event_status
        assert event_repository.get_event(event.id).history == ()

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
    def test_rejection_reason_is_required(self, client, auth_headers, reason):
        event = under_review_event(client, auth_headers)

        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", reason
        )

        assert response.status_code == 400
        after = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Organiser")
        ).json()
        assert after["status"] == "Under Review"

    def test_missing_rejection_reason_is_refused(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = client.post(
            f"/events/{event['id']}/reject",
            json={},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 400

    @pytest.mark.parametrize("role", ["Event Organiser", "Venue Staff"])
    @pytest.mark.parametrize("decision", ["approve", "reject"])
    def test_other_roles_cannot_decide(self, client, auth_headers, role, decision):
        event = under_review_event(client, auth_headers)

        response = decide(client, auth_headers(role), event["id"], decision)

        assert response.status_code == 403

    def test_non_assigned_coordinator_cannot_decide(
        self, client, auth_headers, user_store
    ):
        event = under_review_event(client, auth_headers)
        user_store.users.append(
            User(id=10, email="second@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        )
        user_store.passwords["second@spmg3t7.edu"] = "Sprint1!demo"
        login = client.post(
            "/auth/login",
            json={"email": "second@spmg3t7.edu", "password": "Sprint1!demo"},
        ).json()

        response = decide(
            client,
            {"Authorization": f"Bearer {login['token']}"},
            event["id"],
            "approve",
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("decision", ["approve", "reject"])
    def test_decision_requires_a_session(self, client, auth_headers, decision):
        event = under_review_event(client, auth_headers)
        assert decide(client, {}, event["id"], decision).status_code == 401

    def test_signing_out_removes_decision_access(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        client.post("/auth/logout", headers=headers)

        assert decide(client, headers, event["id"], "approve").status_code == 401

    @pytest.mark.parametrize("event_id", ["999999", "not-a-number"])
    def test_missing_event_returns_404(self, client, auth_headers, event_id):
        response = decide(client, auth_headers("Event Coordinator"), event_id, "approve")
        assert response.status_code == 404

    def test_second_decision_is_blocked_without_a_second_entry(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        first = decide(client, headers, event["id"], "approve")

        second = decide(client, headers, event["id"], "reject")

        assert first.status_code == 200
        assert second.status_code == 409
        after = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Organiser")
        ).json()
        decisions = [item for item in after["history"] if item["to"] in ("Approved", "Rejected")]
        assert len(decisions) == 1


class TestRejectionReasonEdges:
    @pytest.mark.parametrize("length", [1, 2000])
    def test_boundary_lengths_are_accepted(self, client, auth_headers, length):
        event = under_review_event(client, auth_headers)
        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", "x" * length
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["history"][-1]["notes"]) == length

    def test_reason_over_limit_is_rejected(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", "x" * 2001
        )
        assert response.status_code == 400

    def test_unicode_multiline_reason_is_trimmed_only_at_edges(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        reason = "  Budget unavailable â€” è¯·ä¿®æ”¹.\n  Keep this spacing.  "

        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", reason
        )

        assert response.status_code == 200, response.text
        assert response.json()["history"][-1]["notes"] == reason.strip()

    def test_punctuation_only_is_a_meaningful_reason(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", "Not safe?!"
        )

        assert response.status_code == 200, response.text
        assert response.json()["history"][-1]["notes"] == "Not safe?!"
