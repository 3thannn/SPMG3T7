"""The equipment stores' own guards and the Supabase store's queries — US19.

The equipment routes run against `InMemoryEquipment`. The first half of this
file drives `SupabaseEquipment` against the fake client and checks what it asks
for: a request is only edited or removed at the version it was read at and
while it is still open, and the availability and decision rules run in the
database. The second half covers the in-memory store's refusals, which the
routes check for themselves before they would ever reach them.
"""

from dataclasses import replace

import pytest

from app.equipment_store import (
    Equipment,
    EquipmentRequest,
    InMemoryEquipment,
    SupabaseEquipment,
)
from app.event_status import EventStatus
from tests.conftest import TECH_SUPPORT_ID

ITEM_ROW = {
    "id": 5,
    "name": "Wireless microphone",
    "equipment_type": "Audio",
    "description": None,
    "location": "Store room B",
    "total_quantity": 10,
    "out_of_service_quantity": 1,
    "out_of_service_reason": None,
}

REQUEST_ROW = {
    "id": 30,
    "event_id": 7,
    "equipment_type": "Audio",
    "quantity": 2,
    "technical_requirements": None,
    "support_notes": None,
    "start_at": "2026-11-02T18:00:00",
    "end_at": "2026-11-02T21:00:00",
    "status": "Requested",
    "requested_by_id": 2,
    "created_at": "2026-10-01T09:00:00",
    "version": 1,
    "updated_by_id": 2,
    "equipment_id": None,
    "unavailable_reason": None,
    "requested_equipment_id": 5,
    "requested_equipment": {"name": "Wireless microphone"},
    "events": {"name": "Faculty Welcome Night"},
}


def item(**overrides) -> Equipment:
    fields = dict(
        id=0,
        name="Wireless microphone",
        equipment_type="Audio",
        description="",
        location="Store room B",
        total_quantity=10,
        out_of_service_quantity=1,
        out_of_service_reason="",
    )
    return Equipment(**{**fields, **overrides})


def request(**overrides) -> EquipmentRequest:
    fields = dict(
        id=30,
        event_id=7,
        equipment_type="Audio",
        quantity=2,
        technical_requirements="",
        support_notes="",
        starts_at="2026-11-02T18:00:00",
        ends_at="2026-11-02T21:00:00",
        status="Requested",
        requested_by_id=2,
        created_at="2026-10-01T09:00:00",
        version=1,
        updated_by_id=2,
        requested_equipment_id=5,
    )
    return EquipmentRequest(**{**fields, **overrides})


class TestTheCatalogue:
    def test_items_are_listed_by_name(self, fake):
        fake.rows = {"equipment": [dict(ITEM_ROW)]}

        [listed] = SupabaseEquipment().list_items()

        assert ("order", "name", False) in fake.on("equipment")[0].calls
        assert listed.description == ""
        assert listed.out_of_service_reason == ""

    def test_a_missing_item_is_none(self, fake):
        assert SupabaseEquipment().get_item(404) is None

    def test_a_new_item_is_inserted_and_read_back(self, fake):
        fake.queued = {"equipment": [[{"id": 5}], [dict(ITEM_ROW)]]}

        saved = SupabaseEquipment().save_item(item())

        assert fake.on("equipment")[0].named("insert")
        assert saved.id == 5

    def test_an_existing_item_is_updated_in_place(self, fake):
        fake.queued = {"equipment": [[{"id": 5}], [dict(ITEM_ROW)]]}

        SupabaseEquipment().save_item(item(id=5))

        calls = fake.on("equipment")[0].calls
        assert calls[0][0] == "update"
        assert ("eq", "id", 5) in calls

    def test_a_save_that_returns_no_row_is_an_error_not_a_silent_success(self, fake):
        fake.queued = {"equipment": [[]]}

        with pytest.raises(RuntimeError, match="no row"):
            SupabaseEquipment().save_item(item())

    def test_deleting_targets_one_item(self, fake):
        SupabaseEquipment().delete_item(5)

        calls = fake.on("equipment")[0].calls
        assert calls == [("delete",), ("eq", "id", 5)]


