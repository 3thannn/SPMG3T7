"""US19 catalogue, request, queue, notification, and boundary tests."""

from dataclasses import replace

import pytest
from postgrest.exceptions import APIError

from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, SUBMITTABLE_NEEDS

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


def test_catalogue_delete_missing_and_role_boundaries(client, actors, item):
    path = f"/equipment/{item['id']}"
    assert client.delete(path, headers=actors["coord"]).status_code == 403
    assert client.delete("/equipment/999", headers=actors["tech"]).status_code == 404
    assert client.delete(path, headers=actors["tech"]).status_code == 204
    assert client.get(path, headers=actors["tech"]).status_code == 404


def test_last_type_with_active_request_cannot_be_deleted_or_renamed(
    client, actors, planning_event, item
):
    path = f"/equipment/{item['id']}"
    created = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    ).json()
    blocked = client.delete(path, headers=actors["tech"])
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "equipment_in_use"
    renamed = client.put(path, json={**ITEM, "type": "Speaker"}, headers=actors["tech"])
    assert renamed.status_code == 409
    assert client.get(path, headers=actors["tech"]).json()["type"] == "Microphone"

    another = client.post(
        "/equipment", json={**ITEM, "name": "Spare microphone"}, headers=actors["tech"]
    ).json()
    assert client.delete(path, headers=actors["tech"]).status_code == 409
    assert client.delete(f"/equipment/{another['id']}", headers=actors["tech"]).status_code == 204
    assert (
        client.delete(
            f"/equipment-requests/{created['id']}?version=1", headers=actors["coord"]
        ).status_code
        == 204
    )
    assert (
        client.delete(path, headers=actors["tech"]).status_code == 409
    )  # Retain historical linkage.


@pytest.mark.parametrize(
    "changes",
    [
        {"totalQuantity": -1},
        {"totalQuantity": 1.5},
        {"totalQuantity": True},
        {"totalQuantity": 2_147_483_648},
        {"outOfServiceQuantity": -1},
        {"outOfServiceQuantity": 6},
        {"outOfServiceReason": " "},
        {"name": " "},
        {"type": " "},
    ],
)
def test_catalogue_invalid_values(client, actors, changes):
    response = client.post("/equipment", json={**ITEM, **changes}, headers=actors["tech"])
    assert response.status_code in (400, 422)










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




def test_request_requires_end_time_when_event_has_none(
    client, actors, planning_event, item, event_repository
):
    event = event_repository.get_event(int(planning_event))
    event_repository._replace(replace(event, ends_at=""))
    path = f"/events/{planning_event}/equipment-requests"

    missing = client.post(path, json=LINE, headers=actors["coord"])
    assert missing.status_code == 400
    assert missing.json()["detail"] == {
        "code": "invalid_time",
        "message": "Enter a needed end time for this equipment request.",
    }
    assert client.get(path, headers=actors["coord"]).json() == []

    created = client.post(
        path, json={**LINE, "endsAt": "2027-11-02T17:00"}, headers=actors["coord"]
    )
    assert created.status_code == 201, created.text
    assert created.json()["startsAt"] == "2027-11-02T09:00"
    assert created.json()["endsAt"] == "2027-11-02T17:00"




@pytest.mark.parametrize(
    "changes",
    [
        {"equipmentType": "Unknown"},
        {"quantity": 0},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": 2_147_483_648},
        {"startsAt": "2027-11-02T17:00", "endsAt": "2027-11-02T09:00"},
        {"startsAt": "2027-11-02T09:00", "endsAt": "2027-11-02T09:00"},
    ],
)
def test_request_invalid_inputs(client, actors, planning_event, item, changes):
    response = client.post(
        f"/events/{planning_event}/equipment-requests",
        json={**LINE, **changes},
        headers=actors["coord"],
    )
    assert response.status_code in (400, 422)
    assert client.get("/notifications", headers=actors["tech"]).json() == []


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


