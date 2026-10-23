"""The registration store itself — US20.1.

The route tests run against `InMemoryRegistrations`, which covers the rules.
This file covers the rest: that `SupabaseRegistrations` asks PostgREST and the
two database functions for the right thing, and reads every answer they give.
What the functions themselves do is test_registration_db.py (opt-in) and
TEST_US20_1_REGISTRATION.sql.
"""

from dataclasses import dataclass, field

import pytest

from app import supabase_client
from app.event_status import EventStatus
from app.registration_store import (
    EVENTS_TABLE,
    OPEN_EVENT_COLUMNS,
    SETTINGS_COLUMNS,
    TABLE,
    WITH_EVENT_COLUMNS,
    BelowRegistered,
    OpenEvent,
    RegisteredEvent,
    RegisterOutcome,
    Registration,
    RegistrationSettings,
    RegistrationStatus,
    StaleRegistrationSettings,
    SupabaseRegistrations,
    WithdrawOutcome,
    to_registration,
)

OPEN_ROW = {
    "id": 950,
    "name": "Open House",
    "proposed_date": "2099-11-02T09:00:00",
    "end_date": "2099-11-02T17:00:00",
    "registration_capacity": 30,
}


@dataclass
class FakeResponse:
    data: object


@dataclass
class FakeQuery:
    """One table's query: records each call and answers with that table's rows."""

    table: str
    rows: list[dict]
    calls: list[tuple] = field(default_factory=list)

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def eq(self, column: str, value):
        self.calls.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list):
        self.calls.append(("in", column, values))
        return self

    def order(self, column: str, desc: bool = False):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, count: int):
        self.calls.append(("limit", count))
        return self

    def execute(self):
        return FakeResponse(self.rows)


@dataclass
class FakeClient:
    """Answers each table with its own rows and each function with `rpc_answer`."""

    rows: dict[str, list[dict]] = field(default_factory=dict)
    rpc_answer: object = None
    queries: list[FakeQuery] = field(default_factory=list)
    rpcs: list[tuple[str, dict]] = field(default_factory=list)

    def table(self, name: str) -> FakeQuery:
        query = FakeQuery(name, self.rows.get(name, []))
        self.queries.append(query)
        return query

    def rpc(self, name: str, arguments: dict):
        self.rpcs.append((name, arguments))
        return self

    def execute(self):
        return FakeResponse(self.rpc_answer)

    def on(self, table: str) -> list[FakeQuery]:
        return [query for query in self.queries if query.table == table]


@pytest.fixture
def fake(monkeypatch):
    """The admin client every store call goes through, replaced by a recorder."""
    recorder = FakeClient()
    monkeypatch.setattr(supabase_client, "admin", lambda: recorder)
    return recorder


class TestReadingTheSettings:
    def test_it_reads_the_two_columns_and_counts_the_active_registrations(self, fake):
        fake.rows = {
            EVENTS_TABLE: [{"id": 950, "registration_open": True, "registration_capacity": 30}],
            TABLE: [{"id": 1}, {"id": 2}],
        }

        settings = SupabaseRegistrations().settings_for(950)

        assert settings == RegistrationSettings(
            event_id=950, is_open=True, capacity=30, registered=2
        )
        (events,) = fake.on(EVENTS_TABLE)
        assert ("select", SETTINGS_COLUMNS) in events.calls
        assert ("eq", "id", 950) in events.calls
        (registrations,) = fake.on(TABLE)
        assert ("eq", "event_id", 950) in registrations.calls
        assert ("eq", "status", "Registered") in registrations.calls

    def test_an_event_never_opened_reads_as_off_with_no_capacity(self, fake):
        fake.rows = {
            EVENTS_TABLE: [{"id": 950, "registration_open": False, "registration_capacity": None}]
        }

        settings = SupabaseRegistrations().settings_for(950)

        assert (settings.is_open, settings.capacity, settings.places_left) == (False, None, None)


class TestSavingTheSettings:
    def test_it_calls_the_function_with_every_argument(self, fake):
        fake.rpc_answer = {"outcome": "saved", "registered": 0}
        fake.rows = {
            EVENTS_TABLE: [{"id": 950, "registration_open": True, "registration_capacity": 40}]
        }

        saved = SupabaseRegistrations().set_settings(950, actor_id=2, is_open=True, capacity=40)

        assert fake.rpcs == [
            (
                "set_event_registration",
                {"p_event_id": 950, "p_actor_id": 2, "p_open": True, "p_capacity": 40},
            )
        ]
        assert (saved.is_open, saved.capacity) == (True, 40)

    def test_no_capacity_is_sent_as_null_so_the_stored_one_is_kept(self, fake):
        fake.rpc_answer = {"outcome": "saved", "registered": 0}

        SupabaseRegistrations().set_settings(950, actor_id=2, is_open=False, capacity=None)

        assert fake.rpcs[0][1]["p_capacity"] is None

    def test_below_the_places_taken_says_how_many(self, fake):
        fake.rpc_answer = {"outcome": "below-registered", "registered": 7}

        with pytest.raises(BelowRegistered) as raised:
            SupabaseRegistrations().set_settings(950, actor_id=2, is_open=True, capacity=5)

        assert raised.value.registered == 7

    @pytest.mark.parametrize(
        "answer",
        [
            {"outcome": "not-assigned"},
            {"outcome": "closed", "status": "Completed"},
            {"outcome": "invalid"},
            None,
        ],
    )
    def test_anything_but_saved_is_stale(self, fake, answer):
        fake.rpc_answer = answer

        with pytest.raises(StaleRegistrationSettings):
            SupabaseRegistrations().set_settings(950, actor_id=2, is_open=True, capacity=5)


