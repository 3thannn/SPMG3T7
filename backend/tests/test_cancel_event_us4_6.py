"""US4.6: cancel an event, and have its bookings and equipment released.

Acceptance criteria, and the tests that hold each one:

* The owning Organiser or the assigned Coordinator can cancel any event that
  isn't Completed, Cancelled or Rejected; a reason is required ->
  `TestTheRule`, `TestWhoMayCancel`, `TestWhichEvents`, `TestReason`.
* Status -> Cancelled, logged with who and when; the event becomes read-only ->
  `TestHistory`, `TestReadOnly`.
* Every active venue booking and hold -> Cancelled, and every equipment line
  released, so the slots and quantities free up -> `TestReleases`.
* Registrations are marked Event Cancelled -> `TestRegistrations` (built once
  US20.1 brought registrations).
* The Coordinator, Organiser, affected Venue Staff, Tech Support and registered
  Attendees are notified -> `TestNotifications`, `TestRegistrations`.
"""

from types import SimpleNamespace

import pytest

from app import supabase_client
from app.booking_store import Booking, BookingStatus
from app.equipment_store import EquipmentRequest
from app.event_cancellation import (
    KIND_CANCELLATION,
    READ_ONLY_MESSAGE,
)
from app.event_status import CANCELLABLE, EventStatus
from app.event_store import CancelledEvent, Event, StaleEventStatus, SupabaseEvents
from app.registration_store import Registration, RegistrationStatus
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SECOND_ATTENDEE_ID,
    SUBMITTABLE_NEED_ATTRS,
    TECH_SUPPORT_ID,
    VENUE_STAFF_ID,
)

EVENT_ID = 800
OTHER_EVENT_ID = 801
REASON = "Funding was withdrawn."
#: Booking times far enough out that no test day reaches them.
STARTS = "2099-11-02T09:00"
ENDS = "2099-11-02T17:00"
LIVE_HOLD = "2999-01-01T00:00"
EXPIRED_HOLD = "2000-01-01T00:00"


def seed_event(
    event_repository,
    status=EventStatus.PLANNING,
    *,
    event_id=EVENT_ID,
    organiser_id=ORGANISER_ID,
    coordinator_id=COORDINATOR_ID,
    change_requested=False,
):
    event = Event(
        id=event_id,
        title="Open House",
        purpose="Welcome visitors",
        description="Tours and talks.",
        starts_at=STARTS,
        ends_at=ENDS,
        expected_attendance=30,
        status=status,
        organiser_id=organiser_id,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00",
        updated_at="2099-01-01T09:00",
        coordinator_id=coordinator_id,
        change_requested=change_requested,
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    return event


def booking(
    booking_id,
    status=BookingStatus.REQUESTED,
    *,
    event_id=EVENT_ID,
    venue_id=1,
    venue_name="Great Hall",
    hold_expires_at="",
    decision=None,
    conflict=None,
):
    return Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=venue_id,
        venue_name=venue_name,
        starts_at=STARTS,
        ends_at=ENDS,
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
        hold_expires_at=hold_expires_at,
        decision=decision,
        conflict=conflict,
    )


def equipment_line(line_id, status="Requested", *, event_id=EVENT_ID, kind="Projector", qty=1):
    return EquipmentRequest(
        id=line_id,
        event_id=event_id,
        equipment_type=kind,
        quantity=qty,
        technical_requirements="",
        support_notes="",
        starts_at=STARTS,
        ends_at=ENDS,
        status=status,
        requested_by_id=COORDINATOR_ID,
        created_at="2099-01-01T09:00",
        version=1,
        event_title="Open House",
    )


def cancel(client, headers, *, reason=REASON, event_id=EVENT_ID):
    return client.post(f"/events/{event_id}/cancel", json={"reason": reason}, headers=headers)




class TestWhoMayCancel:
    def test_the_owning_organiser_cancels(self, client, auth_headers, event_repository):
        seed_event(event_repository)
        response = cancel(client, auth_headers("Event Organiser"))
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"
        assert event_repository.get_event(EVENT_ID).status is EventStatus.CANCELLED

    def test_the_assigned_coordinator_cancels(self, client, auth_headers, event_repository):
        seed_event(event_repository)
        response = cancel(client, auth_headers("Event Coordinator"))
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"



    def test_an_unassigned_coordinator_gets_not_found(
        self, client, auth_headers, event_repository
    ):
        event = seed_event(event_repository, coordinator_id=999)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 404
        assert event_repository.get_event(EVENT_ID) == event






class TestWhichEvents:
    @pytest.mark.parametrize("status", [s for s in CANCELLABLE if s is not EventStatus.DRAFT])
    def test_every_open_status_can_be_cancelled(
        self, client, auth_headers, event_repository, status
    ):
        seed_event(event_repository, status)
        response = cancel(client, auth_headers("Event Coordinator"))
        assert response.status_code == 200, response.text
        assert response.json()["history"][-1]["from"] == str(status)

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (EventStatus.CANCELLED, "already-cancelled"),
            (EventStatus.COMPLETED, "event-completed"),
            (EventStatus.REJECTED, "event-rejected"),
        ],
    )
    def test_a_closed_event_is_refused_and_left_alone(
        self, client, auth_headers, event_repository, status, reason
    ):
        event = seed_event(event_repository, status)
        response = cancel(client, auth_headers("Event Organiser"))
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == reason
        assert event_repository.get_event(EVENT_ID) == event




