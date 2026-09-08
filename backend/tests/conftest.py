"""Shared fixtures.

The suite runs against an in-memory user store, not Supabase. That is not a
shortcut: these tests are about the rules — who may sign in, what a role may do,
when a session lapses — and none of that is made truer by a network round trip.
It also means CI needs no Supabase credentials, so the checks stay runnable on
a fork and on a machine that has never seen the project's .env.

The accounts below mirror what `python -m app.seed` writes, so a test that signs
in as an Organiser is signing in as the same person the developer sees in their
browser. `passwords` stands in for Supabase Auth: in the real system the
credential lives in `auth.users` and the profile in `public.users`, joined on
email, and the in-memory store keeps that same split rather than pretending the
password is a column on the user.
"""

import pytest
from fastapi.testclient import TestClient

from app import auth, event_store
from app.config import DEFAULT_SEED_PASSWORD
from app.event_store import InMemoryEvents
from app.main import app
from app.permissions import Role
from app.users import InMemoryUsers, User, use_repository

PASSWORD = DEFAULT_SEED_PASSWORD

ACCOUNTS = {
    "Event Organiser": "organiser@spmg3t7.edu",
    "Event Coordinator": "coordinator@spmg3t7.edu",
}

ORGANISER_ID = 1
COORDINATOR_ID = 2


def seed_users() -> list[User]:
    """Fresh User objects, so a test that mutates the list cannot affect another."""
    return [
        User(
            id=ORGANISER_ID,
            email=ACCOUNTS["Event Organiser"],
            name="Dylan",
            role=Role.ORGANISER,
        ),
        User(
            id=COORDINATOR_ID,
            email=ACCOUNTS["Event Coordinator"],
            name="Priya",
            role=Role.COORDINATOR,
        ),
    ]


@pytest.fixture(autouse=True)
def user_store():
    """Point the user directory at memory for every test, and put it back after."""
    store = InMemoryUsers(
        users=seed_users(),
        passwords={email: PASSWORD for email in ACCOUNTS.values()},
    )
    previous = use_repository(store)
    yield store
    use_repository(previous)


@pytest.fixture(autouse=True)
def event_repository():
    """An empty event store per test, knowing the seeded users' display names."""
    store = InMemoryEvents(
        names={ORGANISER_ID: "Dylan", COORDINATOR_ID: "Priya"},
    )
    previous = event_store.use_repository(store)
    yield store
    event_store.use_repository(previous)


@pytest.fixture
def client():
    """A client over a store with no sessions left behind by another test."""
    auth.store.clear()
    with TestClient(app) as test_client:
        yield test_client
    auth.store.clear()


@pytest.fixture
def sign_in(client):
    """Sign in as a role and return its session payload."""

    def _sign_in(role: str = "Event Organiser", password: str = PASSWORD) -> dict:
        response = client.post(
            "/auth/login", json={"email": ACCOUNTS[role], "password": password}
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _sign_in


@pytest.fixture
def auth_headers(sign_in):
    """Bearer headers for a signed-in role."""

    def _headers(role: str = "Event Organiser") -> dict[str, str]:
        return {"Authorization": f"Bearer {sign_in(role)['token']}"}

    return _headers
