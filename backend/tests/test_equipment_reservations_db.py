"""Opt-in two-connection tests against a migrated, disposable PostgreSQL database.

Set US19_DB_TEST_URL to a test database with all application migrations applied.
Creates uniquely named fixtures, commits race outcomes, and deletes fixtures.
Never point this at the shared/live database.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

URL = os.getenv("US19_DB_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires disposable US19_DB_TEST_URL")
psycopg = pytest.importorskip("psycopg")


@pytest.fixture
def world():
    tag = uuid4().hex
    users, events, requests = [], [], []
    with psycopg.connect(URL, autocommit=True) as db:

        def one(sql, params=()):
            return db.execute(sql, params).fetchone()[0]

        equipment = None
        try:
            for role in ("Technical Support", "Event Coordinator"):
                users.append(
                    one(
                        "INSERT INTO users(email,name,role) VALUES (%s,%s,%s) RETURNING id",
                        (f"{tag}-{len(users)}@example.invalid", tag, role),
                    )
                )
            equipment = one(
                "INSERT INTO equipment(name,equipment_type,description,location,"
                "total_quantity,out_of_service_quantity,out_of_service_reason) "
                "VALUES (%s,%s,'','Test',10,2,'Maintenance') RETURNING id",
                (tag, tag),
            )
            for _ in range(2):
                events.append(
                    one(
                        "INSERT INTO events(name,description,organiser_id,coordinator_id,status) "
                        "VALUES (%s,'Test',%s,%s,'Planning') RETURNING id",
                        (tag, users[1], users[1]),
                    )
                )
                requests.append(
                    one(
                        "INSERT INTO equipment_requests(event_id,equipment_type,quantity,"
                        "start_at,end_at,requested_by_id,requested_equipment_id) VALUES (%s,%s,6,"
                        "'2030-01-01 09:00','2030-01-01 17:00',%s,%s) RETURNING id",
                        (events[-1], tag, users[1], equipment),
                    )
                )
            yield db, equipment, users, events, requests
        finally:
            # Delete parents first so request FK references no longer retain stock.
            for event in events:
                db.execute("DELETE FROM events WHERE id=%s", (event,))
            if equipment:
                db.execute("DELETE FROM equipment WHERE id=%s", (equipment,))
            for user in users:
                db.execute("DELETE FROM users WHERE id=%s", (user,))


def test_competing_requests_cannot_double_promise(world):
    db, item, users, events, requests = world
    barrier = Barrier(2)

    def decide(request):
        with psycopg.connect(URL) as connection:
            connection.execute("SET LOCAL lock_timeout = '5s'")
            barrier.wait(timeout=5)
            return connection.execute(
                "SELECT decide_equipment_request(%s,1,%s,%s)", (request, users[0], item)
            ).fetchone()[0]["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, requests))
    assert sorted(results) == ["insufficient_stock", "ok"]
    assert (
        db.execute(
            "SELECT sum(quantity) FROM equipment_requests WHERE equipment_id=%s "
            "AND status='Reserved'",
            (item,),
        ).fetchone()[0]
        == 6
    )
    assert (
        db.execute(
            "SELECT count(*) FROM notifications WHERE event_id=ANY(%s) "
            "AND kind='equipment-reserved'",
            (events,),
        ).fetchone()[0]
        == 1
    )


def test_duplicate_decision_and_adjacent_window(world):
    db, item, users, events, requests = world
    result = db.execute(
        "SELECT decide_equipment_request(%s,1,%s,%s)", (requests[0], users[0], item)
    ).fetchone()[0]
    assert result["code"] == "ok"
    assert (
        db.execute(
            "SELECT decide_equipment_request(%s,1,%s,%s)", (requests[0], users[0], item)
        ).fetchone()[0]["code"]
        == "stale_request"
    )
    db.execute(
        "UPDATE equipment_requests SET start_at='2030-01-01 17:00', "
        "end_at='2030-01-01 18:00' WHERE id=%s",
        (requests[1],),
    )
    assert (
        db.execute(
            "SELECT decide_equipment_request(%s,1,%s,%s)", (requests[1], users[0], item)
        ).fetchone()[0]["code"]
        == "ok"
    )


def test_reserve_versus_unavailable_has_one_winner(world):
    db, item, users, events, requests = world
    barrier = Barrier(2)

    def decide(equipment_id):
        with psycopg.connect(URL) as connection:
            connection.execute("SET LOCAL lock_timeout = '5s'")
            barrier.wait(timeout=5)
            return connection.execute(
                "SELECT decide_equipment_request(%s,1,%s,%s,%s)",
                (requests[0], users[0], equipment_id, "No stock"),
            ).fetchone()[0]["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [item, None]))
    assert sorted(results) == ["ok", "stale_request"]
    assert (
        db.execute(
            "SELECT count(*) FROM notifications WHERE event_id=%s "
            "AND kind IN ('equipment-reserved','equipment-unavailable')",
            (events[0],),
        ).fetchone()[0]
        == 1
    )


def test_notification_failure_rolls_back_decision_and_history(world):
    db, item, users, events, requests = world
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            # Temporary failure injection, rolled back with the failed decision.
            db.execute(
                "ALTER TABLE notifications ADD CONSTRAINT us19_test_failure "
                "CHECK (kind <> 'equipment-reserved')"
            )
            db.execute("SELECT decide_equipment_request(%s,1,%s,%s)", (requests[0], users[0], item))
    assert db.execute(
        "SELECT status,version FROM equipment_requests WHERE id=%s", (requests[0],)
    ).fetchone() == ("Requested", 1)
    assert (
        db.execute(
            "SELECT count(*) FROM equipment_request_history "
            "WHERE request_id=%s AND action='Updated'",
            (requests[0],),
        ).fetchone()[0]
        == 0
    )
