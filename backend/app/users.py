"""The user directory, over the Supabase `users` table.

This module reads only the columns the schema already has — `id`, `email`,
`name`, `role`. Nothing here adds to the table, and nothing here stores a
credential.

**Where the password lives.** Supabase Auth holds it, in the `auth.users` table
that Supabase manages. `POST /auth/login` hands the email and password to Auth,
and on success looks the person up here to find out who they are and what they
may do. The two are joined on **email**, which both sides already have — which
is what makes this work without a linking column.

So there are two records per person, with different jobs:

* `auth.users` — can this person prove who they are? Owned by Supabase.
* `public.users` — who are they, and what may they do? Owned by this project.

A row in one without the other is a real state and is handled: someone in
`auth.users` with no profile row cannot sign in (we would not know their role),
and a profile row with no Auth account cannot sign in either (nothing to prove
themselves with). Both are refused the same way as a wrong password.

**Roles.** `users.role` is a Postgres enum with five values. This project models
the three that have features — an Event Organiser proposes events, an Event
Coordinator reviews them and reads the venue catalogue, and Venue Staff
maintain that catalogue. A row holding Technical Support or Attendee is not an
error, it is an account this build has nothing to offer: it is skipped by the
directory and refused at sign-in rather than being forced into a role it does
not have. Venue Staff was in that group until US9.1a-c gave it something to do.

The repository behind these functions is swappable. Tests install an in-memory
one so the suite — and CI, which holds no Supabase credentials — runs without a
database, while the application uses Supabase.
"""

from dataclasses import dataclass, field
from typing import Protocol

from supabase import AuthApiError, AuthError

from app import supabase_client
from app.permissions import Permission, Role, permissions_for

TABLE = "users"
#: Exactly the columns the schema has. There is no credential column.
COLUMNS = "id, email, name, role"


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: Role

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)


def _normalise(email: str) -> str:
    """Email addresses are matched case-insensitively and without stray space."""
    return email.strip().lower()


def to_user(row: dict) -> User | None:
    """Build a User from a table row, or None if this build cannot represent it.

    The one reason to refuse is a role outside the three modelled here. Returning
    None rather than raising keeps one unmodelled account from breaking a query
    that returned it alongside twenty usable ones.
    """
    try:
        role = Role(row["role"])
    except ValueError:
        return None
    return User(id=row["id"], email=row["email"], name=row["name"], role=role)


class Repository(Protocol):
    """What the routes need from a user store, and nothing more."""

    def get_by_email(self, email: str) -> User | None: ...

    def get_by_id(self, user_id: int) -> User | None: ...

    def list_users(self) -> list[User]: ...

    def authenticate(self, email: str, password: str) -> User | None: ...


class SupabaseUsers:
    """The real store: profiles from `public.users`, passwords from Supabase Auth."""

    def get_by_email(self, email: str) -> User | None:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .ilike("email", _normalise(email))
            .limit(1)
            .execute()
        )
        return to_user(response.data[0]) if response.data else None

    def get_by_id(self, user_id: int) -> User | None:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return to_user(response.data[0]) if response.data else None

    def list_users(self) -> list[User]:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .order("role")
            .order("name")
            .execute()
        )
        found = (to_user(row) for row in response.data or [])
        return [user for user in found if user is not None]

    def authenticate(self, email: str, password: str) -> User | None:
        """Check the password with Supabase Auth, then find out who they are.

        The client is a throwaway that persists nothing, so the session Auth
        hands back dies with this call. This API issues its own session token
        instead — see `app.sessions` for why that is worth doing.
        """
        try:
            result = supabase_client.anonymous().auth.sign_in_with_password(
                {"email": _normalise(email), "password": password}
            )
        except (AuthApiError, AuthError):
            # Wrong password, unknown address, unconfirmed email, rate limited.
            # The caller turns all of them into one message on purpose.
            return None

        if result.user is None:
            return None
        # Proven who they are; the profile row says what they may do. No row
        # means no role, and a session without a role is not one we can issue.
        return self.get_by_email(result.user.email or email)


@dataclass
class InMemoryUsers:
    """A stand-in for tests, holding accounts the suite defines itself.

    `passwords` plays the part of Supabase Auth: the credential lives beside the
    directory rather than in it, the same split the real store has.
    """

    users: list[User] = field(default_factory=list)
    passwords: dict[str, str] = field(default_factory=dict)

    def get_by_email(self, email: str) -> User | None:
        wanted = _normalise(email)
        return next((u for u in self.users if _normalise(u.email) == wanted), None)

    def get_by_id(self, user_id: int) -> User | None:
        return next((u for u in self.users if u.id == user_id), None)

    def list_users(self) -> list[User]:
        return sorted(self.users, key=lambda user: (str(user.role), user.name))

    def authenticate(self, email: str, password: str) -> User | None:
        expected = self.passwords.get(_normalise(email))
        if expected is None or expected != password:
            return None
        return self.get_by_email(email)


_repository: Repository = SupabaseUsers()


def use_repository(repository: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository
    return previous


def get_by_email(email: str) -> User | None:
    return _repository.get_by_email(email)


def get_by_id(user_id: int) -> User | None:
    return _repository.get_by_id(user_id)


def list_users() -> list[User]:
    return _repository.list_users()


def authenticate(email: str, password: str) -> User | None:
    """Return the user when the credentials check out, otherwise None."""
    return _repository.authenticate(email, password)
