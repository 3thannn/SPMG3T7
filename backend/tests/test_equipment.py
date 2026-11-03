"""US19 catalogue, request, queue, notification, and boundary tests."""

from dataclasses import replace

import pytest
from postgrest.exceptions import APIError

from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, SUBMITTABLE_NEEDS, TECH_SUPPORT_ID

ITEM = {
    "name": "Wireless microphone",
    "type": "Microphone",
    "description": "UHF",
    "location": "AV Store",
    "totalQuantity": 5,
    "outOfServiceQuantity": 2,
    "outOfServiceReason": "Battery damage",
}
LINE = {
    "equipmentId": 1,
    "equipmentType": "Microphone",
    "quantity": 1,
    "technicalRequirements": "Two channels",
}


@pytest.fixture
def actors(auth_headers):
    return {
        "tech": auth_headers("Technical Support"),
        "coord": auth_headers("Event Coordinator"),
        "organiser": auth_headers("Event Organiser"),
        "lead": auth_headers("Event Coordinator Lead"),
    }


@pytest.fixture
def approved_event(client, actors):
    created = client.post(
        "/events",
        json={
            "title": "Open Day",
            "purpose": "Welcome new students",
            "description": "Campus tours and talks.",
            "startsAt": "2027-11-02T09:00",
            "endsAt": "2027-11-02T17:00",
            "expectedAttendance": 40,
            **SUBMITTABLE_NEEDS,
        },
        headers=actors["organiser"],
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=actors["organiser"]).status_code == 200
    assert (
        client.post(
            f"/events/{event_id}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=actors["lead"],
        ).status_code
        == 200
    )
    assert client.post(f"/events/{event_id}/approve", headers=actors["coord"]).status_code == 200
    return event_id


@pytest.fixture
def planning_event(approved_event, event_repository):
    event_repository.plan_event(int(approved_event), actor_id=COORDINATOR_ID)
    return approved_event


@pytest.fixture
def item(client, actors):
    response = client.post("/equipment", json=ITEM, headers=actors["tech"])
    assert response.status_code == 201, response.text
    return response.json()


def test_catalogue_happy_path_and_permissions(client, actors, item):
    assert item["usableQuantity"] == 3
    assert len(client.get("/equipment", headers=actors["coord"]).json()) == 1
    assert len(client.get("/equipment", headers=actors["lead"]).json()) == 1
    assert client.post("/equipment", json=ITEM, headers=actors["coord"]).status_code == 403
    assert client.get("/equipment", headers=actors["organiser"]).status_code == 403
    updated = client.put(
        f"/equipment/{item['id']}", json={**ITEM, "outOfServiceQuantity": 5}, headers=actors["tech"]
    )
    assert updated.status_code == 200
    assert updated.json()["usableQuantity"] == 0






TOTAL_RANGE = "Total quantity must be between zero and 2,147,483,647."
OUT_OF_SERVICE_RANGE = "Out-of-service units must be between zero and total quantity."
REQUIRED = "Name, type, and location are required."


@pytest.mark.parametrize(
    ("changes", "status", "message"),
    [
        ({"totalQuantity": -1}, 400, TOTAL_RANGE),
        ({"totalQuantity": 2_147_483_648}, 400, TOTAL_RANGE),
        ({"totalQuantity": 1.5}, 422, None),
        ({"totalQuantity": True}, 422, None),
        ({"outOfServiceQuantity": -1}, 400, OUT_OF_SERVICE_RANGE),
        ({"outOfServiceQuantity": 6}, 400, OUT_OF_SERVICE_RANGE),
        ({"outOfServiceReason": " "}, 400, "Give a reason for out-of-service units."),
        ({"name": " "}, 400, REQUIRED),
        ({"type": " "}, 400, REQUIRED),
    ],
)
def test_catalogue_invalid_values(client, actors, changes, status, message):
    """US19.1 AC1/AC2: each bad value is refused with its own reason.

    A fraction or a boolean is refused by the schema (422) before the rules run.
    ITEM has 5 units, so 6 out of service is one more than the total.
    """
    response = client.post("/equipment", json={**ITEM, **changes}, headers=actors["tech"])

    assert response.status_code == status
    if message:
        assert response.json()["detail"] == {"code": "invalid_equipment", "message": message}
    assert client.get("/equipment", headers=actors["tech"]).json() == []