def test_coordinator_and_support_edit_only_their_fields(client, actors, planning_event, item):
    second_item = client.post(
        "/equipment",
        json={**ITEM, "name": "Speaker", "type": "Speaker"},
        headers=actors["tech"],
    )
    assert second_item.status_code == 201
    created = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    ).json()
    path = f"/equipment-requests/{created['id']}"
    assert client.delete(f"{path}?version=1", headers=actors["tech"]).status_code == 403
    assert (
        client.patch(
            path, json={"version": 1, "equipmentType": "Speaker"}, headers=actors["tech"]
        ).status_code
        == 403
    )
    assert (
        client.patch(path, json={"version": 1, "quantity": 0}, headers=actors["tech"]).status_code
        == 400
    )
    assert (
        client.patch(
            path, json={"version": 1, "startsAt": "2027-11-02T18:00"}, headers=actors["tech"]
        ).status_code
        == 400
    )
    changed = client.patch(
        path,
        json={
            "version": 1,
            "equipmentId": int(second_item.json()["id"]),
            "equipmentType": "Speaker",
            "technicalRequirements": "Stereo",
        },
        headers=actors["coord"],
    )
    assert changed.status_code == 200
    assert changed.json()["equipmentType"] == "Speaker"
    assert changed.json()["technicalRequirements"] == "Stereo"
    assert changed.json()["supportNotes"] == ""
    notices = client.get("/notifications", headers=actors["tech"]).json()
    assert len(notices) == 2
    assert any("updated the Speaker request" in notice["message"] for notice in notices)


def test_read_request_notification_is_followed_by_edit_and_removal_notifications(
    client, actors, planning_event, item
):
    created = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    ).json()
    path = f"/equipment-requests/{created['id']}"
    original = client.get("/notifications", headers=actors["tech"]).json()[0]
    assert (
        client.patch(
            f"/notifications/{original['id']}", json={"read": True}, headers=actors["tech"]
        ).status_code
        == 200
    )

    changed = client.patch(path, json={"version": 1, "quantity": 3}, headers=actors["coord"])
    assert changed.status_code == 200, changed.text
    notices = client.get("/notifications", headers=actors["tech"]).json()
    assert len(notices) == 2
    assert notices[0]["read"] is False
    assert notices[0]["equipmentRequestId"] == created["id"]
    assert "Priya updated" in notices[0]["message"]
    assert next(notice for notice in notices if notice["id"] == original["id"])["read"] is True

    no_change = client.patch(path, json={"version": 2, "quantity": 3}, headers=actors["coord"])
    assert no_change.status_code == 200
    assert len(client.get("/notifications", headers=actors["tech"]).json()) == 2
    support_edit = client.patch(
        path, json={"version": 3, "supportNotes": "Ready"}, headers=actors["tech"]
    )
    assert support_edit.status_code == 200
    assert len(client.get("/notifications", headers=actors["tech"]).json()) == 2

    assert client.delete(f"{path}?version=4", headers=actors["coord"]).status_code == 204
    notices = client.get("/notifications", headers=actors["tech"]).json()
    assert len(notices) == 3
    assert notices[0]["read"] is False
    assert "Priya removed" in notices[0]["message"]
    assert notices[0]["equipmentRequestId"] == created["id"]
    assert client.get("/equipment-requests", headers=actors["tech"]).json() == []
    detail = client.get(path, headers=actors["tech"])
    assert detail.status_code == 200
    assert detail.json()["status"] == "Removed"
    assert detail.json()["removedByName"] == "Priya"
    assert client.get(path, headers=actors["coord"]).status_code == 403
    assert client.get(path, headers=actors["organiser"]).status_code == 403
    assert client.get("/equipment-requests/99999", headers=actors["tech"]).status_code == 404


def test_unassigned_coordinator_cannot_see_or_change_requests(
    client, actors, planning_event, item, user_store
):
    user_store.users.append(User(7, "other-coordinator@example.edu", "Other", Role.COORDINATOR))
    user_store.passwords["other-coordinator@example.edu"] = "Sprint1!demo"
    signed_in = client.post(
        "/auth/login",
        json={"email": "other-coordinator@example.edu", "password": "Sprint1!demo"},
    ).json()
    other = {"Authorization": f"Bearer {signed_in['token']}"}
    path = f"/events/{planning_event}/equipment-requests"
    assert client.post(path, json=LINE, headers=other).status_code == 404
    assert client.get(path, headers=other).status_code == 404
    created = client.post(path, json=LINE, headers=actors["coord"]).json()
    assert (
        client.patch(
            f"/equipment-requests/{created['id']}",
            json={"version": 1, "quantity": 2},
            headers=other,
        ).status_code
        == 404
    )




