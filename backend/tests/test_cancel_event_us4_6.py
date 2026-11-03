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


import pytest

from app.booking_store import Booking, BookingStatus, ConflictFlag, Decision
from app.equipment_store import EquipmentRequest
from app.event_cancellation import (
    CANCEL_REFUSAL_MESSAGES,
    CANCELLATION_REASON_MAX,
    KIND_CANCELLATION,
    READ_ONLY_MESSAGE,
    CancelRefusal,
    cancel_refusal_message,
    check_cancel,
    history_kind,
)
from app.event_status import CANCELLABLE, CLOSED, EventStatus, transition_allowed
from app.event_store import Event, StaleEventStatus
from app.notifications import _listed
from app.permissions import Permission, Role, has_permission, roles_with
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


class TestTheRule:
    def test_cancellable_is_everything_but_completed_cancelled_and_rejected(self):
        assert set(CLOSED) == {EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED}
        assert set(CANCELLABLE) == set(EventStatus) - set(CLOSED)

    @pytest.mark.parametrize("status", CANCELLABLE)
    def test_an_open_event_may_be_cancelled(self, status):
        assert check_cancel(status=status) is None
        assert transition_allowed(from_status=status, to_status=EventStatus.CANCELLED)

    @pytest.mark.parametrize(
        ("status", "refusal"),
        [
            (EventStatus.CANCELLED, CancelRefusal.ALREADY_CANCELLED),
            (EventStatus.COMPLETED, CancelRefusal.COMPLETED),
            (EventStatus.REJECTED, CancelRefusal.REJECTED),
        ],
    )
    def test_a_closed_event_may_not(self, status, refusal):
        assert check_cancel(status=status) is refusal

    def test_nothing_reopens_a_cancelled_event(self):
        for after in EventStatus:
            if after is not EventStatus.CANCELLED:
                assert not transition_allowed(from_status=EventStatus.CANCELLED, to_status=after)

    @pytest.mark.parametrize("closed", [EventStatus.COMPLETED, EventStatus.REJECTED])
    def test_a_completed_or_rejected_event_never_becomes_cancelled(self, closed):
        assert not transition_allowed(from_status=closed, to_status=EventStatus.CANCELLED)

    @pytest.mark.parametrize("reason", list(CancelRefusal))
    def test_every_refusal_explains_itself(self, reason):
        assert cancel_refusal_message(reason) == CANCEL_REFUSAL_MESSAGES[reason]
        assert cancel_refusal_message(reason).endswith(".")

    def test_only_the_move_to_cancelled_is_labelled_a_cancellation(self):
        assert history_kind(to_status=EventStatus.CANCELLED) == KIND_CANCELLATION
        assert history_kind(to_status=EventStatus.PLANNING) == ""


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

    def test_the_organiser_can_cancel_their_own_draft(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, EventStatus.DRAFT, coordinator_id=None)
        response = cancel(client, auth_headers("Event Organiser"))
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"

    def test_another_organisers_event_is_not_found(self, client, auth_headers, event_repository):
        event = seed_event(event_repository, organiser_id=999)
        assert cancel(client, auth_headers("Event Organiser")).status_code == 404
        assert event_repository.get_event(EVENT_ID) == event

    def test_an_unassigned_coordinator_gets_not_found(
        self, client, auth_headers, event_repository
    ):
        event = seed_event(event_repository, coordinator_id=999)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 404
        assert event_repository.get_event(EVENT_ID) == event

    def test_a_coordinator_cannot_reach_a_draft(self, client, auth_headers, event_repository):
        seed_event(event_repository, EventStatus.DRAFT)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 404

    @pytest.mark.parametrize(
        "role",
        ["Event Coordinator Lead", "Venue Staff", "Safety Officer", "Technical Support"],
    )
    def test_no_other_role_may_cancel(self, client, auth_headers, event_repository, role):
        seed_event(event_repository, EventStatus.PENDING_SAFETY_CHECK)
        response = cancel(client, auth_headers(role))
        assert response.status_code == 403
        assert "cancel events" in response.json()["detail"]["message"]
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PENDING_SAFETY_CHECK

    def test_signed_out_is_refused(self, client, event_repository):
        seed_event(event_repository)
        assert client.post(f"/events/{EVENT_ID}/cancel", json={"reason": REASON}).status_code == 401

    @pytest.mark.parametrize("event_id", ["12345", "abc"])
    def test_unknown_event(self, client, auth_headers, event_id):
        assert cancel(client, auth_headers("Event Organiser"), event_id=event_id).status_code == 404


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

    def test_cancelling_twice_is_refused(self, client, auth_headers, event_repository):
        seed_event(event_repository)
        organiser = auth_headers("Event Organiser")
        assert cancel(client, organiser).status_code == 200
        second = cancel(client, organiser)
        assert second.status_code == 409
        assert second.json()["detail"]["message"] == "This event has already been cancelled."

    def test_a_race_lost_in_the_store_is_reported_as_stale(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        seed_event(event_repository)

        def lost(*_args, **_kwargs):
            raise StaleEventStatus

        monkeypatch.setattr(event_repository, "cancel_event", lost)
        response = cancel(client, auth_headers("Event Coordinator"))
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"


class TestReason:
    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_reason_is_required(self, client, auth_headers, event_repository, reason):
        event = seed_event(event_repository)
        response = cancel(client, auth_headers("Event Coordinator"), reason=reason)
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give a reason for cancelling this event."
        assert event_repository.get_event(EVENT_ID) == event

    def test_a_missing_reason_field_is_the_same_sentence(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)
        response = client.post(
            f"/events/{EVENT_ID}/cancel", json={}, headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give a reason for cancelling this event."

    def test_the_reason_has_a_limit(self, client, auth_headers, event_repository):
        seed_event(event_repository)
        coordinator = auth_headers("Event Coordinator")
        too_long = cancel(client, coordinator, reason="x" * (CANCELLATION_REASON_MAX + 1))
        assert too_long.status_code == 400
        at_limit = cancel(client, coordinator, reason="x" * CANCELLATION_REASON_MAX)
        assert at_limit.status_code == 200

    def test_a_closed_event_is_refused_before_the_reason_is_read(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, EventStatus.COMPLETED)
        assert cancel(client, auth_headers("Event Coordinator"), reason="").status_code == 409


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

    def test_an_organisers_cancellation_names_them(self, client, auth_headers, event_repository):
        seed_event(event_repository, EventStatus.SUBMITTED, coordinator_id=None)
        last = cancel(client, auth_headers("Event Organiser")).json()["history"][-1]
        assert (last["byId"], last["byName"], last["kind"]) == (
            str(ORGANISER_ID), "Dylan", KIND_CANCELLATION,
        )

    def test_the_cancellation_reads_back_on_the_event(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)
        cancel(client, auth_headers("Event Coordinator"))
        fetched = client.get(f"/events/{EVENT_ID}", headers=auth_headers("Event Organiser"))
        assert fetched.json()["status"] == "Cancelled"
        assert fetched.json()["history"][-1]["notes"] == REASON


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

    def test_a_confirmed_booking_keeps_the_decision_that_confirmed_it(
        self, client, auth_headers, event_repository, booking_repository
    ):
        seed_event(event_repository)
        decided = Decision(at="2099-01-02T09:00", by_id=VENUE_STAFF_ID, by_name="Sam")
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED, decision=decided))
        cancel(client, auth_headers("Event Organiser"))
        listed = client.get(
            f"/events/{EVENT_ID}/bookings", headers=auth_headers("Event Organiser")
        ).json()
        assert listed[0]["status"] == "Cancelled"
        assert listed[0]["decision"]["byName"] == "Sam"
        assert listed[0]["cancellation"]["reason"] == REASON

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

    def test_a_flag_on_a_released_booking_is_cleared(
        self, client, auth_headers, event_repository, booking_repository
    ):
        seed_event(event_repository)
        flag = ConflictFlag(flagged_at="2099-01-01T09:00", reason="Clashes with booking #9.")
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED, conflict=flag))
        cancel(client, auth_headers("Event Coordinator"))
        assert booking_repository.get_booking(1).conflict is None

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

    def test_released_equipment_leaves_the_tech_support_queue(
        self, client, auth_headers, event_repository, equipment_repository
    ):
        seed_event(event_repository)
        equipment_repository.requests.append(equipment_line(1))
        support = auth_headers("Technical Support")
        assert [r["id"] for r in client.get("/equipment-requests", headers=support).json()] == ["1"]
        cancel(client, auth_headers("Event Coordinator"))
        assert client.get("/equipment-requests", headers=support).json() == []

    def test_an_event_with_nothing_held_still_cancels(
        self, client, auth_headers, event_repository, booking_repository, equipment_repository
    ):
        seed_event(event_repository, EventStatus.UNDER_REVIEW)
        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200
        assert booking_repository.bookings == []
        assert equipment_repository.requests == []


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

    def test_no_venue_can_be_requested(self, client, auth_headers, cancelled):
        response = client.post(
            f"/events/{EVENT_ID}/bookings",
            json={"venueId": "1", "startsAt": STARTS, "endsAt": ENDS},
            headers=auth_headers("Event Coordinator"),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-closed"

    def test_no_equipment_can_be_requested(self, client, auth_headers, cancelled):
        response = client.post(
            f"/events/{EVENT_ID}/equipment-requests",
            json={"equipmentId": 1, "quantity": 1},
            headers=auth_headers("Event Coordinator"),
        )
        assert response.status_code == 409

    def test_no_change_can_be_requested(self, client, auth_headers, cancelled):
        response = client.post(
            f"/events/{EVENT_ID}/change-request",
            json={"title": "Changed", "startsAt": STARTS, "endsAt": ENDS,
                  "expectedAttendance": 30, "purpose": "p", "description": "d"},
            headers=auth_headers("Event Organiser"),
        )
        assert response.status_code == 409

    def test_no_clarification_can_be_asked(self, client, auth_headers, cancelled):
        response = client.post(
            f"/events/{EVENT_ID}/clarification",
            json={"message": "Anything?"},
            headers=auth_headers("Event Coordinator"),
        )
        assert response.status_code == 409

    def test_it_cannot_be_sent_for_a_safety_check(self, client, auth_headers, cancelled):
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409

    def test_a_cancelled_draft_cannot_be_submitted(self, client, auth_headers, event_repository):
        seed_event(event_repository, EventStatus.DRAFT, coordinator_id=None)
        organiser = auth_headers("Event Organiser")
        cancel(client, organiser)
        assert client.post(f"/events/{EVENT_ID}/submit", headers=organiser).status_code == 409

    def test_a_change_request_left_waiting_can_no_longer_be_answered(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, change_requested=True)
        coordinator = auth_headers("Event Coordinator")
        assert cancel(client, coordinator).status_code == 200
        response = client.post(f"/events/{EVENT_ID}/change-request/approve", headers=coordinator)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "nothing-pending"

    def test_it_can_still_be_read_by_both(self, client, auth_headers, cancelled):
        for role in ("Event Organiser", "Event Coordinator"):
            response = client.get(f"/events/{EVENT_ID}", headers=auth_headers(role))
            assert response.status_code == 200
            assert response.json()["status"] == "Cancelled"


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

    def test_the_coordinator_is_told_when_the_organiser_cancels(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_event(event_repository)
        cancel(client, auth_headers("Event Organiser"))
        assert self.messages(notification_repository, COORDINATOR_ID) == [
            f'"Open House" was cancelled by Dylan. Reason: {REASON}'
        ]
        assert self.messages(notification_repository, ORGANISER_ID) == []

    def test_nobody_else_is_told_when_nothing_was_released(
        self, client, auth_headers, event_repository, booking_repository,
        notification_repository,
    ):
        seed_event(event_repository, EventStatus.SUBMITTED, coordinator_id=None)
        booking_repository.bookings.append(booking(1, BookingStatus.REJECTED))
        cancel(client, auth_headers("Event Organiser"))
        assert notification_repository.notifications == []

    def test_one_booking_and_one_line_read_in_the_singular(
        self, client, auth_headers, event_repository, booking_repository,
        equipment_repository, notification_repository,
    ):
        seed_event(event_repository)
        booking_repository.bookings.append(booking(1))
        equipment_repository.requests.append(equipment_line(1))
        cancel(client, auth_headers("Event Coordinator"))
        assert "its booking was released: Great Hall." in self.messages(
            notification_repository, VENUE_STAFF_ID
        )[0]
        assert "its equipment request was released: 1 × Projector." in self.messages(
            notification_repository, TECH_SUPPORT_ID
        )[0]

    def test_venue_staff_read_the_notice(
        self, client, auth_headers, event_repository, booking_repository
    ):
        seed_event(event_repository)
        booking_repository.bookings.append(booking(1))
        cancel(client, auth_headers("Event Coordinator"))
        listed = client.get("/notifications", headers=auth_headers("Venue Staff"))
        assert listed.status_code == 200
        assert [item["status"] for item in listed.json()] == ["Cancelled"]

    def test_a_notice_that_cannot_be_written_does_not_undo_the_cancellation(
        self, client, auth_headers, event_repository, booking_repository,
        notification_repository, monkeypatch,
    ):
        seed_event(event_repository)
        booking_repository.bookings.append(booking(1))

        def broken(**_kwargs):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(notification_repository, "create", broken)
        response = cancel(client, auth_headers("Event Coordinator"))
        assert response.status_code == 200
        assert event_repository.get_event(EVENT_ID).status is EventStatus.CANCELLED
        assert booking_repository.get_booking(1).status is BookingStatus.CANCELLED

    def test_a_failed_read_of_what_was_released_does_not_undo_it(
        self, client, auth_headers, event_repository, booking_repository,
        notification_repository, monkeypatch,
    ):
        seed_event(event_repository)
        booking_repository.bookings.append(booking(1))
        cancel_in_store = event_repository.cancel_event

        def then_break(*args, **kwargs):
            cancelled = cancel_in_store(*args, **kwargs)
            monkeypatch.setattr(booking_repository, "list_for_event", broken)
            return cancelled

        def broken(_event_id):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(event_repository, "cancel_event", then_break)
        response = cancel(client, auth_headers("Event Coordinator"))
        assert response.status_code == 200
        # The people on the event are still told; only the release details are lost.
        assert len(notification_repository.list_for_user(ORGANISER_ID)) == 1
        assert notification_repository.list_for_user(VENUE_STAFF_ID) == []

    @pytest.mark.parametrize(
        ("items", "joined"),
        [([], ""), (["A"], "A"), (["A", "B"], "A and B"), (["A", "B", "C"], "A, B and C")],
    )
    def test_lists_read_as_a_sentence(self, items, joined):
        assert _listed(items) == joined


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

    def test_registration_closes_and_keeps_its_capacity(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Organiser"))

        assert registration_repository.settings[EVENT_ID] == (False, 30)
        assert registration_repository.settings_for(EVENT_ID).registered == 0

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

    def test_each_attendee_is_told_once(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository, EventStatus.CONFIRMED)
        registration_repository.registrations.extend(
            [registration(1, ATTENDEE_ID), registration(4, SECOND_ATTENDEE_ID)]
        )
        cancel(client, auth_headers("Event Organiser"))

        for attendee in (ATTENDEE_ID, SECOND_ATTENDEE_ID):
            assert len(notification_repository.list_for_user(attendee)) == 1

    def test_an_attendee_reads_it_on_their_notifications_page(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Coordinator"))

        listed = client.get("/notifications", headers=auth_headers("Attendee"))

        assert listed.status_code == 200, listed.text
        shown = [(item["status"], item["eventTitle"], item["message"]) for item in listed.json()]
        assert shown == [("Cancelled", "Open House", self.ATTENDEE_NOTICE)]

    def test_the_attendee_sees_event_cancelled_on_my_registrations(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Coordinator"))

        (item,) = client.get("/attendee/registrations", headers=auth_headers("Attendee")).json()

        assert (item["status"], item["canWithdraw"], item["canRegisterAgain"]) == (
            "Event Cancelled",
            False,
            False,
        )

    def test_a_cancelled_registration_cannot_be_withdrawn(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Coordinator"))

        response = client.post(
            "/attendee/registrations/1/withdraw", headers=auth_headers("Attendee")
        )

        assert response.status_code == 409
        # Closed, not "already withdrawn": the Attendee did not withdraw it.
        assert response.json()["detail"]["reason"] == "event-closed"

    def test_the_organiser_still_sees_who_was_registered(
        self, client, auth_headers, event_repository, registration_repository
    ):
        self.registered_event(event_repository, registration_repository)
        cancel(client, auth_headers("Event Coordinator"))

        body = client.get(
            f"/events/{EVENT_ID}/registrations", headers=auth_headers("Event Organiser")
        ).json()

        assert [(person["name"], person["status"]) for person in body["registrations"]] == [
            ("Casey Tan", "Event Cancelled"),
            ("Morgan Lee", "Withdrawn"),
        ]
        assert (body["open"], body["registered"]) == (False, 0)

    def test_an_event_nobody_registered_for_tells_no_attendee(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_event(event_repository, EventStatus.CONFIRMED)
        cancel(client, auth_headers("Event Coordinator"))

        assert notification_repository.list_for_user(ATTENDEE_ID) == []

    def test_a_failed_read_of_the_registrations_does_not_undo_it(
        self, client, auth_headers, event_repository, booking_repository,
        registration_repository, notification_repository, monkeypatch,
    ):
        self.registered_event(event_repository, registration_repository)
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED))

        def broken(_event_id):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(registration_repository, "list_for_event", broken)

        assert cancel(client, auth_headers("Event Coordinator")).status_code == 200
        assert self.statuses(registration_repository)[1] is RegistrationStatus.EVENT_CANCELLED
        # Only the Attendees' notices are lost; everyone else is still told.
        assert notification_repository.list_for_user(ATTENDEE_ID) == []
        assert len(notification_repository.list_for_user(ORGANISER_ID)) == 1
        assert len(notification_repository.list_for_user(VENUE_STAFF_ID)) == 1


class TestPermissions:
    def test_organisers_and_coordinators_cancel(self):
        assert roles_with(Permission.EVENTS_CANCEL) == [Role.ORGANISER, Role.COORDINATOR]

    def test_venue_staff_now_read_notifications(self):
        assert has_permission(Role.VENUE_STAFF, Permission.NOTIFICATIONS_READ)

