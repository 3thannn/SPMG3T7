"""Server-side session storage.

A session is an opaque token mapped to a user, held on the server so that
logout can end it outright (US1.2) — a self-contained token cannot be taken
back before it expires. The window is a sliding one: every authenticated
request extends it, so a session stays alive through normal use and lapses only
after a period of inactivity (US1.1).

Sessions live in memory, so restarting the API signs everyone out. That is the
same gap as the rest of the project's storage and closes with US6.3.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.security import new_token


class SessionState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass
class Session:
    token: str
    user_id: int
    created_at: datetime
    last_seen_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SessionStore:
    def __init__(
        self,
        idle_timeout: timedelta,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._idle_timeout = idle_timeout
        self._clock = clock
        self._sessions: dict[str, Session] = {}

    @property
    def idle_timeout(self) -> timedelta:
        return self._idle_timeout

    def create(self, user_id: int) -> Session:
        now = self._clock()
        session = Session(
            token=new_token(), user_id=user_id, created_at=now, last_seen_at=now
        )
        self._sessions[session.token] = session
        return session

    def touch(self, token: str) -> tuple[SessionState, Session | None]:
        """Look a session up and extend it.

        Returns EXPIRED rather than UNKNOWN for a session that timed out, so the
        caller can tell someone they were signed out for being idle instead of
        implying their credentials were wrong.
        """
        session = self._sessions.get(token)
        if session is None:
            return SessionState.UNKNOWN, None

        now = self._clock()
        if now - session.last_seen_at >= self._idle_timeout:
            del self._sessions[token]
            return SessionState.EXPIRED, None

        session.last_seen_at = now
        return SessionState.ACTIVE, session

    def revoke(self, token: str) -> bool:
        """End one session. True when a session was actually removed."""
        return self._sessions.pop(token, None) is not None

    def revoke_all_for(self, user_id: int) -> int:
        """End every session belonging to a user, e.g. after a password change."""
        doomed = [
            token for token, session in self._sessions.items() if session.user_id == user_id
        ]
        for token in doomed:
            del self._sessions[token]
        return len(doomed)

    def active_count(self) -> int:
        """Live sessions, ignoring any that have timed out but not been touched."""
        now = self._clock()
        return sum(
            1
            for session in self._sessions.values()
            if now - session.last_seen_at < self._idle_timeout
        )

    def clear(self) -> None:
        self._sessions.clear()