class TestOpenEvents:
    def test_it_asks_for_confirmed_events_taking_registrations_soonest_first(self, fake):
        fake.rows = {EVENTS_TABLE: [OPEN_ROW], TABLE: [{"event_id": 950}] * 3}

        listed = SupabaseRegistrations().list_open()

        assert listed == [
            OpenEvent(
                event_id=950,
                title="Open House",
                starts_at="2099-11-02T09:00:00",
                ends_at="2099-11-02T17:00:00",
                capacity=30,
                registered=3,
            )
        ]
        (events,) = fake.on(EVENTS_TABLE)
        assert events.calls[0] == ("select", OPEN_EVENT_COLUMNS)
        assert ("eq", "status", "Confirmed") in events.calls
        assert ("eq", "registration_open", True) in events.calls
        assert [call for call in events.calls if call[0] == "order"] == [
            ("order", "proposed_date", False),
            ("order", "id", False),
        ]

    def test_places_are_counted_for_every_listed_event_in_one_query(self, fake):
        fake.rows = {
            EVENTS_TABLE: [OPEN_ROW, {**OPEN_ROW, "id": 951}],
            TABLE: [{"event_id": 950}, {"event_id": 951}, {"event_id": 951}],
        }

        listed = SupabaseRegistrations().list_open()

        assert [(item.event_id, item.registered) for item in listed] == [(950, 1), (951, 2)]
        (registrations,) = fake.on(TABLE)
        assert ("in", "event_id", [950, 951]) in registrations.calls
        assert ("eq", "status", "Registered") in registrations.calls

    def test_nothing_open_asks_nothing_more(self, fake):
        assert SupabaseRegistrations().list_open() == []
        assert fake.on(TABLE) == []

    def test_one_open_event_is_the_same_query_for_one_id(self, fake):
        fake.rows = {EVENTS_TABLE: [OPEN_ROW]}

        found = SupabaseRegistrations().get_open(950)

        assert found is not None and found.places_left == 30
        (events,) = fake.on(EVENTS_TABLE)
        assert ("eq", "id", 950) in events.calls
        assert ("eq", "status", "Confirmed") in events.calls

    def test_an_event_not_open_is_none(self, fake):
        assert SupabaseRegistrations().get_open(950) is None

    def test_an_attendees_own_registrations(self, fake):
        fake.rows = {TABLE: [{"event_id": 950}, {"event_id": 951}]}

        mine = SupabaseRegistrations().registered_event_ids(20)

        assert mine == frozenset({950, 951})
        (registrations,) = fake.on(TABLE)
        assert ("eq", "attendee_id", 20) in registrations.calls
        assert ("eq", "status", "Registered") in registrations.calls


class TestRegistering:
    def test_it_calls_the_function_and_reads_the_registration_back(self, fake):
        fake.rpc_answer = {
            "outcome": "registered",
            "id": 5,
            "createdAt": "2026-10-23T06:00:00",
            "becameFull": True,
        }

        result = SupabaseRegistrations().register(
            950, attendee_id=20, name="Casey Tan", email="casey@example.com"
        )

        assert fake.rpcs == [
            (
                "register_for_event",
                {
                    "p_event_id": 950,
                    "p_attendee_id": 20,
                    "p_name": "Casey Tan",
                    "p_email": "casey@example.com",
                },
            )
        ]
        assert result.outcome is RegisterOutcome.REGISTERED
        assert result.became_full is True
        assert result.registration == Registration(
            id=5,
            event_id=950,
            attendee_id=20,
            name="Casey Tan",
            email="casey@example.com",
            status=RegistrationStatus.REGISTERED,
            created_at="2026-10-23T06:00:00",
        )

    @pytest.mark.parametrize(
        ("answer", "outcome"),
        [
            ("already-registered", RegisterOutcome.ALREADY_REGISTERED),
            ("full", RegisterOutcome.FULL),
            ("closed", RegisterOutcome.CLOSED),
        ],
    )
    def test_each_refusal_is_an_outcome_not_an_error(self, fake, answer, outcome):
        fake.rpc_answer = {"outcome": answer}

        result = SupabaseRegistrations().register(
            950, attendee_id=20, name="Casey", email="casey@example.com"
        )

        assert (result.outcome, result.registration, result.became_full) == (
            outcome,
            None,
            False,
        )

    @pytest.mark.parametrize("answer", [{"outcome": "invalid"}, {"outcome": "not-attendee"}, None])
    def test_an_answer_the_route_should_have_prevented_is_a_bug(self, fake, answer):
        fake.rpc_answer = answer

        with pytest.raises(RuntimeError):
            SupabaseRegistrations().register(
                950, attendee_id=20, name="Casey", email="casey@example.com"
            )


