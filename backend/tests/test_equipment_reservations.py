"""US19.3: stock arithmetic, decisions, permissions, persistence and boundaries."""

from dataclasses import replace

import pytest

from app.event_status import EventStatus
from tests import test_equipment as fixtures
from tests.test_equipment import LINE

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
    assert str(other.id) not in stock  # Only the requested item is offered.