class TestRequests:
    def test_an_events_open_lines_leave_out_removed_ones_unless_asked(self, fake):
        fake.rows = {"equipment_requests": [dict(REQUEST_ROW)]}

        [line] = SupabaseEquipment().list_for_event(7)
        SupabaseEquipment().list_for_event(7, include_removed=True)

        open_only, everything = fake.on("equipment_requests")
        assert ("in", "status", ["Requested", "Reserved", "Unavailable"]) in open_only.calls
        assert ("in", "status", ["Requested", "Reserved", "Unavailable", "Removed"]) in (
            everything.calls
        )
        assert line.event_title == "Faculty Welcome Night"
        assert line.equipment_name == "Wireless microphone"


    def test_technical_supports_queue_is_every_requested_line(self, fake):
        SupabaseEquipment().list_requested()

        assert ("eq", "status", "Requested") in fake.on("equipment_requests")[0].calls

    def test_a_missing_request_is_none(self, fake):
        assert SupabaseEquipment().get_request(404) is None

    def test_a_new_line_is_inserted_and_read_back(self, fake):
        fake.queued = {"equipment_requests": [[{"id": 30}], [dict(REQUEST_ROW)]]}

        created = SupabaseEquipment().create_request(request(id=0))

        [insert] = fake.on("equipment_requests")[0].named("insert")
        assert insert[1]["updated_by_id"] == insert[1]["requested_by_id"] == 2
        assert created.id == 30

    def test_an_insert_that_returns_no_row_is_an_error(self, fake):
        fake.queued = {"equipment_requests": [[]]}

        with pytest.raises(RuntimeError, match="no row"):
            SupabaseEquipment().create_request(request(id=0))

    def test_an_edit_is_guarded_by_version_and_open_status(self, fake):
        fake.queued = {"equipment_requests": [[{"id": 30}], [dict(REQUEST_ROW, version=2)]]}

        updated = SupabaseEquipment().update_request(request(quantity=3), expected_version=1)

        calls = fake.on("equipment_requests")[0].calls
        assert ("eq", "version", 1) in calls
        assert ("in", "status", ["Requested", "Unavailable"]) in calls
        assert calls[0][1]["version"] == 2
        assert updated is not None and updated.version == 2

    def test_an_edit_that_matched_nothing_is_none(self, fake):
        fake.queued = {"equipment_requests": [[]]}

        assert SupabaseEquipment().update_request(request(), expected_version=1) is None

    def test_removing_keeps_the_row_marked_removed(self, fake):
        fake.rows = {"equipment_requests": [{"id": 30}]}

        assert SupabaseEquipment().delete_request(30, expected_version=1, actor_id=2) is True

        [update] = fake.on("equipment_requests")[0].named("update")
        assert update[1]["status"] == "Removed"
        assert update[1]["updated_by_id"] == 2

    def test_removing_a_line_that_moved_on_is_refused(self, fake):
        assert SupabaseEquipment().delete_request(30, expected_version=1, actor_id=2) is False

    def test_history_is_newest_first(self, fake):
        fake.rows = {
            "equipment_request_history": [
                {
                    "id": 1,
                    "request_id": 30,
                    "event_id": 7,
                    "actor_id": 2,
                    "action": "Created",
                    "changed_at": "2026-10-01T09:00:00",
                    "before_data": None,
                    "after_data": {"quantity": 2},
                }
            ]
        }

        [entry] = SupabaseEquipment().list_history(7)

        orders = fake.on("equipment_request_history")[0].named("order")
        assert orders == [("order", "changed_at", True), ("order", "id", True)]
        assert entry.after == {"quantity": 2}


class TestDatabaseRules:
    def test_availability_is_the_databases_answer(self, fake):
        fake.rpc_answers = {"equipment_availability": [{"equipmentId": "5"}]}

        assert SupabaseEquipment().availability(30) == [{"equipmentId": "5"}]
        assert fake.rpcs == [("equipment_availability", {"p_request_id": 30})]

    def test_no_answer_is_no_stock(self, fake):
        assert SupabaseEquipment().availability(30) == []

    def test_a_decision_is_passed_through_whole(self, fake):
        fake.rpc_answers = {"decide_equipment_request": {"code": "ok"}}

        answer = SupabaseEquipment().decide(30, 1, TECH_SUPPORT_ID, 5, "")

        assert answer == {"code": "ok"}
        [(name, arguments)] = fake.rpcs
        assert name == "decide_equipment_request"
        assert arguments["p_equipment_id"] == 5


class TestInMemoryRefusals:
    """The stand-in has to refuse what the real store refuses."""

    def test_an_edit_at_a_stale_version_is_refused(self):
        store = InMemoryEquipment()
        created = store.create_request(request(id=0))

        assert store.update_request(created, expected_version=created.version + 1) is None

    def test_an_unknown_request_has_no_availability(self):
        assert InMemoryEquipment().availability(404) == []

    def test_only_technical_support_may_decide(self):
        store = InMemoryEquipment()
        created = store.create_request(request(id=0))

        # 2 is the fixture Coordinator.
        assert store.decide(created.id, created.version, 2, None, "") == {"code": "forbidden"}

    def test_an_edit_that_leaves_enough_stock_for_its_reservations_is_allowed(self):
        store = InMemoryEquipment()
        saved = store.save_item(item())
        store.requests.append(
            request(id=40, status="Reserved", equipment_id=saved.id, quantity=2)
        )

        renamed = store.save_item(replace(saved, description="Spare batteries in the case"))

        assert renamed.description == "Spare batteries in the case"

    def test_a_decision_on_an_event_with_no_coordinator_notifies_nobody(
        self, event_repository, notification_repository
    ):
        """A Planning event normally has a Coordinator; data from before US8.3 may not."""
        event = event_repository.create_event(
            title="Open Day",
            purpose="Welcome",
            description="Tours.",
            starts_at="2026-11-02T09:00",
            ends_at="2026-11-02T17:00",
            expected_attendance=40,
            organiser_id=1,
        )
        event_repository._replace(replace(event, status=EventStatus.PLANNING))
        store = InMemoryEquipment()
        created = store.create_request(request(id=0, event_id=event.id))

        answer = store.decide(created.id, created.version, TECH_SUPPORT_ID, None, "None left")

        assert answer == {"code": "ok"}
        assert notification_repository.notifications == []
