import os

DEFAULT_SESSION_IDLE_MINUTES = 30
DEFAULT_SEED_PASSWORD = "Sprint1!demo"


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
