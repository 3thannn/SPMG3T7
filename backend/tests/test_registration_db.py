"""US20.1, US20.2 and US4.6 against the real database: the functions, the trigger, two at once.

CI has no database, so this file is opt-in. Apply
SUPABASE_US20_1_REGISTRATION.sql, SUPABASE_US20_2_WITHDRAW.sql and
SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql first, then run it from backend/:

    SPMG3T7_DB_TESTS=1 python -m pytest tests/test_registration_db.py          # bash
    $env:SPMG3T7_DB_TESTS=1; python -m pytest tests/test_registration_db.py    # PowerShell

It needs `SUPABASE_DB_URL` in backend/.env and psycopg (requirements-dev.txt).

Two kinds of test, because two connections cannot share a transaction:

* `TestTheFunctions` works in one transaction that is rolled back at the end,
  as test_hold_expiry_db.py does, so it leaves nothing behind.
* `TestTwoAtOnce` cannot: a second connection only sees what the first has
  committed. It commits its own tagged users and event, and deletes them in a
  `finally` whatever happens. Deleting the event deletes its registrations.
"""

import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv

if not os.getenv("SPMG3T7_DB_TESTS"):
    pytest.skip(
        "opt-in: set SPMG3T7_DB_TESTS=1 to run against SUPABASE_DB_URL",
        allow_module_level=True,
    )

psycopg = pytest.importorskip("psycopg")


def _url() -> str:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        pytest.skip("SUPABASE_DB_URL is not set in backend/.env")
    return url


def connect():
    return psycopg.connect(_url(), connect_timeout=15)


@pytest.fixture
def db():
    """A cursor in a transaction that is always rolled back."""
    connection = connect()
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.rollback()
        connection.close()


def one(cursor, sql, *params):
    cursor.execute(sql, params)
    return cursor.fetchone()[0]


class World:
    """An Organiser, a Coordinator, two Attendees and a Confirmed event."""

    def __init__(self, cursor, *, capacity=2):
        self.cursor = cursor
        self.tag = uuid.uuid4().hex[:8]
        self.organiser = self.user("Event Organiser")
        self.coordinator = self.user("Event Coordinator")
        self.attendee = self.user("Attendee", "a")
        self.second = self.user("Attendee", "b")
        self.event = self.add_event("Confirmed", capacity=capacity)

    def user(self, role, suffix=""):
        return one(
            self.cursor,
            "INSERT INTO public.users (email, name, role) "
            "VALUES (%s, %s, %s::public.user_role) RETURNING id",
            f"us20-1-{role.split()[-1].lower()}{suffix}-{self.tag}@example.invalid",
            f"US20.1 {role}",
            role,
        )

    def add_event(self, status, *, capacity=2, is_open=True, starts="2099-11-02 09:00"):
        return one(
            self.cursor,
            "INSERT INTO public.events (name, description, organiser_id, coordinator_id, "
            "status, expected_attendance, registration_open, registration_capacity, "
            "proposed_date) "
            "VALUES (%s, 'Test', %s, %s, %s::public.event_status, 30, %s, %s, %s) RETURNING id",
            f"US20.1 event {self.tag}",
            self.organiser,
            self.coordinator,
            status,
            is_open,
            capacity,
            starts,
        )

    def withdraw(self, registration, attendee=None):
        return one(
            self.cursor,
            "SELECT public.withdraw_registration(%s, %s)",
            registration,
            attendee or self.attendee,
        )

    def register(self, attendee=None, *, event=None, name="Casey", email="casey@example.com"):
        return one(
            self.cursor,
            "SELECT public.register_for_event(%s, %s, %s, %s)",
            event or self.event,
            attendee or self.attendee,
            name,
            email,
        )

    def settings(self, *, is_open, capacity, actor=None, event=None):
        return one(
            self.cursor,
            "SELECT public.set_event_registration(%s, %s, %s, %s)",
            event or self.event,
            actor or self.coordinator,
            is_open,
            capacity,
        )

    def taken(self, event=None):
        return one(
            self.cursor,
            "SELECT count(*) FROM public.registrations "
            "WHERE event_id = %s AND status = 'Registered'",
            event or self.event,
        )


