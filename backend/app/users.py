"""The user directory.

There is no database yet (that is US6.3), so accounts live in a dict seeded at
import time. Every lookup goes through this module, so replacing the dict with
a table is a change here and nowhere else.

The seeded accounts are development credentials, documented in the README so the
team can sign in as each role. They are not secrets and must not survive into a
deployed environment — SEED_PASSWORD overrides the shared password, and seeding
should be dropped entirely once accounts can be created (US1.4).
"""

from dataclasses import dataclass

from app.config import seed_password
from app.permissions import Permission, Role, permissions_for
from app.security import hash_password, verify_password


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    role: Role
    password_hash: str

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)


# (id, email, display name, role). The Organiser's id matches the owner of the
# seeded events in the frontend's event store, so signing in as them shows the
# Sprint 1 demonstration data as their own.
SEED_ACCOUNTS: tuple[tuple[str, str, str, Role], ...] = (
    ("user_organiser", "organiser@spmg3t7.edu", "Dylan", Role.ORGANISER),
    ("user_coordinator", "coordinator@spmg3t7.edu", "Priya", Role.COORDINATOR),
)

_users: dict[str, User] = {}


def _normalise(email: str) -> str:
    """Email addresses are matched case-insensitively and without stray space."""
    return email.strip().lower()


def _seed() -> None:
    password = seed_password()
    for user_id, email, name, role in SEED_ACCOUNTS:
        _users[_normalise(email)] = User(
            id=user_id,
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(password),
        )


_seed()

# One throwaway hash, used to spend the same time on an unknown email as on a
# known one so the response time cannot be used to discover who has an account.
_DUMMY_HASH = hash_password("this password matches nothing")


def get_by_email(email: str) -> User | None:
    return _users.get(_normalise(email))


def get_by_id(user_id: str) -> User | None:
    return next((user for user in _users.values() if user.id == user_id), None)


def list_users() -> list[User]:
    return sorted(_users.values(), key=lambda user: (str(user.role), user.name))


def authenticate(email: str, password: str) -> User | None:
    """Return the user when the credentials match, otherwise None."""
    user = get_by_email(email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
