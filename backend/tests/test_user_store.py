"""The Supabase user directory and sign-in, against a fake client.

The rest of the suite signs in through `InMemoryUsers`. These drive
`SupabaseUsers` itself: the lookups it sends to `public.users`, and how it reads
each answer Supabase Auth can give to a sign-in.
"""

from types import SimpleNamespace

import pytest
from supabase import AuthApiError, AuthError

from app import supabase_client, users
from app.permissions import Role
from app.users import TABLE, SupabaseUsers

ROW = {"id": 1, "email": "organiser@spmg3t7.edu", "name": "Dylan", "role": "Event Organiser"}


class FakeAuth:
    """Supabase Auth's sign-in: answers with `outcome`, or raises it."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.attempts: list[dict] = []

    def sign_in_with_password(self, credentials: dict):
        self.attempts.append(credentials)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def auth(monkeypatch):
    """Install a fake Auth client; a test sets `outcome` before signing in."""
    fake_auth = FakeAuth(SimpleNamespace(user=None))
    monkeypatch.setattr(
        supabase_client, "anonymous", lambda: SimpleNamespace(auth=fake_auth)
    )
    return fake_auth


class TestLookups:
    def test_an_address_is_matched_case_insensitively_and_trimmed(self, fake):
        fake.rows = {TABLE: [dict(ROW)]}

        found = SupabaseUsers().get_by_email("  Organiser@SPMG3T7.edu ")

        assert found is not None and found.id == 1
        assert ("ilike", "email", "organiser@spmg3t7.edu") in fake.on(TABLE)[0].calls

    def test_an_unknown_address_is_none(self, fake):
        assert SupabaseUsers().get_by_email("nobody@spmg3t7.edu") is None

    def test_a_user_is_found_by_id(self, fake):
        fake.rows = {TABLE: [dict(ROW)]}

        found = SupabaseUsers().get_by_id(1)

        assert found is not None and found.role is Role.ORGANISER
        assert ("eq", "id", 1) in fake.on(TABLE)[0].calls

    def test_an_unknown_id_is_none(self, fake):
        assert SupabaseUsers().get_by_id(404) is None

    def test_the_directory_is_ordered_by_role_then_name_and_skips_unmodelled_roles(
        self, fake
    ):
        fake.rows = {
            TABLE: [dict(ROW), dict(ROW, id=2, email="x@spmg3t7.edu", role="Caterer")]
        }

        listed = SupabaseUsers().list_users()

        assert [user.id for user in listed] == [1]
        orders = fake.on(TABLE)[0].named("order")
        assert [call[1] for call in orders] == ["role", "name"]

    def test_the_module_reads_through_whichever_store_is_installed(self, fake):
        fake.rows = {TABLE: [dict(ROW)]}
        previous = users.use_repository(SupabaseUsers())
        try:
            found = users.get_by_email("organiser@spmg3t7.edu")
        finally:
            users.use_repository(previous)

        assert found is not None and found.name == "Dylan"


class TestSigningIn:
    def test_a_proven_identity_is_looked_up_by_the_address_auth_returns(self, fake, auth):
        fake.rows = {TABLE: [dict(ROW)]}
        auth.outcome = SimpleNamespace(user=SimpleNamespace(email="organiser@spmg3t7.edu"))

        found = SupabaseUsers().authenticate(" Organiser@spmg3t7.edu", "Sprint1!demo")

        assert found is not None and found.id == 1
        assert auth.attempts == [
            {"email": "organiser@spmg3t7.edu", "password": "Sprint1!demo"}
        ]

    def test_an_auth_user_with_no_email_falls_back_to_the_one_typed(self, fake, auth):
        fake.rows = {TABLE: [dict(ROW)]}
        auth.outcome = SimpleNamespace(user=SimpleNamespace(email=None))

        found = SupabaseUsers().authenticate("organiser@spmg3t7.edu", "Sprint1!demo")

        assert found is not None and found.id == 1

    @pytest.mark.parametrize(
        "refusal",
        [
            AuthApiError("Invalid login credentials", 400, "invalid_credentials"),
            AuthError("Email not confirmed", "email_not_confirmed"),
        ],
        ids=["wrong-password", "unconfirmed"],
    )
    def test_every_auth_refusal_is_the_same_none(self, fake, auth, refusal):
        auth.outcome = refusal

        assert SupabaseUsers().authenticate("organiser@spmg3t7.edu", "wrong") is None
        assert fake.queries == []

    def test_an_answer_with_no_user_is_refused(self, fake, auth):
        auth.outcome = SimpleNamespace(user=None)

        assert SupabaseUsers().authenticate("organiser@spmg3t7.edu", "Sprint1!demo") is None
