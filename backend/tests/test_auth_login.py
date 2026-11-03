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


@pytest.mark.parametrize(
    ("role", "home"),
    [
        ("Event Organiser", "/events"),
        ("Event Coordinator", "/events"),
        ("Event Coordinator Lead", "/unassigned-queue"),
        ("Venue Staff", "/venues"),
        ("Safety Officer", "/safety-review"),
        ("Technical Support", "/equipment-requests"),
        ("Attendee", "/attend"),
    ],
)
def test_each_role_is_told_where_its_own_view_is(sign_in, role, home):
    """US1.1 AC1, US1.4 AC1-AC2: every role signs in and lands on its own view.

    The destination comes from the account on the server, not from the client:
    the Lead lands on the unassigned queue and the Safety Officer on the safety
    review queue (US1.4), each other role on the page its work starts from.
    """
    session = sign_in(role)

    assert session["role"] == role
    assert session["token"]
    assert session["home"] == home






def test_a_wrong_password_is_rejected(client):
    response = client.post(
        "/auth/login", json={"email": ACCOUNTS["Event Organiser"], "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"
    assert response.json()["detail"]["message"] == "Incorrect email or password."
    # US1.1 AC2: "do not grant access" - no session exists afterwards.
    assert auth.store.active_count() == 0
















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




class _FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)