class TestReason:
    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_reason_is_required(self, client, auth_headers, event_repository, reason):
        event = seed_event(event_repository)
        response = cancel(client, auth_headers("Event Coordinator"), reason=reason)
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give a reason for cancelling this event."
        assert event_repository.get_event(EVENT_ID) == event





class TestHistory:
    def test_the_move_is_logged_with_who_when_and_why(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, EventStatus.CONFIRMED)
        response = cancel(client, auth_headers("Event Coordinator"), reason=f"  {REASON}  ")
        last = response.json()["history"][-1]
        assert (last["from"], last["to"], last["byId"], last["byName"]) == (
            "Confirmed", "Cancelled", str(COORDINATOR_ID), "Priya",
        )
        assert last["notes"] == REASON
        assert last["kind"] == KIND_CANCELLATION
        assert last["at"]




class TestReleases:
    def test_every_active_booking_and_hold_is_cancelled_and_nothing_else(
        self, client, auth_headers, event_repository, booking_repository
    ):
        seed_event(event_repository)
        earlier = booking(6, BookingStatus.CANCELLED)
        booking_repository.bookings.extend(
            [
                booking(1, BookingStatus.REQUESTED),
                booking(2, BookingStatus.CONFIRMED, venue_id=3, venue_name="Seminar Room 4"),
                booking(3, BookingStatus.HELD, hold_expires_at=LIVE_HOLD),
                booking(4, BookingStatus.HELD, hold_expires_at=EXPIRED_HOLD),
                booking(5, BookingStatus.REJECTED),
                earlier,
                booking(7, BookingStatus.CONFIRMED, event_id=OTHER_EVENT_ID),
            ]
        )
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200

        status_of = {b.id: b.status for b in booking_repository.bookings}
        assert status_of == {
            1: BookingStatus.CANCELLED,
            2: BookingStatus.CANCELLED,
            3: BookingStatus.CANCELLED,
            4: BookingStatus.HELD,  # expired: it already let the slot go
            5: BookingStatus.REJECTED,
            6: BookingStatus.CANCELLED,
            7: BookingStatus.CONFIRMED,  # another event's
        }
        for released in (1, 2, 3):
            cancellation = booking_repository.get_booking(released).cancellation
            assert (cancellation.by_id, cancellation.by_name, cancellation.reason) == (
                COORDINATOR_ID, "Priya", REASON,
            )
        assert booking_repository.get_booking(6) == earlier


    def test_the_freed_slot_can_be_requested_by_another_event(
        self, client, auth_headers, event_repository, booking_repository
    ):
        seed_event(event_repository)
        seed_event(event_repository, EventStatus.APPROVED, event_id=OTHER_EVENT_ID)
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED))
        coordinator = auth_headers("Event Coordinator")
        same_slot = {"venueId": "1", "startsAt": STARTS, "endsAt": ENDS}

        before = client.post(f"/events/{OTHER_EVENT_ID}/bookings", json=same_slot,
                             headers=coordinator)
        assert before.status_code == 409
        assert before.json()["detail"]["reason"] == "not-available"

        assert cancel(client, coordinator).status_code == 200
        after = client.post(f"/events/{OTHER_EVENT_ID}/bookings", json=same_slot,
                            headers=coordinator)
        assert after.status_code == 201, after.text


    def test_every_equipment_line_is_released(
        self, client, auth_headers, event_repository, equipment_repository
    ):
        seed_event(event_repository)
        already = equipment_line(2, "Removed")
        equipment_repository.requests.extend(
            [equipment_line(1), already, equipment_line(3, event_id=OTHER_EVENT_ID)]
        )
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200

        released = equipment_repository.get_request(1)
        assert (released.status, released.version, released.updated_by_id) == (
            "Removed", 2, COORDINATOR_ID,
        )
        assert equipment_repository.get_request(2) == already
        assert equipment_repository.get_request(3).status == "Requested"
        # The line's history says it was removed, and by whom.
        assert [(h.request_id, h.action, h.actor_id) for h in equipment_repository.history] == [
            (1, "Removed", COORDINATOR_ID)
        ]




class TestReadOnly:
    @pytest.fixture
    def cancelled(self, client, auth_headers, event_repository):
        seed_event(event_repository)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200
        return event_repository.get_event(EVENT_ID)

    @pytest.mark.parametrize("role", ["Event Coordinator", "Event Organiser"])
    def test_its_details_cannot_be_saved(self, client, auth_headers, cancelled, role):
        response = client.put(
            f"/events/{EVENT_ID}",
            json={"title": "Changed", "startsAt": STARTS, "expectedAttendance": 30},
            headers=auth_headers(role),
        )
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "rule_refused", "message": READ_ONLY_MESSAGE, "reason": "event-cancelled",
        }










