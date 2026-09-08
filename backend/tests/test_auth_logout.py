"""US1.2 — Logout.

Logout ends the session immediately. Subsequent requests require
re-authentication.
"""

from tests.conftest import ACCOUNTS, PASSWORD


def test_logout_succeeds_for_a_signed_in_user(client, auth_headers):
    assert client.post("/auth/logout", headers=auth_headers("Event Organiser")).status_code == 204


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


def test_the_new_session_after_signing_back_in_is_a_different_one(client, sign_in):
    first = sign_in("Event Organiser")["token"]
    client.post("/auth/logout", headers={"Authorization": f"Bearer {first}"})

    assert sign_in("Event Organiser")["token"] != first


def test_logging_out_of_one_device_leaves_the_other_signed_in(client, sign_in):
    """Signing out of a shared machine must not sign you out of your phone."""
    phone = sign_in("Event Organiser")["token"]
    library_pc = sign_in("Event Organiser")["token"]

    client.post("/auth/logout", headers={"Authorization": f"Bearer {library_pc}"})

    assert client.get(
        "/auth/me", headers={"Authorization": f"Bearer {phone}"}
    ).status_code == 200


def test_logging_out_twice_is_not_an_error(client, auth_headers):
    """The second attempt leaves you signed out, which is what was asked for."""
    headers = auth_headers("Event Organiser")

    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.post("/auth/logout", headers=headers).status_code == 204


def test_logging_out_without_a_token_is_not_an_error(client):
    assert client.post("/auth/logout").status_code == 204


def test_the_ended_session_is_released_rather_than_left_behind(client, auth_headers):
    from app import auth

    headers = auth_headers("Event Organiser")
    assert auth.store.active_count() == 1

    client.post("/auth/logout", headers=headers)

    assert auth.store.active_count() == 0
