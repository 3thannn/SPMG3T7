"""US1.2 — Logout.

Logout ends the session immediately. Subsequent requests require
re-authentication.
"""

from tests.conftest import ACCOUNTS, PASSWORD


def test_the_token_stops_working_the_moment_the_session_ends(client, auth_headers):
    headers = auth_headers("Event Organiser")
    assert client.get("/auth/me", headers=headers).status_code == 200

    client.post("/auth/logout", headers=headers)

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"


def test_every_protected_route_refuses_the_ended_session(client, auth_headers):
    headers = auth_headers("Event Coordinator")
    client.post("/auth/logout", headers=headers)

    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/auth/users", headers=headers).status_code == 401


def test_signing_in_again_after_logout_works(client, auth_headers):
    client.post("/auth/logout", headers=auth_headers("Event Organiser"))

    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD}
    )
    assert response.status_code == 200
    assert client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.json()['token']}"}
    ).status_code == 200










