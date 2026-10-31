"""The Supabase settings and the clients built from them.

Every test sets or clears the variables it depends on, so the suite behaves the
same whether or not the developer running it has a real backend/.env on disk.
"""

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app import supabase_client
from app.config import (
    MissingConfig,
    supabase_anon_key,
    supabase_configured,
    supabase_db_url,
    supabase_service_role_key,
    supabase_url,
)

CREDENTIALS = {
    "SUPABASE_URL": "https://demo.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
}


@pytest.fixture
def configured(monkeypatch):
    """A complete, fake set of credentials, and no cached client from before."""
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)
    supabase_client.reset()
    yield
    supabase_client.reset()


def test_reads_each_credential(configured):
    assert supabase_url() == "https://demo.supabase.co"
    assert supabase_anon_key() == "anon-key"
    assert supabase_service_role_key() == "service-role-key"


def test_a_trailing_slash_on_the_url_is_dropped(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co/")
    assert supabase_url() == "https://demo.supabase.co"


@pytest.mark.parametrize(
    ("name", "read"),
    [
        ("SUPABASE_URL", supabase_url),
        ("SUPABASE_ANON_KEY", supabase_anon_key),
        ("SUPABASE_SERVICE_ROLE_KEY", supabase_service_role_key),
    ],
)
def test_a_missing_credential_names_itself_and_says_where_to_put_it(
    monkeypatch, name, read
):
    monkeypatch.delenv(name, raising=False)
    with pytest.raises(MissingConfig) as raised:
        read()
    assert name in str(raised.value)
    assert ".env.example" in str(raised.value)


def test_a_blank_credential_counts_as_missing(monkeypatch):
    """An empty line in .env is a value that was never filled in, not a value."""
    monkeypatch.setenv("SUPABASE_ANON_KEY", "   ")
    with pytest.raises(MissingConfig):
        supabase_anon_key()


def test_the_database_url_is_optional(monkeypatch):
    """PostgREST does not need it; only introspection and migrations do."""
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    assert supabase_db_url() is None
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://postgres:pw@host:5432/postgres")
    assert supabase_db_url() == "postgresql://postgres:pw@host:5432/postgres"


def test_configured_reports_rather_than_raises(monkeypatch, configured):
    assert supabase_configured() is True
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert supabase_configured() is False


def test_the_admin_client_is_cached_and_droppable(configured):
    assert supabase_client.admin() is supabase_client.admin()
    first = supabase_client.admin()
    supabase_client.reset()
    assert supabase_client.admin() is not first


def test_each_anonymous_client_is_its_own(configured):
    """A shared auth client would leak one caller's session into another's."""
    assert supabase_client.anonymous() is not supabase_client.anonymous()


def test_a_user_client_carries_the_callers_token(configured):
    client = supabase_client.as_user("a-user-access-token")
    assert client.postgrest.headers["Authorization"] == "Bearer a-user-access-token"


def test_concurrent_admin_reads_and_writes_use_http1_without_replaying_writes(
    configured, monkeypatch
):
    requests = []
    original_client = httpx.Client

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer service-role-key"
        return httpx.Response(200, json=[{"id": 1}])

    def transport_client(**kwargs):
        assert kwargs["http2"] is False
        return original_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(supabase_client.httpx, "Client", transport_client)
    client = supabase_client.admin()
    transport = client.options.httpx_client

    def query(index):
        if index % 2:
            return client.table("events").insert({"name": f"test-{index}"}).execute()
        return client.table("events").select("id").execute()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(query, range(8)))
    assert len(results) == len(requests) == 8
    assert sum(request.method == "POST" for request in requests) == 4
    supabase_client.reset()
    assert transport.is_closed
