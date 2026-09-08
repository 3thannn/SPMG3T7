"""US1.1 — Login.

Valid credentials grant access and redirect to a role-appropriate view. Invalid
credentials show a clear error. A session stays active during normal use and
expires after a defined inactivity period.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import auth
from app.sessions import SessionStore
from tests.conftest import ACCOUNTS, PASSWORD


def test_valid_credentials_return_a_session(client):
    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["email"] == ACCOUNTS["Event Organiser"]
    assert body["name"] == "Dylan"
    assert body["role"] == "Event Organiser"


def test_the_role_comes_from_the_account_and_is_not_chosen_at_sign_in(sign_in):
    assert sign_in("Event Organiser")["role"] == "Event Organiser"
    assert sign_in("Event Coordinator")["role"] == "Event Coordinator"


def test_the_password_is_never_echoed_back(client):
    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD}
    )
    assert PASSWORD not in response.text
    assert "password" not in response.json()


@pytest.mark.parametrize(
    ("role", "home"),
    [("Event Organiser", "/events"), ("Event Coordinator", "/events")],
)
def test_each_role_is_told_where_its_own_view_is(sign_in, role, home):
    """"Redirect to a role-appropriate view" — the server decides where.

    Both roles work from the events list today, so both land there. The point
    under test is that the destination comes from the account rather than being
    hardcoded in the client.
    """
    assert sign_in(role)["home"] == home


def test_the_session_carries_the_permissions_the_role_holds(sign_in):
    organiser = sign_in("Event Organiser")["permissions"]
    coordinator = sign_in("Event Coordinator")["permissions"]

    assert "events:create" in organiser
    assert "events:review" not in organiser
    assert "events:review" in coordinator
    assert "events:create" not in coordinator


def test_two_sign_ins_get_two_different_tokens(sign_in):
    assert sign_in("Event Organiser")["token"] != sign_in("Event Organiser")["token"]


def test_a_wrong_password_is_rejected(client):
    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"
    assert response.json()["detail"]["message"] == "Incorrect email or password."


def test_an_unknown_email_is_rejected_the_same_way_as_a_wrong_password(client):
    """A different message here would say which addresses have accounts."""
    unknown = client.post(
        "/auth/login", json={"email": "nobody@spmg3t7.edu", "password": PASSWORD}
    )
    wrong = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": "wrong"}
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_a_rejected_sign_in_issues_no_session(client):
    client.post("/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": "wrong"})
    assert auth.store.active_count() == 0


def test_the_email_is_matched_without_case_or_padding(client):
    response = client.post(
        "/auth/login",
        json={"email": f"  {ACCOUNTS['Event Organiser'].upper()}  ", "password": PASSWORD},
    )
    assert response.status_code == 200


def test_the_password_is_matched_exactly(client):
    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD.upper()}
    )
    assert response.status_code == 401


def test_a_request_missing_a_field_is_a_validation_error_not_a_sign_in(client):
    payload = {"email": ACCOUNTS["Event Organiser"]}
    assert client.post("/auth/login", json=payload).status_code == 422


def test_the_session_survives_normal_use(client, auth_headers):
    headers = auth_headers("Event Organiser")

    for _ in range(5):
        assert client.get("/auth/me", headers=headers).status_code == 200


def test_the_client_is_told_how_long_the_idle_window_is(sign_in):
    """The frontend signs out at the same threshold, so it reads it from here."""
    assert sign_in("Event Organiser")["idleMinutes"] == 30


def test_the_session_expires_after_the_inactivity_period(client, monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(
        auth, "store", SessionStore(idle_timeout=timedelta(minutes=30), clock=clock)
    )

    token = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).status_code == 200

    clock.advance(minutes=31)

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"
    assert "inactivity" in response.json()["detail"]["message"]


def test_an_expired_session_is_not_confused_with_a_bad_password(client, monkeypatch):
    """Being idle is not the same as getting your password wrong; say so."""
    clock = _FakeClock()
    monkeypatch.setattr(
        auth, "store", SessionStore(idle_timeout=timedelta(minutes=30), clock=clock)
    )
    token = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": PASSWORD}
    ).json()["token"]
    clock.advance(minutes=31)

    code = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "detail"
    ]["code"]
    assert code == "session_expired"
    assert code != "invalid_credentials"


class _FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)
