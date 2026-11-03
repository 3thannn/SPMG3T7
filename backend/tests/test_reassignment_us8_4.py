"""US8.4: the Coordinator Lead reassigns an event.

Acceptance criteria, and the tests that hold each one:

* The Lead can change the assigned Coordinator on any active event; a
  Completed, Cancelled or Rejected one is refused -> `TestActiveEvents`.
* The old and new Coordinator are both notified (US10.2) -> `TestNotices`.
* The old Coordinator loses access (US8.6) -> `TestAccess`.
* Logged with who, when and the previous Coordinator, shown in the event's
  history -> `TestTheLog`.
* reassign_event_coordinator is committed as a migration
  (SUPABASE_US8_4_REASSIGN_COORDINATOR.sql) and tested against Postgres in CI
  -> integration/test_us8_4_db.py. The real store's call to it ->
  `TestTheRealStore`.

tests/test_lead_reassignment.py holds the route's earlier validation tests.
"""

from dataclasses import replace

import pytest

from app import reassignment
from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus
from app.event_store import (
    EVENTS_TABLE,
    Event,
    InMemoryEvents,
    StaleEventStatus,
    StatusChange,
    SupabaseEvents,
)
from app.notifications import CoordinatorNotice
from app.permissions import Role
from app.users import User
from tests.conftest import (
    COORDINATOR_ID,
    COORDINATOR_LEAD_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEED_ATTRS,
)
from tests.test_change_requests import add_user

EVENT_ID = 980
NEW_COORDINATOR_ID = 40
LEAD = "Event Coordinator Lead"
UPDATED_AT = "2099-01-02T12:00:00"


