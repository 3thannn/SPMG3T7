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


def test_a_new_session_resolves_to_its_user():
    store, _ = build()
    session = store.create(1)

    state, found = store.touch(session.token)

    assert state is SessionState.ACTIVE
    assert found is not None and found.user_id == 1


def test_each_session_gets_its_own_token():
    store, _ = build()
    assert store.create(1).token != store.create(1).token


def test_an_unknown_token_is_unknown_rather_than_expired():
    store, _ = build()
    assert store.touch("never-issued") == (SessionState.UNKNOWN, None)


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


def test_an_expired_session_is_reported_once_then_forgotten():
    store, clock = build()
    session = store.create(1)
    clock.advance(minutes=31)

    assert store.touch(session.token)[0] is SessionState.EXPIRED
    assert store.touch(session.token)[0] is SessionState.UNKNOWN


def test_revoking_ends_the_session_immediately():
    store, _ = build()
    session = store.create(1)

    assert store.revoke(session.token) is True
    assert store.touch(session.token)[0] is SessionState.UNKNOWN


def test_revoking_an_unknown_token_reports_that_nothing_was_removed():
    store, _ = build()
    assert store.revoke("never-issued") is False


def test_revoking_one_session_leaves_the_users_other_sessions_alone():
    store, _ = build()
    phone = store.create(1)
    laptop = store.create(1)

    store.revoke(phone.token)

    assert store.touch(laptop.token)[0] is SessionState.ACTIVE


def test_revoke_all_ends_every_session_for_one_user_only():
    store, _ = build()
    phone = store.create(1)
    laptop = store.create(1)
    other = store.create(2)

    assert store.revoke_all_for(1) == 2
    assert store.touch(phone.token)[0] is SessionState.UNKNOWN
    assert store.touch(laptop.token)[0] is SessionState.UNKNOWN
    assert store.touch(other.token)[0] is SessionState.ACTIVE


def test_active_count_ignores_sessions_that_have_timed_out():
    store, clock = build()
    store.create(1)
    clock.advance(minutes=31)
    store.create(2)

    assert store.active_count() == 1
