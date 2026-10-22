"""US1.3 — Baseline access enforcement.

Out-of-role access attempts are blocked, and a clear message explains the
denial. /auth/users is the first route behind the permission layer, so it is
what these tests push against.
"""

from app.permissions import Permission, Role, denial_message, permissions_for, roles_with


def test_an_allowed_role_gets_through(client, auth_headers):
    response = client.get("/auth/users", headers=auth_headers("Event Coordinator"))

    assert response.status_code == 200
    assert {entry["role"] for entry in response.json()} == {str(role) for role in Role}


def test_an_out_of_role_request_is_blocked(client, auth_headers):
    """An Organiser is signed in and legitimate, and still may not read this."""
    assert client.get("/auth/users", headers=auth_headers("Event Organiser")).status_code == 403


def test_the_denial_says_what_was_refused_and_who_may_do_it(client, auth_headers):
    detail = client.get("/auth/users", headers=auth_headers("Event Organiser")).json()["detail"]

    assert detail["code"] == "forbidden"
    # US1.4: Coordinator Lead also has USERS_READ, so message now lists both
    assert detail["message"] == (
        "The Event Organiser role cannot view the user directory. "
        "That is available to: Event Coordinator, Event Coordinator Lead."
    )
    assert detail["role"] == "Event Organiser"
    assert detail["required"] == "users:read"


def test_a_blocked_request_returns_none_of_the_data_it_guarded(client, auth_headers):
    body = client.get("/auth/users", headers=auth_headers("Event Organiser")).text

    assert "coordinator@spmg3t7.edu" not in body


def test_being_signed_out_and_being_out_of_role_are_different_answers(client, auth_headers):
    """401 means sign in; 403 means signing in again will not help."""
    assert client.get("/auth/users").status_code == 401
    assert client.get("/auth/users", headers=auth_headers("Event Organiser")).status_code == 403


def test_a_missing_token_asks_the_caller_to_sign_in(client):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"
    assert response.json()["detail"]["message"] == "Sign in to continue."


def test_a_made_up_token_is_refused(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer made-up-token"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"


def test_a_malformed_authorization_header_is_refused(client):
    for header in ("", "Bearer", "Basic abc123", "token abc123"):
        response = client.get("/auth/me", headers={"Authorization": header})
        assert response.status_code == 401, header


def test_the_health_check_stays_open_to_everyone(client):
    """Enforcement must not lock out the probe the frontend uses on load."""
    assert client.get("/health").status_code == 200


class TestPermissionCatalogue:
    """The rules themselves, independent of any route that applies them."""

    def test_every_role_has_a_defined_permission_set(self):
        for role in Role:
            assert permissions_for(role), f"{role} has no permissions"

    def test_no_role_holds_every_permission(self):
        for role in Role:
            assert permissions_for(role) != set(Permission)

    def test_organisers_and_coordinators_hold_different_things(self):
        # US10.2: both read their own notifications. US4.6: both may cancel an
        # event (their own, or one assigned to them). They share nothing else.
        shared = permissions_for(Role.ORGANISER) & permissions_for(Role.COORDINATOR)
        assert shared == {Permission.NOTIFICATIONS_READ, Permission.EVENTS_CANCEL}

    def test_only_organisers_create_and_submit_events(self):
        assert roles_with(Permission.EVENTS_CREATE) == [Role.ORGANISER]
        assert roles_with(Permission.EVENTS_SUBMIT) == [Role.ORGANISER]

    def test_only_coordinators_review_events(self):
        assert roles_with(Permission.EVENTS_REVIEW) == [Role.COORDINATOR]

    def test_every_permission_belongs_to_at_least_one_role(self):
        orphans = [item for item in Permission if not roles_with(item)]
        assert orphans == []

    def test_every_permission_can_be_named_in_a_denial(self):
        for permission in Permission:
            message = denial_message(Role.ORGANISER, permission)
            assert str(permission) not in message, f"{permission} has no readable label"
            assert message.startswith("The Event Organiser role cannot ")


class TestUS14NewRoles:
    """US1.4: Coordinator Lead and Safety Officer roles exist."""

    def test_coordinator_lead_is_a_valid_role(self):
        """US1.4 AC1: Coordinator Lead role exists."""
        assert hasattr(Role, "COORDINATOR_LEAD")
        assert Role.COORDINATOR_LEAD == "Event Coordinator Lead"

    def test_safety_officer_is_a_valid_role(self):
        """US1.4 AC1: Safety Officer role exists."""
        assert hasattr(Role, "SAFETY_OFFICER")
        assert Role.SAFETY_OFFICER == "Safety Officer"

    def test_coordinator_lead_has_defined_permissions(self):
        """US1.4 AC1: Lead has a permission set."""
        perms = permissions_for(Role.COORDINATOR_LEAD)
        assert perms is not None
        # Lead needs at least permission to view unassigned queue (US8.2)
        # Exact permissions will be defined when we know what Lead can do

    def test_safety_officer_has_defined_permissions(self):
        """US1.4 AC1: Safety Officer has a permission set."""
        perms = permissions_for(Role.SAFETY_OFFICER)
        assert perms is not None
        # Safety Officer permissions will be defined in US17.x
        # For now, just needs to be defined (can be empty)
