"""US19.3: stock arithmetic, decisions, permissions, persistence and boundaries."""

from dataclasses import replace

import pytest

from app.event_status import EventStatus
from tests import test_equipment as fixtures
from tests.test_equipment import ITEM, LINE

actors = fixtures.actors
item = fixtures.item
planning_event = fixtures.planning_event
approved_event = fixtures.approved_event


@pytest.fixture
def line(client, actors, item, planning_event):
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 201
    return response.json()


def reserve(client, actors, line, item, **changes):
    return client.post(
        f"/equipment-requests/{line['id']}/reserve",
        json={"version": line["version"], "equipmentId": int(item["id"]), **changes},
        headers=actors["tech"],
    )


def test_reserve_persists_and_notifies_once(client, actors, line, item, planning_event):
    response = reserve(client, actors, line, item)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Reserved"
    assert response.json()["equipmentId"] == item["id"]
    assert response.json()["eventId"] == planning_event
    assert response.json()["version"] == 2
    assert reserve(client, actors, line, item).status_code == 409
    notices = client.get("/notifications", headers=actors["coord"]).json()
    assert len([n for n in notices if n["kind"] == "equipment-reserved"]) == 1
    assert (
        client.get(f"/events/{planning_event}/equipment-requests", headers=actors["coord"]).json()[
            0
        ]["status"]
        == "Reserved"
    )


@pytest.mark.parametrize("quantity,expected,shortfall", [(2, 200, 0), (3, 409, 1)])
def test_ten_minus_two_minus_six(
    client, actors, line, item, equipment_repository, quantity, expected, shortfall
):
    repo = equipment_repository
    repo.save_item(replace(repo.items[0], total_quantity=10, out_of_service_quantity=2))
    current = repo.get_request(int(line["id"]))
    repo.requests = [
        replace(current, quantity=quantity),
        replace(current, id=999, status="Reserved", quantity=6, equipment_id=int(item["id"])),
    ]
    stock = client.get(
        f"/equipment-requests/{line['id']}/availability", headers=actors["tech"]
    ).json()[0]
    assert stock["availableQuantity"] == 2
    assert stock["shortfall"] == shortfall
    response = reserve(client, actors, line, item)
    assert response.status_code == expected
    if shortfall:
        assert response.json()["detail"]["shortfall"] == 1
        assert repo.get_request(current.id).status == "Requested"
        assert not any(
            n["kind"] == "equipment-reserved"
            for n in client.get("/notifications", headers=actors["coord"]).json()
        )


@pytest.mark.parametrize(
    "start,end,used",
    [
        ("08:00", "09:00", 0),
        ("17:00", "18:00", 0),
        ("08:00", "09:01", 1),
        ("16:59", "18:00", 1),
        ("09:00", "17:00", 1),
        ("10:00", "12:00", 1),
    ],
)
def test_overlap_boundaries(client, actors, line, item, equipment_repository, start, end, used):
    current = equipment_repository.get_request(int(line["id"]))
    equipment_repository.requests.append(
        replace(
            current,
            id=999,
            status="Reserved",
            equipment_id=int(item["id"]),
            starts_at=f"2027-11-02T{start}",
            ends_at=f"2027-11-02T{end}",
        )
    )
    stock = client.get(
        f"/equipment-requests/{line['id']}/availability", headers=actors["tech"]
    ).json()[0]
    assert stock["reservedQuantity"] == used


def test_request_window_not_event_and_overnight(client, actors, line, item, equipment_repository):
    current = equipment_repository.get_request(int(line["id"]))
    equipment_repository.requests = [
        replace(current, starts_at="2027-11-03T23:00", ends_at="2027-11-04T02:00"),
        replace(
            current,
            id=999,
            status="Reserved",
            equipment_id=int(item["id"]),
            starts_at="2027-11-04T01:00",
            ends_at="2027-11-04T03:00",
        ),
    ]
    stock = client.get(
        f"/equipment-requests/{line['id']}/availability", headers=actors["tech"]
    ).json()[0]
    assert stock["reservedQuantity"] == 1


def test_unavailable_reason_and_notification(client, actors, line):
    path = f"/equipment-requests/{line['id']}/unavailable"
    assert (
        client.post(path, json={"version": 1, "reason": "  "}, headers=actors["tech"]).status_code
        == 400
    )
    response = client.post(
        path, json={"version": 1, "reason": "  Broken  "}, headers=actors["tech"]
    )
    assert response.status_code == 200
    assert response.json()["unavailableReason"] == "Broken"
    notices = client.get("/notifications", headers=actors["coord"]).json()
    notice = next(n for n in notices if n["kind"] == "equipment-unavailable")
    assert "Broken" in notice["message"]
    assert not notice["read"]


def test_negative_decisions(client, actors, line, item, event_repository, equipment_repository):
    path = f"/equipment-requests/{line['id']}"
    payload = {"version": 1, "equipmentId": int(item["id"])}
    for role in ("coord", "organiser", "lead"):
        assert client.post(path + "/reserve", json=payload, headers=actors[role]).status_code == 403
        assert client.get(path + "/availability", headers=actors[role]).status_code == 403
    assert reserve(client, actors, line, item, version=9).status_code == 409
    assert reserve(client, actors, line, item, equipmentId=999).status_code == 400
    assert reserve(client, actors, line, item, equipmentId=True).status_code == 422
    assert (
        client.post(
            "/equipment-requests/999/reserve", json=payload, headers=actors["tech"]
        ).status_code
        == 404
    )
    event = event_repository.get_event(int(line["eventId"]))
    event_repository._replace(replace(event, status=EventStatus.CONFIRMED))
    assert reserve(client, actors, line, item).status_code == 409


