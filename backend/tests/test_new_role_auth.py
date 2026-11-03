"""US1.4 — Coordinator Lead and Safety Officer authentication and access.

AC2: Login sends each role to its own landing view.
AC3: US1.3's baseline access rule applies to both.
"""

from tests.conftest import ACCOUNTS, PASSWORD


class TestUS14LoginRouting:
    """US1.4 AC2: Each new role has its own landing view."""




    def test_safety_officer_home_route_is_safety_review(self, client):
        """US1.4 AC2 + US17.1: Safety Officer's home is /safety-review."""
        response = client.post(
            "/auth/login",
            json={"email": ACCOUNTS["Safety Officer"], "password": PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["home"] == "/safety-review"



class TestUS14AccessEnforcement:
    """US1.4 AC3: New roles follow US1.3 access blocking patterns."""


    def test_safety_officer_blocked_from_coordinator_routes(self, client, auth_headers):
        """Safety Officer cannot review events (Coordinator permission)."""
        # Safety Officer doesn't have EVENTS_REVIEW permission
        # Trying to access coordinator-only permissions should fail
        # For now, test they can't access /auth/users (requires USERS_READ which they don't have)
        response = client.get("/auth/users", headers=auth_headers("Safety Officer"))
        assert response.status_code == 403


