import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import DEFAULT_SEED_PASSWORD
from app.main import app

PASSWORD = DEFAULT_SEED_PASSWORD

ACCOUNTS = {
    "Organiser": "organiser@spmg3t7.edu",
    "Coordinator": "coordinator@spmg3t7.edu",
}


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

    def _sign_in(role: str = "Organiser", password: str = PASSWORD) -> dict:
        response = client.post(
            "/auth/login", json={"email": ACCOUNTS[role], "password": password}
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _sign_in


@pytest.fixture
def auth_headers(sign_in):
    """Bearer headers for a signed-in role."""

    def _headers(role: str = "Organiser") -> dict[str, str]:
        return {"Authorization": f"Bearer {sign_in(role)['token']}"}

    return _headers