def seed(event_repository, status=EventStatus.PLANNING) -> Event:
    event = Event(
        id=EVENT_ID,
        title="Open House",
        purpose="Welcome visitors",
        description="Tours and talks.",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        expected_attendance=30,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00:00",
        updated_at=UPDATED_AT,
        coordinator_id=COORDINATOR_ID,
        coordinator_name="Priya",
        history=(
            StatusChange(
                EventStatus.SUBMITTED,
                EventStatus.UNDER_REVIEW,
                "2099-01-01T10:00:00",
                COORDINATOR_LEAD_ID,
                "Jordan",
            ),
        ),
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    return event


@pytest.fixture
def new_coordinator(client, user_store, event_repository):
    """Alex, a second Coordinator, signed in."""
    headers = add_user(user_store, client, NEW_COORDINATOR_ID, Role.COORDINATOR)
    user_store.users[-1] = User(
        id=NEW_COORDINATOR_ID,
        email=user_store.users[-1].email,
        name="Alex",
        role=Role.COORDINATOR,
    )
    event_repository.names[NEW_COORDINATOR_ID] = "Alex"
    return headers


def reassign(client, auth_headers, coordinator_id=NEW_COORDINATOR_ID):
    return client.post(
        f"/events/{EVENT_ID}/reassign",
        json={"coordinatorId": str(coordinator_id)},
        headers=auth_headers(LEAD),
    )


class TestActiveEvents:
    @pytest.mark.parametrize(
        "status",
        [
            EventStatus.UNDER_REVIEW,
            EventStatus.APPROVED,
            EventStatus.PLANNING,
            EventStatus.PENDING_SAFETY_CHECK,
            EventStatus.CONFIRMED,
        ],
    )
    def test_any_active_event_can_be_reassigned(
        self, client, auth_headers, event_repository, new_coordinator, status
    ):
        seed(event_repository, status)

        response = reassign(client, auth_headers)

        assert response.status_code == 200, response.text
        assert response.json()["coordinatorId"] == str(NEW_COORDINATOR_ID)
        assert response.json()["coordinatorName"] == "Alex"
        assert response.json()["status"] == str(status)

    @pytest.mark.parametrize(
        "status", [EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED]
    )
    def test_a_finished_event_is_refused(
        self,
        client,
        auth_headers,
        event_repository,
        new_coordinator,
        notification_repository,
        status,
    ):
        seed(event_repository, status)

        response = reassign(client, auth_headers)

        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            f"This event is {status}, so it can no longer be reassigned."
        )
        assert event_repository.get_event(EVENT_ID).coordinator_id == COORDINATOR_ID
        assert notification_repository.notifications == []

    def test_an_event_changed_since_it_was_read_is_refused(
        self, client, auth_headers, event_repository, new_coordinator, monkeypatch
    ):
        seed(event_repository)

        def changed(*_args, **_kwargs):
            raise StaleEventStatus

        monkeypatch.setattr(event_repository, "reassign_coordinator", changed)

        assert reassign(client, auth_headers).status_code == 409

    def test_the_same_coordinator_changes_nothing(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed(event_repository)

        response = reassign(client, auth_headers, COORDINATOR_ID)

        assert response.status_code == 200
        assert len(response.json()["history"]) == 1
        assert notification_repository.notifications == []


class TestNotices:
    def test_both_coordinators_are_told_and_nobody_else(
        self, client, auth_headers, event_repository, new_coordinator, notification_repository
    ):
        seed(event_repository)

        reassign(client, auth_headers)

        assert {(n.user_id, n.kind, n.message) for n in notification_repository.notifications} == {
            (
                COORDINATOR_ID,
                CoordinatorNotice.UNASSIGNED,
                '"Open House" is no longer assigned to you.',
            ),
            (NEW_COORDINATOR_ID, CoordinatorNotice.ASSIGNED, 'You were assigned "Open House".'),
        }

    def test_the_new_coordinator_hears_of_bookings_that_need_replacing(
        self,
        client,
        auth_headers,
        event_repository,
        booking_repository,
        new_coordinator,
        notification_repository,
    ):
        seed(event_repository, EventStatus.CONFIRMED)
        booking_repository.bookings.append(
            Booking(
                id=91,
                event_id=EVENT_ID,
                venue_id=1,
                venue_name="Great Hall",
                starts_at="2099-11-02T09:00",
                ends_at="2099-11-02T17:00",
                status=BookingStatus.NEEDS_REPLACEMENT,
                requested_by_id=COORDINATOR_ID,
                requested_at="2099-01-01T09:00",
                headcount=30,
                replacement_reason="scheduled maintenance",
            )
        )

        reassign(client, auth_headers)

        handover = [
            n.message
            for n in notification_repository.notifications
            if n.user_id == NEW_COORDINATOR_ID and n.kind == CoordinatorNotice.BOOKING_CONFLICT
        ]
        assert handover == [
            '"Open House" has venue bookings that need replacement. Review its bookings.'
        ]


class TestAccess:
    def test_the_old_coordinator_loses_the_event_and_the_new_one_gains_it(
        self, client, auth_headers, event_repository, new_coordinator
    ):
        seed(event_repository)

        reassign(client, auth_headers)

        old = client.get(f"/events/{EVENT_ID}", headers=auth_headers("Event Coordinator"))
        new = client.get(f"/events/{EVENT_ID}", headers=new_coordinator)
        assert old.status_code == 404
        assert new.status_code == 200


class TestTheLog:
    def test_who_when_and_the_previous_coordinator(
        self, client, auth_headers, event_repository, new_coordinator
    ):
        seed(event_repository)

        logged = reassign(client, auth_headers).json()["history"][-1]

        assert (logged["from"], logged["to"]) == ("Planning", "Planning")
        assert (logged["byId"], logged["byName"]) == (str(COORDINATOR_LEAD_ID), "Jordan")
        assert logged["at"] and logged["at"] != UPDATED_AT
        assert logged["notes"] == "Coordinator reassigned from Priya to Alex."
        assert logged["kind"] == "reassignment"

    def test_a_coordinator_without_a_name_is_given_by_id(self, event_repository):
        seed(event_repository)
        store = InMemoryEvents(events=list(event_repository.events), names={})

        moved = store.reassign_coordinator(
            EVENT_ID, 41, reassigned_by_id=COORDINATOR_LEAD_ID, expected_updated_at=UPDATED_AT
        )

        assert moved.history[-1].notes == (
            "Coordinator reassigned from Coordinator 2 to Coordinator 41."
        )

    @pytest.mark.parametrize(
        ("from_status", "to_status", "notes", "kind"),
        [
            (
                EventStatus.PLANNING,
                EventStatus.PLANNING,
                reassignment.note("A", "B"),
                "reassignment",
            ),
            # US7.3's follow-up question also keeps the status, with its own note.
            (EventStatus.UNDER_REVIEW, EventStatus.UNDER_REVIEW, "Which room?", ""),
            (
                EventStatus.PLANNING,
                EventStatus.PENDING_SAFETY_CHECK,
                reassignment.note("A", "B"),
                "",
            ),
        ],
    )
    def test_only_a_reassignment_entry_is_labelled_so(self, from_status, to_status, notes, kind):
        assert (
            reassignment.history_kind(from_status=from_status, to_status=to_status, notes=notes)
            == kind
        )


class TestTheInMemoryStore:
    """It stands in for reassign_event_coordinator, so refuses what that refuses."""

    @pytest.mark.parametrize(
        "change",
        [
            {"coordinator_id": None},
            {"status": EventStatus.CANCELLED},
            {"updated_at": "2099-01-03T08:00:00"},
        ],
        ids=["unassigned", "closed", "changed-since-read"],
    )
    def test_it_refuses_what_the_database_refuses(self, event_repository, change):
        event_repository.events[-1:] = [replace(seed(event_repository), **change)]

        with pytest.raises(StaleEventStatus):
            event_repository.reassign_coordinator(
                EVENT_ID, 41, reassigned_by_id=COORDINATOR_LEAD_ID, expected_updated_at=UPDATED_AT
            )

    def test_an_event_that_is_gone_is_stale(self, event_repository):
        with pytest.raises(StaleEventStatus):
            event_repository.reassign_coordinator(
                404, 41, reassigned_by_id=COORDINATOR_LEAD_ID, expected_updated_at=UPDATED_AT
            )

    def test_first_assignment_no_longer_reassigns(self, event_repository):
        """As assign_event_coordinator: only a Submitted event with no Coordinator."""
        seed(event_repository)

        with pytest.raises(StaleEventStatus):
            event_repository.assign_coordinator(EVENT_ID, 41, COORDINATOR_LEAD_ID)


class TestTheRealStore:
    ROW = {
        "id": EVENT_ID,
        "name": "Open House",
        "status": "Planning",
        "organiser_id": ORGANISER_ID,
        "coordinator_id": NEW_COORDINATOR_ID,
        "created_at": "2099-01-01T09:00:00",
        "updated_at": UPDATED_AT,
    }

    def test_it_reassigns_through_the_database_function(self, fake):
        fake.rows = {EVENTS_TABLE: [self.ROW]}
        fake.rpc_answers = {"reassign_event_coordinator": True}

        moved = SupabaseEvents().reassign_coordinator(
            EVENT_ID,
            NEW_COORDINATOR_ID,
            reassigned_by_id=COORDINATOR_LEAD_ID,
            expected_updated_at=UPDATED_AT,
        )

        assert fake.rpcs == [
            (
                "reassign_event_coordinator",
                {
                    "p_event_id": EVENT_ID,
                    "p_coordinator_id": NEW_COORDINATOR_ID,
                    "p_assigned_by_id": COORDINATOR_LEAD_ID,
                    "p_expected_updated_at": UPDATED_AT,
                },
            )
        ]
        assert moved.coordinator_id == NEW_COORDINATOR_ID

    def test_a_refusal_is_stale(self, fake):
        fake.rpc_answers = {"reassign_event_coordinator": False}

        with pytest.raises(StaleEventStatus):
            SupabaseEvents().reassign_coordinator(
                EVENT_ID,
                NEW_COORDINATOR_ID,
                reassigned_by_id=COORDINATOR_LEAD_ID,
                expected_updated_at=UPDATED_AT,
            )
