"""US1.4 — Coordinator Lead and Safety Officer authentication and access.

AC2: Login sends each role to its own landing view.
AC3: US1.3's baseline access rule applies to both.
"""

from tests.conftest import ACCOUNTS, PASSWORD


class TestUS14LoginRouting:
    """US1.4 AC2: Each new role has its own landing view."""

    def test_coordinator_lead_can_sign_in(self, client):
        """Lead can authenticate and get a session."""
        response = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Event Coordinator Lead"], "password": PASSWORD},
        )
        assert response.status_code == 200
        session = response.json()
        assert session["role"] == "Event Coordinator Lead"
        assert "token" in session

    def test_safety_officer_can_sign_in(self, client):
        """Safety Officer can authenticate and get a session."""
        response = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Safety Officer"], "password": PASSWORD},
        )
        assert response.status_code == 200
        session = response.json()
        assert session["role"] == "Safety Officer"
        assert "token" in session

    def test_coordinator_lead_home_route_is_unassigned_queue(self, client):
        """US1.4 AC2 + US8.2: Lead's home is /unassigned-queue."""
        response = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Event Coordinator Lead"], "password": PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["home"] == "/unassigned-queue"

    def test_safety_officer_home_route_is_safety_review(self, client):
        """US1.4 AC2 + US17.1: Safety Officer's home is /safety-review."""
        response = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Safety Officer"], "password": PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["home"] == "/safety-review"

    def test_existing_roles_home_routes_unchanged(self, client):
        """US1.4: Existing role home routes stay the same (regression)."""
        organiser = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD},
        )
        assert organiser.json()["home"] == "/events"

        coordinator = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Event Coordinator"], "password": PASSWORD},
        )
        assert coordinator.json()["home"] == "/events"

        venue_staff = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Venue Staff"], "password": PASSWORD},
        )
        assert venue_staff.json()["home"] == "/venues"


class TestUS14AccessEnforcement:
    """US1.4 AC3: New roles follow US1.3 access blocking patterns."""

    def test_coordinator_lead_blocked_from_venue_staff_routes(self, client, auth_headers):
        """Lead cannot create venues (Venue Staff permission)."""
        response = client.post(
            "/venues",
            json={"name": "Test Hall", "capacity": 100, "location": "Campus"},
            headers=auth_headers("Event Coordinator Lead"),
        )
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert "cannot add a venue" in detail["message"]

    def test_safety_officer_blocked_from_coordinator_routes(self, client, auth_headers):
        """Safety Officer cannot review events (Coordinator permission)."""
        # Safety Officer doesn't have EVENTS_REVIEW permission
        # Trying to access coordinator-only permissions should fail
        # For now, test they can't access /auth/users (requires USERS_READ which they don't have)
        response = client.get("/auth/users", headers=auth_headers("Safety Officer"))
        assert response.status_code == 403

    def test_regular_coordinator_blocked_from_lead_routes(self, client, auth_headers):
        """Regular Coordinators can't access Lead-only permissions.

        This will be fully tested once US8.2's unassigned queue route exists.
        For now, we verify permissions are separate."""
        from app.permissions import Permission, Role, permissions_for

        lead_perms = permissions_for(Role.COORDINATOR_LEAD)
        coord_perms = permissions_for(Role.COORDINATOR)

        # Lead has permissions Coordinator doesn't
        assert Permission.QUEUE_VIEW_UNASSIGNED in lead_perms
        assert Permission.QUEUE_VIEW_UNASSIGNED not in coord_perms
        assert Permission.COORDINATORS_ASSIGN in lead_perms
        assert Permission.COORDINATORS_ASSIGN not in coord_perms

    def test_lead_and_safety_officer_permissions_are_separate(self, client):
        """Lead can't do Safety Officer things and vice versa."""
        from app.permissions import Permission, Role, permissions_for

        lead_perms = permissions_for(Role.COORDINATOR_LEAD)
        safety_perms = permissions_for(Role.SAFETY_OFFICER)

        # No overlap except maybe future shared ones
        assert Permission.SAFETY_REVIEW not in lead_perms
        assert Permission.QUEUE_VIEW_UNASSIGNED not in safety_perms
        assert Permission.COORDINATORS_ASSIGN not in safety_perms