def test_zero_stock_is_valid(client, actors):
    response = client.post(
        "/equipment",
        json={**ITEM, "totalQuantity": 0, "outOfServiceQuantity": 0, "outOfServiceReason": ""},
        headers=actors["tech"],
    )
    assert response.status_code == 201
    assert response.json()["usableQuantity"] == 0








def test_request_happy_path_and_notifications(
    client, actors, planning_event, item, event_repository
):
    event_id = planning_event
    created = client.post(
        f"/events/{event_id}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert created.status_code == 201, created.text
    line = created.json()
    assert line["status"] == "Requested"
    assert line["startsAt"] == "2027-11-02T09:00"
    assert line["endsAt"] == "2027-11-02T17:00"
    assert line["quantity"] == 1
    assert event_repository.get_event(int(event_id)).status is EventStatus.PLANNING
    assert (
        client.get(f"/events/{event_id}/equipment-requests", headers=actors["organiser"]).json()[0][
            "id"
        ]
        == line["id"]
    )
    assert (
        client.get(f"/events/{event_id}/equipment-requests", headers=actors["lead"]).json()[0]["id"]
        == line["id"]
    )
    assert (
        client.get(f"/events/{event_id}/equipment-requests", headers=actors["tech"]).status_code
        == 403
    )
    assert (
        len(client.get(f"/events/{event_id}/equipment-requests", headers=actors["coord"]).json())
        == 1
    )
    assert client.get("/equipment-requests", headers=actors["tech"]).json()[0]["id"] == line["id"]
    notices = client.get("/notifications", headers=actors["tech"]).json()
    assert len(notices) == 1
    assert notices[0]["kind"] == "equipment-request"
    assert notices[0]["equipmentRequestId"] == line["id"]
    assert (
        client.get("/notifications", headers=actors["organiser"]).json()[-1]["kind"]
        == "event-status"
    )
    read = client.patch(
        f"/notifications/{notices[0]['id']}", json={"read": True}, headers=actors["tech"]
    )
    assert read.json()["read"] is True
    unread = client.patch(
        f"/notifications/{notices[0]['id']}", json={"read": False}, headers=actors["tech"]
    )
    assert unread.json()["read"] is False
    assert (
        client.patch(
            f"/notifications/{notices[0]['id']}", json={"read": True}, headers=actors["organiser"]
        ).status_code
        == 404
    )








QUANTITY_RANGE = ("invalid_quantity", "Quantity must be between one and 2,147,483,647.")
END_AFTER_START = ("invalid_time", "The needed end time must be after the start time.")


@pytest.mark.parametrize(
    ("changes", "status", "detail"),
    [
        (
            {"equipmentType": "Unknown"},
            400,
            ("invalid_equipment_type", "The selected item does not match that equipment type."),
        ),
        ({"quantity": 0}, 400, QUANTITY_RANGE),
        ({"quantity": 2_147_483_648}, 400, QUANTITY_RANGE),
        ({"quantity": 1.5}, 422, None),
        ({"quantity": True}, 422, None),
        ({"startsAt": "2027-11-02T17:00", "endsAt": "2027-11-02T09:00"}, 400, END_AFTER_START),
        ({"startsAt": "2027-11-02T09:00", "endsAt": "2027-11-02T09:00"}, 400, END_AFTER_START),
    ],
)
def test_request_invalid_inputs(client, actors, planning_event, item, changes, status, detail):
    """US19.2 AC1: quantity is a whole number of at least 1; the window must have length."""
    response = client.post(
        f"/events/{planning_event}/equipment-requests",
        json={**LINE, **changes},
        headers=actors["coord"],
    )

    assert response.status_code == status
    if detail:
        code, message = detail
        assert response.json()["detail"] == {"code": code, "message": message}
    assert client.get("/notifications", headers=actors["tech"]).json() == []
    assert client.get("/equipment-requests", headers=actors["tech"]).json() == []


def test_roles_status_and_stale_edits(client, actors, planning_event, item, event_repository):
    path = f"/events/{planning_event}/equipment-requests"
    assert client.post(path, json=LINE, headers=actors["tech"]).status_code == 403
    assert client.post(path, json=LINE, headers=actors["organiser"]).status_code == 403
    created = client.post(path, json=LINE, headers=actors["coord"]).json()
    request_path = f"/equipment-requests/{created['id']}"
    assert (
        client.patch(
            request_path, json={"version": 1, "supportNotes": "Ready"}, headers=actors["coord"]
        ).status_code
        == 403
    )
    changed = client.patch(
        request_path,
        json={"version": 1, "supportNotes": "Checked", "quantity": 2},
        headers=actors["tech"],
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["technicalRequirements"] == "Two channels"
    assert changed.json()["version"] == 2
    assert (
        client.patch(
            request_path, json={"version": 1, "quantity": 3}, headers=actors["coord"]
        ).status_code
        == 409
    )
    assert client.delete(f"{request_path}?version=1", headers=actors["coord"]).status_code == 409
    assert client.delete(f"{request_path}?version=2", headers=actors["coord"]).status_code == 204
    assert client.get("/equipment-requests", headers=actors["tech"]).json() == []
    # An event that leaves Planning freezes remaining Requested lines.
    again = client.post(path, json=LINE, headers=actors["coord"]).json()
    current = event_repository.get_event(int(planning_event))
    event_repository._replace(replace(current, status=EventStatus.CONFIRMED))
    assert (
        client.patch(
            f"/equipment-requests/{again['id']}",
            json={"version": 1, "quantity": 2},
            headers=actors["tech"],
        ).status_code
        == 409
    )








def test_queue_ties_and_multiple_recipients(
    client, actors, planning_event, item, user_store, equipment_repository, notification_repository
):
    user_store.users.append(User(7, "tech2@example.edu", "Second tech", Role.TECH_SUPPORT))
    user_store.passwords["tech2@example.edu"] = "Sprint1!demo"
    path = f"/events/{planning_event}/equipment-requests"
    first = client.post(path, json=LINE, headers=actors["coord"]).json()
    second = client.post(path, json={**LINE, "quantity": 9}, headers=actors["coord"]).json()
    equipment_repository.requests = [
        replace(r, created_at="2027-01-01T00:00:00") for r in equipment_repository.requests
    ]
    assert [r["id"] for r in client.get("/equipment-requests", headers=actors["tech"]).json()] == [
        first["id"],
        second["id"],
    ]
    assert (
        len(
            [
                n
                for n in client.get("/notifications", headers=actors["tech"]).json()
                if n["kind"] == "equipment-request"
            ]
        )
        == 2
    )
    assert {
        n.user_id for n in notification_repository.notifications if n.kind == "equipment-request"
    } == {TECH_SUPPORT_ID, 7}
    second_login = client.post(
        "/auth/login", json={"email": "tech2@example.edu", "password": "Sprint1!demo"}
    ).json()
    other = {"Authorization": f"Bearer {second_login['token']}"}
    other_notices = client.get("/notifications", headers=other).json()
    assert len(other_notices) == 2
    assert set(n["id"] for n in other_notices).isdisjoint(
        n["id"] for n in client.get("/notifications", headers=actors["tech"]).json()
    )
    assert (
        client.patch(
            f"/notifications/{other_notices[0]['id']}",
            json={"read": True},
            headers=actors["tech"],
        ).status_code
        == 404
    )












# -- Refusals and database errors the paths above never reach ----------------


def database_error(code: str, message: str) -> APIError:
    return APIError({"code": code, "details": None, "hint": None, "message": message})


def raising(error: APIError):
    def fail(*_args, **_kwargs):
        raise error

    return fail


def legacy_line(**overrides) -> EquipmentRequest:
    """A request row as stored, for states the routes can no longer create."""
    fields = dict(
        id=50,
        event_id=1,
        equipment_type="Microphone",
        quantity=1,
        technical_requirements="",
        support_notes="",
        starts_at="2027-11-02T09:00",
        ends_at="2027-11-02T17:00",
        status="Requested",
        requested_by_id=COORDINATOR_ID,
        created_at="2026-10-01T09:00:00",
        version=1,
    )
    return EquipmentRequest(**{**fields, **overrides})




















@pytest.fixture
def open_line(client, actors, planning_event, item) -> dict:
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 201, response.text
    return response.json()