class TestNotifications:
    def busy_event(self, event_repository, booking_repository, equipment_repository):
        seed_event(event_repository)
        booking_repository.bookings.extend(
            [
                booking(1, BookingStatus.CONFIRMED),
                booking(2, BookingStatus.REQUESTED, venue_id=3, venue_name="Seminar Room 4"),
            ]
        )
        equipment_repository.requests.extend(
            [equipment_line(1, qty=2), equipment_line(2, kind="Microphone")]
        )

    def messages(self, notification_repository, user_id):
        return [n.message for n in notification_repository.list_for_user(user_id)]

    def test_everyone_affected_is_told_but_not_the_canceller(
        self, client, auth_headers, event_repository, booking_repository,
        equipment_repository, notification_repository,
    ):
        self.busy_event(event_repository, booking_repository, equipment_repository)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200

        assert self.messages(notification_repository, ORGANISER_ID) == [
            f'"Open House" was cancelled by Priya. Reason: {REASON}'
        ]
        assert self.messages(notification_repository, COORDINATOR_ID) == []
        assert self.messages(notification_repository, VENUE_STAFF_ID) == [
            '"Open House" was cancelled, so its bookings were released: '
            f"Great Hall and Seminar Room 4. Reason: {REASON}"
        ]
        assert self.messages(notification_repository, TECH_SUPPORT_ID) == [
            '"Open House" was cancelled, so its equipment requests were released: '
            f"2 × Projector and 1 × Microphone. Reason: {REASON}"
        ]
        assert {n.status for n in notification_repository.notifications} == {
            EventStatus.CANCELLED
        }
        assert {n.event_id for n in notification_repository.notifications} == {EVENT_ID}









def registration(registration_id, attendee_id, status=RegistrationStatus.REGISTERED, **changes):
    return Registration(
        id=registration_id,
        event_id=changes.pop("event_id", EVENT_ID),
        attendee_id=attendee_id,
        name="Casey Tan" if attendee_id == ATTENDEE_ID else "Morgan Lee",
        email="casey@example.com" if attendee_id == ATTENDEE_ID else "morgan@example.com",
        status=status,
        created_at="2099-01-02T09:00:00",
        **changes,
    )


class TestRegistrations:
    """AC4, and the Attendee half of AC5 (US20.1 brought registrations)."""

    ATTENDEE_NOTICE = (
        '"Open House" has been cancelled, so your registration for it is cancelled too.'
    )

    def registered_event(self, event_repository, registration_repository):
        seed_event(event_repository, EventStatus.CONFIRMED)
        registration_repository.settings[EVENT_ID] = (True, 30)
        registration_repository.registrations.extend(
            [
                registration(1, ATTENDEE_ID),
                registration(
                    2,
                    SECOND_ATTENDEE_ID,
                    RegistrationStatus.WITHDRAWN,
                    withdrawn_at="2099-01-03T09:00:00",
                ),
                registration(3, SECOND_ATTENDEE_ID, event_id=OTHER_EVENT_ID),
            ]
        )

    def statuses(self, registration_repository):
        return {item.id: item.status for item in registration_repository.registrations}

    def test_every_registered_registration_is_marked_event_cancelled_and_nothing_else(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)

        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200

        assert self.statuses(registration_repository) == {
            1: RegistrationStatus.EVENT_CANCELLED,
            # A withdrawal is history, and another event's registration is not this one's.
            2: RegistrationStatus.WITHDRAWN,
            3: RegistrationStatus.REGISTERED,
        }


    def test_registered_attendees_are_told_without_the_reason(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Coordinator"))

        told = notification_repository.list_for_user(ATTENDEE_ID)
        assert [notice.message for notice in told] == [self.ATTENDEE_NOTICE]
        assert REASON not in told[0].message
        assert (told[0].status, told[0].event_id) == (EventStatus.CANCELLED, EVENT_ID)
        # Morgan withdrew, so their place was not taken away and they are not told.
        assert notification_repository.list_for_user(SECOND_ATTENDEE_ID) == []













class RpcAdmin:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def rpc(self, name, arguments):
        self.calls.append((name, arguments))
        return self

    def execute(self):
        return SimpleNamespace(data=self.result)


class TestSupabaseStore:
    def test_cancel_uses_the_atomic_rpc(self, monkeypatch):
        admin = RpcAdmin({"bookings": [3, 4], "equipment": [9]})
        marker = object()
        store = SupabaseEvents()
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _id: marker)

        result = store.cancel_event(
            42, actor_id=COORDINATOR_ID, from_status=EventStatus.CONFIRMED, reason=REASON
        )

        assert result == CancelledEvent(event=marker, booking_ids=(3, 4), equipment_ids=(9,))
        assert admin.calls == [
            ("cancel_event", {
                "p_event_id": 42, "p_expected_status": "Confirmed",
                "p_actor_id": COORDINATOR_ID, "p_reason": REASON,
            })
        ]




    def test_null_from_the_rpc_is_stale(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "admin", lambda: RpcAdmin(None))
        with pytest.raises(StaleEventStatus):
            SupabaseEvents().cancel_event(
                42, actor_id=ORGANISER_ID, from_status=EventStatus.PLANNING, reason=REASON
            )



