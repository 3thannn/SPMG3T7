"""US1.3 — Baseline access enforcement.

Out-of-role access attempts are blocked, and a clear message explains the
denial. /auth/users is the first route behind the permission layer, so it is
what these tests push against.
"""

from app.permissions import Role


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








def test_a_made_up_token_is_refused(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer made-up-token"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"








        # Safety Officer permissions will be defined in US17.x
        # For now, just needs to be defined (can be empty)
