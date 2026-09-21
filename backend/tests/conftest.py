"""Shared fixtures.

The suite runs against an in-memory user store, not Supabase. That is not a
shortcut: these tests are about the rules — who may sign in, what a role may do,
when a session lapses — and none of that is made truer by a network round trip.
It also means CI needs no Supabase credentials, so the checks stay runnable on
a fork and on a machine that has never seen the project's .env.

The accounts below are the suite's own fixtures. `passwords` stands in for
Supabase Auth: in the real system the
credential lives in `auth.users` and the profile in `public.users`, joined on
email, and the in-memory store keeps that same split rather than pretending the
password is a column on the user.
"""

import pytest
from fastapi.testclient import TestClient

from app import auth, event_store, venue_store
from app.event_store import InMemoryEvents
from app.main import app
from app.permissions import Role
from app.users import InMemoryUsers, User, use_repository
from app.venue_store import InMemoryVenues, Venue

#: The password every fixture account signs in with. The suite owns it;
#: nothing outside the tests depends on the value.
PASSWORD = "Sprint1!demo"

ACCOUNTS = {
    "Event Organiser": "organiser@spmg3t7.edu",
    "Event Coordinator": "coordinator@spmg3t7.edu",
    "Venue Staff": "venuestaff@spmg3t7.edu",
}

ORGANISER_ID = 1
COORDINATOR_ID = 2
VENUE_STAFF_ID = 3


def fixture_users() -> list[User]:
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
        # US9.1a-c: the role that maintains the venue catalogue. It holds no
        # event permission, which is what makes it the useful fixture for
        # asserting that a venue route refuses everyone else.
        User(
            id=VENUE_STAFF_ID,
            email=ACCOUNTS["Venue Staff"],
            name="Sam",
            role=Role.VENUE_STAFF,
        ),
    ]


@pytest.fixture(autouse=True)
def user_store():
    """Point the user directory at memory for every test, and put it back after."""
    store = InMemoryUsers(
        users=fixture_users(),
        passwords={email: PASSWORD for email in ACCOUNTS.values()},
    )
    previous = use_repository(store)
    yield store
    use_repository(previous)


@pytest.fixture(autouse=True)
def event_repository():
    """An empty event store per test, knowing the fixture users' display names."""
    store = InMemoryEvents(
        names={ORGANISER_ID: "Dylan", COORDINATOR_ID: "Priya", VENUE_STAFF_ID: "Sam"},
    )
    previous = event_store.use_repository(store)
    yield store
    event_store.use_repository(previous)


#: Three venues, chosen so the US9.3 filters can actually discriminate: two
#: share a location, two share an accessibility feature, and no single filter
#: picks out the same rows as another.
def fixture_venues() -> list[Venue]:
    """Fresh Venue objects, so a test that mutates the list cannot affect another."""
    return [
        Venue(
            id=1,
            name="Great Hall",
            location="Main Campus, Building A",
            capacity=500,
            facilities="Stage, PA system, projector",
            accessibility_features="Step-free access, hearing loop",
            operating_hours="08:00-22:00",
            created_at="2026-01-05T09:00:00",
            updated_at="2026-01-05T09:00:00",
        ),
        Venue(
            id=2,
            name="Bertha Room",
            location="Library, Level 3",
            capacity=40,
            # The nullable columns, left empty on purpose: the catalogue has to
            # render a half-filled record without falling over.
            facilities="",
            accessibility_features="",
            operating_hours="",
            created_at="2026-01-06T09:00:00",
            updated_at="2026-01-06T09:00:00",
        ),
        Venue(
            id=3,
            name="Seminar Room 4",
            # Shares "Library" with Bertha Room, so a location filter alone
            # cannot stand in for a capacity one.
            location="Library, Level 1",
            capacity=60,
            facilities="Boardroom table, screen",
            # Shares "Step-free access" with the Great Hall but not the
            # hearing loop, so accessibility filtering is not all-or-nothing.
            accessibility_features="Step-free access",
            operating_hours="07:30-19:00",
            created_at="2026-01-07T09:00:00",
            updated_at="2026-01-07T09:00:00",
        ),
    ]


@pytest.fixture(autouse=True)
def venue_repository():
    """A venue catalogue in memory for every test, and put the real one back after."""
    store = InMemoryVenues(venues=fixture_venues())
    previous = venue_store.use_repository(store)
    yield store
    venue_store.use_repository(previous)


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
        response = client.post("/auth/login", json={"email": ACCOUNTS[role], "password": password})
        assert response.status_code == 200, response.text
        return response.json()

    return _sign_in


@pytest.fixture
def auth_headers(sign_in):
    """Bearer headers for a signed-in role."""

    def _headers(role: str = "Event Organiser") -> dict[str, str]:
        return {"Authorization": f"Bearer {sign_in(role)['token']}"}

    return _headers
