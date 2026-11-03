from datetime import UTC, datetime, timedelta

from app.sessions import SessionState, SessionStore

IDLE = timedelta(minutes=30)


class FakeClock:
    """A clock the test moves by hand, so idle timeouts need no real waiting."""

    def __init__(self) -> None:
        self.now = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def build() -> tuple[SessionStore, FakeClock]:
    clock = FakeClock()
    return SessionStore(idle_timeout=IDLE, clock=clock), clock








def test_a_session_survives_inactivity_shorter_than_the_timeout():
    store, clock = build()
    session = store.create(1)

    clock.advance(minutes=29)

    assert store.touch(session.token)[0] is SessionState.ACTIVE


def test_a_session_expires_once_the_idle_window_passes():
    store, clock = build()
    session = store.create(1)

    clock.advance(minutes=30)

    assert store.touch(session.token)[0] is SessionState.EXPIRED


def test_use_slides_the_window_so_an_active_session_stays_alive():
    """US1.1: a session stays active during normal use, however long that runs."""
    store, clock = build()
    session = store.create(1)

    for _ in range(10):
        clock.advance(minutes=25)
        assert store.touch(session.token)[0] is SessionState.ACTIVE

    clock.advance(minutes=31)
    assert store.touch(session.token)[0] is SessionState.EXPIRED