REGISTRATION_ROW = {
    "id": 5,
    "event_id": 950,
    "attendee_id": 20,
    "name": "Casey Tan",
    "email": "casey@example.com",
    "status": "Withdrawn",
    "created_at": "2026-10-23T06:00:00",
    "withdrawn_at": "2026-10-24T01:30:00",
    "events": {
        "name": "Open House",
        "proposed_date": "2099-11-02T09:00:00",
        "end_date": "2099-11-02T17:00:00",
        "status": "Confirmed",
    },
}


class TestAnAttendeesRegistrations:
    """US20.2: their own list, with each event's current details embedded."""

    def test_it_reads_their_rows_newest_first_with_the_event(self, fake):
        fake.rows = {TABLE: [REGISTRATION_ROW]}

        listed = SupabaseRegistrations().list_for_attendee(20)

        assert listed == [
            Registration(
                id=5,
                event_id=950,
                attendee_id=20,
                name="Casey Tan",
                email="casey@example.com",
                status=RegistrationStatus.WITHDRAWN,
                created_at="2026-10-23T06:00:00",
                withdrawn_at="2026-10-24T01:30:00",
                event=RegisteredEvent(
                    title="Open House",
                    starts_at="2099-11-02T09:00:00",
                    ends_at="2099-11-02T17:00:00",
                    status=EventStatus.CONFIRMED,
                ),
            )
        ]
        (query,) = fake.on(TABLE)
        assert query.calls[0] == ("select", WITH_EVENT_COLUMNS)
        assert ("eq", "attendee_id", 20) in query.calls
        assert ("order", "id", True) in query.calls

    def test_the_embedded_event_is_read_whether_object_or_list(self):
        as_list = to_registration({**REGISTRATION_ROW, "events": [REGISTRATION_ROW["events"]]})
        missing = to_registration({**REGISTRATION_ROW, "events": None, "withdrawn_at": None})

        assert as_list.event is not None and as_list.event.title == "Open House"
        assert (missing.event, missing.withdrawn_at) == (None, "")

    def test_one_registration_by_id(self, fake):
        fake.rows = {TABLE: [REGISTRATION_ROW]}

        found = SupabaseRegistrations().get_registration(5)

        assert found is not None and found.id == 5
        (query,) = fake.on(TABLE)
        assert ("eq", "id", 5) in query.calls

    def test_no_such_registration_is_none(self, fake):
        assert SupabaseRegistrations().get_registration(5) is None


class TestWithdrawing:
    def test_it_calls_the_function_and_reads_the_registration_back(self, fake):
        fake.rpc_answer = {"outcome": "withdrawn", "withdrawnAt": "2026-10-24T01:30:00"}
        fake.rows = {TABLE: [REGISTRATION_ROW]}

        result = SupabaseRegistrations().withdraw(5, attendee_id=20)

        assert fake.rpcs == [
            ("withdraw_registration", {"p_registration_id": 5, "p_attendee_id": 20})
        ]
        assert result.outcome is WithdrawOutcome.WITHDRAWN
        assert result.registration is not None
        assert result.registration.status is RegistrationStatus.WITHDRAWN

    @pytest.mark.parametrize(
        ("answer", "outcome"),
        [
            ("not-found", WithdrawOutcome.NOT_FOUND),
            ("already-withdrawn", WithdrawOutcome.ALREADY_WITHDRAWN),
            ("closed", WithdrawOutcome.CLOSED),
            ("started", WithdrawOutcome.STARTED),
        ],
    )
    def test_each_refusal_is_an_outcome_not_an_error(self, fake, answer, outcome):
        fake.rpc_answer = {"outcome": answer}

        result = SupabaseRegistrations().withdraw(5, attendee_id=20)

        assert (result.outcome, result.registration) == (outcome, None)

    @pytest.mark.parametrize("answer", [{"outcome": "nonsense"}, None])
    def test_an_answer_it_does_not_know_is_a_bug(self, fake, answer):
        fake.rpc_answer = answer

        with pytest.raises(RuntimeError):
            SupabaseRegistrations().withdraw(5, attendee_id=20)