def test_catalogue_guard_and_release(client, actors, line, item, equipment_repository):
    assert reserve(client, actors, line, item).status_code == 200
    path = f"/equipment/{item['id']}"
    assert (
        client.put(
            path, json={**ITEM, "outOfServiceQuantity": 5}, headers=actors["tech"]
        ).status_code
        == 409
    )
    assert client.delete(path, headers=actors["tech"]).status_code == 409
    equipment_repository.release_for_event(int(line["eventId"]), actor_id=1)
    assert equipment_repository.availability(int(line["id"]))[0]["reservedQuantity"] == 0
    assert client.delete(path, headers=actors["tech"]).status_code == 409


def test_zero_stock_wrong_type_and_ignored_statuses(
    client, actors, line, item, equipment_repository
):
    repo = equipment_repository
    current = repo.get_request(int(line["id"]))
    for number, state in enumerate(("Requested", "Unavailable", "Removed"), start=20):
        repo.requests.append(
            replace(current, id=number, status=state, quantity=100, equipment_id=int(item["id"]))
        )
    assert repo.availability(current.id)[0]["reservedQuantity"] == 0
    wrong = repo.save_item(replace(repo.items[0], id=0, equipment_type="Other"))
    assert reserve(client, actors, line, item, equipmentId=wrong.id).status_code == 400
    repo.save_item(replace(repo.items[0], out_of_service_quantity=5))
    assert repo.availability(current.id)[0]["shortfall"] == 1
    assert reserve(client, actors, line, item).status_code == 409


def test_multiple_overlaps_and_independent_items(client, actors, line, item, equipment_repository):
    repo = equipment_repository
    current = repo.get_request(int(line["id"]))
    other = repo.save_item(replace(repo.items[0], id=0, name="Other microphone"))
    repo.requests.extend(
        [
            replace(current, id=20, status="Reserved", equipment_id=int(item["id"])),
            replace(current, id=21, status="Reserved", equipment_id=int(item["id"])),
            replace(current, id=22, status="Reserved", equipment_id=other.id, quantity=3),
        ]
    )
    stock = {row["equipmentId"]: row for row in repo.availability(current.id)}
    assert stock[item["id"]]["availableQuantity"] == 1
    assert stock[str(other.id)]["availableQuantity"] == 0


@pytest.mark.parametrize("recovery", ["resubmit", "remove"])
def test_unavailable_recovery_allows_safety_review(
    client, actors, line, item, equipment_repository, booking_repository, recovery
):
    from tests.test_safety_check_us4_4 import booking

    booking_repository.bookings.append(booking(event_id=int(line["eventId"])))
    path = f"/equipment-requests/{line['id']}"
    assert (
        client.post(
            path + "/unavailable",
            json={"version": 1, "reason": "4 requested, 3 available"},
            headers=actors["tech"],
        ).status_code
        == 200
    )
    safety = f"/events/{line['eventId']}/safety-check"
    assert client.get(safety, headers=actors["coord"]).json()["reason"] == "equipment-not-reserved"
    if recovery == "resubmit":
        # Resubmitting with unchanged fields must also notify Technical Support.
        response = client.patch(path, json={"version": 2}, headers=actors["coord"])
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["status"] == "Requested"
        assert updated["unavailableReason"] == ""
        assert updated["equipmentId"] is None
        assert updated["version"] == 3
        queue = client.get("/equipment-requests", headers=actors["tech"]).json()
        assert any(r["id"] == line["id"] for r in queue)
        notices = client.get("/notifications", headers=actors["tech"]).json()
        assert any("resubmitted" in n["message"] for n in notices)
        assert reserve(client, actors, updated, item).status_code == 200
    else:
        assert client.delete(path + "?version=2", headers=actors["coord"]).status_code == 204
    history = equipment_repository.list_history(int(line["eventId"]))
    assert any(
        h.before and h.before["unavailable_reason"] == "4 requested, 3 available" for h in history
    )
    assert client.get(safety, headers=actors["coord"]).json()["ready"] is True
    response = client.post(safety, headers=actors["coord"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Pending Safety Check"


def test_unavailable_recovery_permissions_versions_and_rechecks(
    client, actors, line, item, event_repository
):
    path = f"/equipment-requests/{line['id']}"
    assert (
        client.post(
            path + "/unavailable", json={"version": 1, "reason": "Shortage"}, headers=actors["tech"]
        ).status_code
        == 200
    )
    assert client.patch(path, json={"version": 2}, headers=actors["tech"]).status_code == 409
    for role in ("organiser", "lead"):
        assert client.patch(path, json={"version": 2}, headers=actors[role]).status_code == 403
    assert client.patch(path, json={"version": 1}, headers=actors["coord"]).status_code == 409
    assert client.delete(path + "?version=1", headers=actors["coord"]).status_code == 409
    response = client.patch(path, json={"version": 2, "quantity": 4}, headers=actors["coord"])
    assert response.status_code == 200
    assert reserve(client, actors, response.json(), item).status_code == 409  # Only 3 usable.
    event = event_repository.get_event(int(line["eventId"]))
    event_repository._replace(replace(event, status=EventStatus.CONFIRMED))
    assert client.patch(path, json={"version": 3}, headers=actors["coord"]).status_code == 409