class TestTheFunctions:
    def test_registering_takes_a_place_and_says_when_it_was_the_last(self, db):
        world = World(db, capacity=2)

        first = world.register()
        last = world.register(world.second)

        assert first["outcome"] == "registered" and first["becameFull"] is False
        assert last["outcome"] == "registered" and last["becameFull"] is True
        assert world.taken() == 2

    def test_a_full_event_refuses_and_writes_nothing(self, db):
        world = World(db, capacity=1)
        world.register()

        assert world.register(world.second) == {"outcome": "full"}
        assert world.taken() == 1

    def test_one_active_registration_per_attendee(self, db):
        world = World(db, capacity=5)
        world.register()

        assert world.register() == {"outcome": "already-registered"}
        assert world.taken() == 1

    def test_already_registered_is_answered_before_full(self, db):
        world = World(db, capacity=1)
        world.register()

        assert world.register() == {"outcome": "already-registered"}

    @pytest.mark.parametrize(
        ("status", "is_open"),
        [("Planning", True), ("Completed", True), ("Cancelled", True), ("Confirmed", False)],
    )
    def test_only_a_confirmed_event_taking_registrations_is_open(self, db, status, is_open):
        world = World(db)
        closed = world.add_event(status, is_open=is_open)

        assert world.register(event=closed) == {"outcome": "closed"}

    def test_a_missing_event_is_closed(self, db):
        world = World(db)
        assert world.register(event=-1) == {"outcome": "closed"}

    def test_only_an_attendee_registers(self, db):
        world = World(db)
        assert world.register(world.organiser) == {"outcome": "not-attendee"}

    @pytest.mark.parametrize(("name", "email"), [("", "a@example.com"), ("Casey", "  ")])
    def test_a_blank_name_or_email_is_invalid(self, db, name, email):
        world = World(db)
        assert world.register(name=name, email=email) == {"outcome": "invalid"}

    def test_the_trigger_refuses_a_direct_insert_beyond_capacity(self, db):
        world = World(db, capacity=1)
        world.register()

        with pytest.raises(psycopg.errors.CheckViolation, match="Event is full"):
            db.execute(
                "INSERT INTO public.registrations (event_id, attendee_id, name, email) "
                "VALUES (%s, %s, 'Morgan', 'm@example.com')",
                (world.event, world.second),
            )

    def test_the_trigger_refuses_a_direct_insert_when_registration_is_off(self, db):
        world = World(db)
        closed = world.add_event("Confirmed", is_open=False)

        with pytest.raises(psycopg.errors.CheckViolation, match="not open"):
            db.execute(
                "INSERT INTO public.registrations (event_id, attendee_id, name, email) "
                "VALUES (%s, %s, 'Casey', 'c@example.com')",
                (closed, world.attendee),
            )

    def test_the_index_refuses_a_second_active_row_for_one_attendee(self, db):
        world = World(db, capacity=5)
        world.register()

        with pytest.raises(psycopg.errors.UniqueViolation):
            db.execute(
                "INSERT INTO public.registrations (event_id, attendee_id, name, email) "
                "VALUES (%s, %s, 'Casey', 'c@example.com')",
                (world.event, world.attendee),
            )

    def test_the_coordinator_saves_and_a_null_capacity_keeps_the_stored_one(self, db):
        world = World(db, capacity=2)

        assert world.settings(is_open=False, capacity=None)["outcome"] == "saved"
        row = one(
            db,
            "SELECT row(registration_open, registration_capacity)::text "
            "FROM public.events WHERE id = %s",
            world.event,
        )
        assert row == "(f,2)"

    def test_the_capacity_cannot_go_below_the_places_taken(self, db):
        world = World(db, capacity=5)
        world.register()
        world.register(world.second)

        assert world.settings(is_open=True, capacity=1) == {
            "outcome": "below-registered",
            "registered": 2,
        }
        assert world.settings(is_open=True, capacity=2)["outcome"] == "saved"

    @pytest.mark.parametrize("capacity", [0, None])
    def test_opening_without_a_usable_capacity_is_invalid(self, db, capacity):
        world = World(db)
        fresh = world.add_event("Planning", capacity=None, is_open=False)

        assert world.settings(is_open=True, capacity=capacity, event=fresh) == {
            "outcome": "invalid"
        }

    def test_only_the_assigned_coordinator_saves(self, db):
        world = World(db)
        other = world.user("Event Coordinator", "x")

        assert world.settings(is_open=True, capacity=5, actor=other) == {"outcome": "not-assigned"}
        assert world.settings(is_open=True, capacity=5, actor=world.organiser) == {
            "outcome": "not-assigned"
        }

    @pytest.mark.parametrize("status", ["Submitted", "Completed", "Cancelled"])
    def test_a_status_that_takes_no_settings_is_closed(self, db, status):
        world = World(db)
        event = world.add_event(status, capacity=None, is_open=False)

        answer = world.settings(is_open=True, capacity=5, event=event)

        assert answer == {"outcome": "closed", "status": status}

    def test_the_event_full_notice_kind_is_allowed(self, db):
        world = World(db)
        db.execute(
            "INSERT INTO public.notifications (user_id, event_id, kind, status, message) "
            "VALUES (%s, %s, 'event-full', NULL, 'x is full')",
            (world.organiser, world.event),
        )


