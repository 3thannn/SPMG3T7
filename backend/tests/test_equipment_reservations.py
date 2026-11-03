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




def test_exact_item_selection_and_no_substitution(client, actors, line, item, equipment_repository):
    repo = equipment_repository
    other = repo.save_item(replace(repo.items[0], id=0, name="Lapel microphone"))
    assert line["requestedEquipmentId"] == item["id"]
    assert line["equipmentName"] == item["name"]
    assert reserve(client, actors, line, item, equipmentId=other.id).status_code == 400
    assert (
        client.patch(
            f"/equipment-requests/{line['id']}",
            json={"version": 1, "equipmentId": other.id},
            headers=actors["tech"],
        ).status_code
        == 403
    )
    response = client.patch(
        f"/equipment-requests/{line['id']}",
        json={"version": 1, "equipmentId": other.id},
        headers=actors["coord"],
    )
    assert response.status_code == 200
    assert response.json()["requestedEquipmentId"] == str(other.id)
    assert response.json()["equipmentName"] == "Lapel microphone"
    assert reserve(client, actors, response.json(), item).status_code == 400
    assert reserve(client, actors, response.json(), item, equipmentId=other.id).status_code == 200


def test_legacy_request_requires_coordinator_selection(
    client, actors, line, item, equipment_repository
):
    repo = equipment_repository
    repo.requests = [replace(repo.requests[0], requested_equipment_id=None, equipment_name="")]
    path = f"/equipment-requests/{line['id']}"
    assert client.get(path, headers=actors["tech"]).status_code == 200
    assert repo.availability(int(line["id"])) == []
    assert reserve(client, actors, line, item).status_code == 400
    assert client.patch(path, json={"version": 1}, headers=actors["coord"]).status_code == 400
    assert (
        client.patch(
            path, json={"version": 1, "equipmentId": int(item["id"])}, headers=actors["coord"]
        ).status_code
        == 200
    )


@pytest.mark.parametrize("selected", [None, True, 0, 999])
def test_new_request_requires_valid_catalogue_item(client, actors, planning_event, item, selected):
    payload = {"quantity": 1}
    if selected is not None:
        payload["equipmentId"] = selected
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=payload, headers=actors["coord"]
    )
    assert response.status_code in (400, 422)


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


def test_missing_notification_kind_returns_clear_error(
    client, actors, line, item, equipment_repository, monkeypatch
):
    from postgrest.exceptions import APIError

    def fail(*args, **kwargs):
        raise APIError(
            {
                "code": "23514",
                "message": 'new row violates check constraint "notifications_kind_valid"',
            }
        )

    monkeypatch.setattr(equipment_repository, "decide", fail)
    response = reserve(client, actors, line, item)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "equipment_configuration_error"
    assert "notifications are not configured" in response.json()["detail"]["message"]
    assert equipment_repository.get_request(int(line["id"])).status == "Requested"




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