def test_notification_failure_does_not_fail_request(
    client, actors, planning_event, item, notification_repository, monkeypatch
):
    def fail(**_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(notification_repository, "create_equipment", fail)
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 201


def test_recipient_lookup_failure_does_not_fail_stored_request(
    client, actors, planning_event, item, equipment_repository, monkeypatch
):
    from app import users

    def fail():
        raise RuntimeError("directory unavailable")

    monkeypatch.setattr(users, "list_users", fail)
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 201, response.text
    assert [request.id for request in equipment_repository.requests] == [int(response.json()["id"])]


def test_equipment_history_records_create_edit_and_remove(client, actors, planning_event, item):
    event_path = f"/events/{planning_event}"
    history_path = f"{event_path}/equipment-history"
    created = client.post(
        f"{event_path}/equipment-requests", json=LINE, headers=actors["coord"]
    ).json()
    request_path = f"/equipment-requests/{created['id']}"
    initial = client.get(history_path, headers=actors["coord"])
    assert initial.status_code == 200
    assert len(initial.json()) == 1
    assert initial.json()[0]["action"] == "Created"
    assert initial.json()[0]["byName"] == "Priya"
    assert initial.json()[0]["after"]["quantity"] == 1
    assert initial.json()[0]["before"] is None

    edited = client.patch(
        request_path,
        json={"version": 1, "quantity": 2, "supportNotes": "Tested"},
        headers=actors["tech"],
    )
    assert edited.status_code == 200
    assert (
        client.patch(
            request_path, json={"version": 1, "quantity": 3}, headers=actors["coord"]
        ).status_code
        == 409
    )
    assert (
        client.patch(
            request_path, json={"version": 2, "quantity": 0}, headers=actors["coord"]
        ).status_code
        == 400
    )
    middle = client.get(history_path, headers=actors["coord"]).json()
    assert [entry["action"] for entry in middle] == ["Updated", "Created"]
    assert middle[0]["byName"] == "Bryan"
    assert middle[0]["before"]["quantity"] == 1
    assert middle[0]["after"]["quantity"] == 2
    assert middle[0]["after"]["support_notes"] == "Tested"

    assert client.delete(f"{request_path}?version=2", headers=actors["coord"]).status_code == 204
    assert client.get(f"{event_path}/equipment-requests", headers=actors["coord"]).json() == []
    assert client.get("/equipment-requests", headers=actors["tech"]).json() == []
    history = client.get(history_path, headers=actors["coord"]).json()
    assert [entry["action"] for entry in history] == ["Removed", "Updated", "Created"]
    assert history[0]["before"]["quantity"] == 2
    assert history[0]["after"] is None
    assert history[0]["byName"] == "Priya"
    assert client.delete(f"{request_path}?version=2", headers=actors["coord"]).status_code == 409
    assert len(client.get(history_path, headers=actors["coord"]).json()) == 3


def test_equipment_history_is_assignment_scoped(client, actors, planning_event, item, user_store):
    path = f"/events/{planning_event}/equipment-history"
    assert client.get(path, headers=actors["tech"]).status_code == 403
    assert client.get(path, headers=actors["organiser"]).status_code == 200
    user_store.users.append(User(7, "other-coordinator@example.edu", "Other", Role.COORDINATOR))
    user_store.passwords["other-coordinator@example.edu"] = "Sprint1!demo"
    login = client.post(
        "/auth/login", json={"email": "other-coordinator@example.edu", "password": "Sprint1!demo"}
    ).json()
    other = {"Authorization": f"Bearer {login['token']}"}
    assert client.get(path, headers=other).status_code == 404
    user_store.users.append(User(8, "other-organiser@example.edu", "Another", Role.ORGANISER))
    user_store.passwords["other-organiser@example.edu"] = "Sprint1!demo"
    login = client.post(
        "/auth/login", json={"email": "other-organiser@example.edu", "password": "Sprint1!demo"}
    ).json()
    assert (
        client.get(path, headers={"Authorization": f"Bearer {login['token']}"}).status_code == 404
    )


def test_database_planning_race_has_clear_conflict_and_no_audit_entry(
    client, actors, planning_event, item, equipment_repository, monkeypatch
):
    def event_left_planning(_request):
        raise APIError(
            {
                "code": "P0001",
                "details": None,
                "hint": None,
                "message": "Equipment requests can only change while the event is Planning",
            }
        )

    monkeypatch.setattr(equipment_repository, "create_request", event_left_planning)
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rule_refused"
    assert (
        client.get(f"/events/{planning_event}/equipment-history", headers=actors["coord"]).json()
        == []
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


@pytest.mark.parametrize("raw", ["abc", "0", "-3"], ids=["not-a-number", "zero", "negative"])
def test_an_id_that_cannot_name_an_item_is_not_found(client, actors, raw):
    response = client.get(f"/equipment/{raw}", headers=actors["tech"])

    assert response.status_code == 404


def test_a_name_over_255_characters_is_refused(client, actors):
    response = client.post("/equipment", json={**ITEM, "name": "x" * 256}, headers=actors["tech"])

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Name or type is too long."


def test_updating_a_missing_item_is_not_found(client, actors):
    response = client.put("/equipment/999", json=ITEM, headers=actors["tech"])

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "equipment_not_found"


def test_an_unexpected_database_error_on_save_is_not_disguised_as_a_conflict(
    client, actors, item, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository, "save_item", raising(database_error("XX000", "disk full"))
    )

    with pytest.raises(APIError):
        client.put(f"/equipment/{item['id']}", json=ITEM, headers=actors["tech"])




def test_a_type_only_request_from_before_exact_items_still_protects_its_type(
    client, actors, item, equipment_repository
):
    """Rows written before US19 named an exact item ask only for a type."""
    equipment_repository.requests.append(
        legacy_line(equipment_type="microphone", requested_equipment_id=None)
    )

    response = client.delete(f"/equipment/{item['id']}", headers=actors["tech"])

    assert response.status_code == 409
    assert "Active equipment requests still need this type" in (
        response.json()["detail"]["message"]
    )


def test_an_unexpected_database_error_on_a_request_is_raised_not_hidden(
    client, actors, planning_event, item, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository, "create_request", raising(database_error("XX000", "disk full"))
    )

    with pytest.raises(APIError):
        client.post(
            f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
        )


def test_times_that_are_not_times_are_refused(client, actors, planning_event, item):
    response = client.post(
        f"/events/{planning_event}/equipment-requests",
        json={**LINE, "startsAt": "after lunch", "endsAt": "teatime"},
        headers=actors["coord"],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Enter valid start and end times."


def test_availability_for_a_missing_request_is_not_found(client, actors):
    response = client.get("/equipment-requests/999/availability", headers=actors["tech"])

    assert response.status_code == 404


@pytest.fixture
def open_line(client, actors, planning_event, item) -> dict:
    response = client.post(
        f"/events/{planning_event}/equipment-requests", json=LINE, headers=actors["coord"]
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_an_unexpected_database_error_on_a_decision_is_raised(
    client, actors, item, open_line, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository, "decide", raising(database_error("XX000", "disk full"))
    )

    with pytest.raises(APIError):
        client.post(
            f"/equipment-requests/{open_line['id']}/reserve",
            json={"version": 1, "equipmentId": int(item["id"])},
            headers=actors["tech"],
        )


def test_editing_a_missing_request_is_not_found(client, actors):
    response = client.patch(
        "/equipment-requests/999", json={"version": 1}, headers=actors["coord"]
    )

    assert response.status_code == 404


def test_a_request_whose_event_is_gone_is_not_found(client, actors, equipment_repository):
    equipment_repository.requests.append(legacy_line(id=60, event_id=999))

    response = client.patch(
        "/equipment-requests/60", json={"version": 1, "quantity": 2}, headers=actors["tech"]
    )

    assert response.status_code == 404


def test_an_edit_that_lost_a_race_to_the_event_leaving_planning_is_a_conflict(
    client, actors, open_line, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository,
        "update_request",
        raising(database_error("P0001", "Equipment requests can only change while Planning")),
    )

    response = client.patch(
        f"/equipment-requests/{open_line['id']}",
        json={"version": 1, "quantity": 2},
        headers=actors["coord"],
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rule_refused"


def test_an_edit_that_matched_no_row_is_stale(
    client, actors, open_line, equipment_repository, monkeypatch
):
    monkeypatch.setattr(equipment_repository, "update_request", lambda *_args: None)

    response = client.patch(
        f"/equipment-requests/{open_line['id']}",
        json={"version": 1, "quantity": 2},
        headers=actors["coord"],
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_request"


def test_a_removal_that_lost_a_race_to_the_event_leaving_planning_is_a_conflict(
    client, actors, open_line, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository,
        "delete_request",
        raising(database_error("P0001", "Equipment requests can only change while Planning")),
    )

    response = client.delete(
        f"/equipment-requests/{open_line['id']}?version=1", headers=actors["coord"]
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "rule_refused"


def test_an_unexpected_database_error_on_delete_is_raised_not_hidden(
    client, actors, item, equipment_repository, monkeypatch
):
    monkeypatch.setattr(
        equipment_repository, "delete_item", raising(database_error("XX000", "disk full"))
    )

    with pytest.raises(APIError):
        client.delete(f"/equipment/{item['id']}", headers=actors["tech"])