class TestWithdrawingInTheDatabase:
    """US20.2: `withdraw_registration`, and registering again afterwards."""

    def test_withdrawing_gives_the_place_back_and_keeps_the_row(self, db):
        world = World(db, capacity=1)
        taken = world.register()

        answer = world.withdraw(taken["id"])

        assert answer["outcome"] == "withdrawn" and answer["withdrawnAt"]
        assert world.taken() == 0
        row = one(
            db,
            "SELECT row(status::text, withdrawn_at IS NOT NULL)::text "
            "FROM public.registrations WHERE id = %s",
            taken["id"],
        )
        assert row == "(Withdrawn,t)"

    def test_the_freed_place_goes_to_someone_else(self, db):
        world = World(db, capacity=1)
        taken = world.register()
        assert world.register(world.second) == {"outcome": "full"}

        world.withdraw(taken["id"])

        assert world.register(world.second)["outcome"] == "registered"

    def test_a_withdrawn_attendee_registers_again_as_a_new_row(self, db):
        world = World(db, capacity=5)
        taken = world.register()
        world.withdraw(taken["id"])

        again = world.register()

        assert again["outcome"] == "registered" and again["id"] != taken["id"]
        assert world.taken() == 1

    def test_withdrawing_twice_is_answered(self, db):
        world = World(db)
        taken = world.register()
        world.withdraw(taken["id"])

        assert world.withdraw(taken["id"]) == {"outcome": "already-withdrawn"}

    def test_someone_elses_or_a_missing_registration_is_not_found(self, db):
        world = World(db)
        taken = world.register()

        assert world.withdraw(taken["id"], world.second) == {"outcome": "not-found"}
        assert world.withdraw(-1) == {"outcome": "not-found"}

    def test_once_the_event_has_started_it_is_too_late(self, db):
        world = World(db)
        started = world.add_event("Confirmed", starts="2000-01-01 09:00")
        taken = world.register(event=started)

        assert world.withdraw(taken["id"]) == {"outcome": "started"}
        assert world.taken(started) == 1

    def test_an_event_no_longer_confirmed_is_closed(self, db):
        world = World(db)
        taken = world.register()
        db.execute(
            "UPDATE public.events SET status = 'Completed' WHERE id = %s", (world.event,)
        )

        assert world.withdraw(taken["id"]) == {"outcome": "closed"}

    def test_a_withdrawn_row_must_say_when(self, db):
        world = World(db)
        taken = world.register()

        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                "UPDATE public.registrations SET status = 'Withdrawn' WHERE id = %s",
                (taken["id"],),
            )

    def test_bringing_a_withdrawn_row_back_still_counts_the_places(self, db):
        """The capacity trigger also guards an UPDATE back to Registered."""
        world = World(db, capacity=1)
        taken = world.register()
        world.withdraw(taken["id"])
        world.register(world.second)

        with pytest.raises(psycopg.errors.CheckViolation, match="Event is full"):
            db.execute(
                "UPDATE public.registrations SET status = 'Registered', withdrawn_at = NULL "
                "WHERE id = %s",
                (taken["id"],),
            )


