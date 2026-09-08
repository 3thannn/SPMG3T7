"""Environment-driven settings.

Values come from the process environment, with `backend/.env` loaded first for
local development. `.env` never overrides a variable that is already set, so CI
and a deployed environment keep control of their own configuration, and a test
that sets a variable still wins over whatever happens to be on the developer's
disk.

Supabase credentials have no defaults on purpose. A wrong-but-plausible default
would let the API start and then fail on the first query; a missing one is named
here, at the point of use, pointing at `.env.example`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_SESSION_IDLE_MINUTES = 30
DEFAULT_SEED_PASSWORD = "Sprint1!demo"

#: backend/.env — one level up from this package.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(ENV_FILE, override=False)


class MissingConfig(RuntimeError):
    """A required setting has no value. Raised when it is read, not at import."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise MissingConfig(
            f"{name} is not set. Copy backend/.env.example to backend/.env and "
            f"fill it in from your Supabase dashboard."
        )
    return value.strip()


def cors_origins() -> list[str]:
    """Origins allowed to call this API.

    Set CORS_ORIGINS to a comma-separated list to override the local default,
    e.g. CORS_ORIGINS="https://spmg3t7.example.com,http://localhost:5173"
    """
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def session_idle_minutes() -> int:
    """How long a session survives without a request before it expires (US1.1).

    Set SESSION_IDLE_MINUTES to override. A value that is not a positive whole
    number falls back to the default rather than disabling the timeout, because
    a session that never expires is the more dangerous reading of bad input.
    """
    raw = os.getenv("SESSION_IDLE_MINUTES")
    if raw is None:
        return DEFAULT_SESSION_IDLE_MINUTES
    try:
        minutes = int(raw)
    except ValueError:
        return DEFAULT_SESSION_IDLE_MINUTES
    return minutes if minutes > 0 else DEFAULT_SESSION_IDLE_MINUTES


def seed_password() -> str:
    """Shared password for the seeded development accounts.

    Set SEED_PASSWORD to override. These accounts exist so the team can sign in
    as each role while there is no way to create one; they are not a production
    credential store.
    """
    return os.getenv("SEED_PASSWORD") or DEFAULT_SEED_PASSWORD


def supabase_url() -> str:
    """Base URL of the Supabase project, e.g. https://abcdef.supabase.co"""
    return _required("SUPABASE_URL").rstrip("/")


def supabase_anon_key() -> str:
    """The anon key — the one tied to a signed-in user's own permissions.

    Safe to expose, and the key used for end-user sign-in: a client built with
    it is subject to Row Level Security, so it sees what that user may see.
    """
    return _required("SUPABASE_ANON_KEY")


def supabase_service_role_key() -> str:
    """The service role key — full admin, bypasses Row Level Security.

    Backend only. It must never be sent to the browser or put behind a VITE_
    variable; anything holding it can read and write every row in the project.
    """
    return _required("SUPABASE_SERVICE_ROLE_KEY")


def supabase_db_url() -> str | None:
    """Direct Postgres connection string, for schema introspection and migrations.

    Optional: the API itself goes through PostgREST and does not need it, so a
    missing value is None rather than an error.
    """
    raw = os.getenv("SUPABASE_DB_URL")
    return raw.strip() if raw and raw.strip() else None


def supabase_configured() -> bool:
    """Whether Supabase credentials are present, without raising if they are not.

    Lets a caller — the health check, a test — report the state of the wiring
    instead of failing on it.
    """
    return all(
        os.getenv(name) for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    )