class TestCancellingTheEvent:
    """US4.6: `cancel_event` ends the event's registrations.

    SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql.
    """

    def cancel(self, world, *, expected="Confirmed", actor=None):
        return one(
            world.cursor,
            "SELECT public.cancel_event(%s, %s, %s, 'Funding was withdrawn.')",
            world.event,
            expected,
            actor or world.coordinator,
        )

    def status_of(self, db, registration_id):
        return one(
            db, "SELECT status::text FROM public.registrations WHERE id = %s", registration_id
        )

    def test_registered_ones_become_event_cancelled_and_withdrawn_ones_stay(self, db):
        world = World(db, capacity=5)
        casey = world.register()
        morgan = world.register(world.second, name="Morgan", email="morgan@example.com")
        world.withdraw(morgan["id"], world.second)

        released = self.cancel(world)

        assert released["registrations"] == [casey["id"]]
        assert self.status_of(db, casey["id"]) == "Event Cancelled"
        assert self.status_of(db, morgan["id"]) == "Withdrawn"
        assert world.taken() == 0

    def test_registration_closes_and_keeps_its_capacity(self, db):
        world = World(db, capacity=5)
        self.cancel(world)

        row = one(
            db,
            "SELECT row(registration_open, registration_capacity)::text "
            "FROM public.events WHERE id = %s",
            world.event,
        )
        assert row == "(f,5)"

    def test_an_event_nobody_registered_for_releases_none(self, db):
        world = World(db)
        assert self.cancel(world, actor=world.organiser)["registrations"] == []

    def test_a_refused_cancellation_ends_nothing(self, db):
        world = World(db)
        taken = world.register()

        assert self.cancel(world, expected="Planning") is None
        assert self.status_of(db, taken["id"]) == "Registered"

    def test_a_cancelled_registration_answers_closed_not_withdrawn(self, db):
        world = World(db)
        taken = world.register()
        self.cancel(world)

        assert world.withdraw(taken["id"]) == {"outcome": "closed"}

    def test_nobody_registers_afterwards(self, db):
        world = World(db)
        self.cancel(world)

        assert world.register(world.second) == {"outcome": "closed"}


class TestTwoAtOnce:
    """AC4: two Attendees after the last place; the database lets one through."""

    @pytest.fixture
    def committed(self):
        """A committed world with one place, removed afterwards whatever happens."""
        setup = connect()
        setup.autocommit = True
        with setup.cursor() as cursor:
            world = World(cursor, capacity=1)
        try:
            yield world
        finally:
            with setup.cursor() as cursor:
                cursor.execute("DELETE FROM public.events WHERE id = %s", (world.event,))
                cursor.execute(
                    "DELETE FROM public.users WHERE id = ANY(%s)",
                    ([world.organiser, world.coordinator, world.attendee, world.second],),
                )
            setup.close()

    @staticmethod
    def attempt(event, attendee):
        connection = connect()
        try:
            with connection.cursor() as cursor:
                answer = one(
                    cursor,
                    "SELECT public.register_for_event(%s, %s, 'Someone', 's@example.com')",
                    event,
                    attendee,
                )
            connection.commit()
            return answer["outcome"]
        finally:
            connection.close()

    def test_the_second_waits_for_the_first_then_finds_the_event_full(self, committed):
        first = connect()
        outcome: list[str] = []
        try:
            with first.cursor() as cursor:
                taken = one(
                    cursor,
                    "SELECT public.register_for_event(%s, %s, 'First', 'f@example.com')",
                    committed.event,
                    committed.attendee,
                )
            assert taken["outcome"] == "registered"

            # The first holds the event's lock and has not committed.
            second = threading.Thread(
                target=lambda: outcome.append(self.attempt(committed.event, committed.second))
            )
            second.start()
            time.sleep(1.0)
            assert second.is_alive(), "the second registration should be waiting on the lock"

            first.commit()
            second.join(timeout=15)
            assert outcome == ["full"]
        finally:
            first.close()

    def test_at_the_same_moment_exactly_one_gets_the_place(self, committed):
        start = threading.Barrier(2)
        outcomes: list[str] = []

        def run(attendee):
            start.wait()
            outcomes.append(self.attempt(committed.event, attendee))

        threads = [
            threading.Thread(target=run, args=(person,))
            for person in (committed.attendee, committed.second)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(outcomes) == ["full", "registered"]
