"""Venue Staff approve or reject a booking request — US16.1.

Test case ids (TC-D…) match the US16.1 test cases document; the classes follow
the acceptance criteria in order. Bookings are seeded straight into the store
so each test controls status, times and request order. "Now" is pinned to NOW.

Fixture venues: 1 Great Hall (given 30 minutes' setup and 45 minutes'
turnaround below), 2 Bertha Room (no buffers). The fixture Venue Staff member
is Sam and the Coordinator is Priya.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app import availability, booking_store
from app.booking_store import Booking, BookingStatus, SlotTaken
from app.event_status import EventStatus
from tests.conftest import COORDINATOR_ID, VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, seed_event

NOW = datetime(2027, 10, 1, 9, 0)
OTHER_EVENT = 901


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    current = {"now": NOW}
    monkeypatch.setattr(booking_store, "local_now", lambda: current["now"])

    def move_to(moment: datetime) -> None:
        current["now"] = moment

    return move_to


@pytest.fixture(autouse=True)
def buffered_hall(venue_repository):
    """Great Hall needs 30 minutes before and 45 after each booking (US9.4)."""
    venue_repository.venues = [
        replace(v, setup_minutes=30, turnaround_minutes=45) if v.id == 1 else v
        for v in venue_repository.venues
    ]


@pytest.fixture
def events(event_repository):
    seed_event(event_repository)
    seed_event(event_repository, event_id=OTHER_EVENT)
    return event_repository


@pytest.fixture
def staff(auth_headers):
    return auth_headers("Venue Staff")


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


def seed(
    booking_repository,
    booking_id: int,
    *,
    venue_id: int = 1,
    event_id: int = EVENT_ID,
    starts_at: str = "2027-11-02T09:00",
    ends_at: str = "2027-11-02T17:00",
    status: BookingStatus = BookingStatus.REQUESTED,
    requested_at: str = "2027-09-01T09:00:00",
    hold_expires_at: str = "",
    headcount: int | None = 120,
    layout: str = "Theatre",
) -> Booking:
    booking = Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=venue_id,
        venue_name={1: "Great Hall", 2: "Bertha Room"}.get(venue_id, ""),
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at=requested_at,
        headcount=headcount,
        required_layout=layout,
        hold_expires_at=hold_expires_at,
    )
    booking_repository.bookings.append(booking)
    return booking


def approve(client, headers, booking_id):
    return client.post(f"/booking-requests/{booking_id}/approve", headers=headers)


def reject(client, headers, booking_id, **body):
    return client.post(f"/booking-requests/{booking_id}/reject", json=body, headers=headers)


def refused(response) -> dict:
    assert response.status_code == 409, response.text
    return response.json()["detail"]


def bad_request(response) -> str:
    assert response.status_code == 400, response.text
    return response.json()["detail"]["message"]


def status_of(booking_repository, booking_id) -> BookingStatus:
    return booking_repository.get_booking(booking_id).status


class TestTheQueue:
    """AC1: every Requested booking, oldest first, with what a decision needs."""

    def test_tc_d01_oldest_request_first(self, client, staff, events, booking_repository):
        seed(booking_repository, 11, requested_at="2027-09-03T09:00:00")
        seed(booking_repository, 12, requested_at="2027-09-01T09:00:00", venue_id=2)
        seed(booking_repository, 13, requested_at="2027-09-02T09:00:00", venue_id=2,
             starts_at="2027-11-05T09:00", ends_at="2027-11-05T10:00")

        listed = client.get("/booking-requests", headers=staff)

        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()] == ["12", "13", "11"]

    def test_tc_d02_only_requested_bookings_are_listed(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, status=BookingStatus.HELD, hold_expires_at="2027-10-08T17:00")
        seed(booking_repository, 13, status=BookingStatus.CANCELLED)
        seed(booking_repository, 14, status=BookingStatus.CONFIRMED)
        seed(booking_repository, 15, status=BookingStatus.REJECTED)

        assert [item["id"] for item in client.get("/booking-requests", headers=staff).json()] == [
            "11"
        ]

    def test_tc_d03_each_request_shows_what_a_decision_needs(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)

        [item] = client.get("/booking-requests", headers=staff).json()

        assert item["eventTitle"] == "Faculty Welcome Night"
        assert item["venueName"] == "Great Hall"
        assert (item["startsAt"], item["endsAt"]) == ("2027-11-02T09:00", "2027-11-02T17:00")
        # The full occupied window: 30 minutes' setup before, 45 minutes' turnaround after.
        assert (item["occupiedFrom"], item["occupiedTo"]) == (
            "2027-11-02T08:30",
            "2027-11-02T17:45",
        )
        assert (item["setupMinutes"], item["turnaroundMinutes"]) == (30, 45)
        assert item["headcount"] == 120
        assert item["requiredLayout"] == "Theatre"
        assert item["coordinatorName"] == "Priya"
        assert item["clashes"] == []

    def test_tc_d04_a_request_shows_what_it_already_clashes_with(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED,
             starts_at="2027-11-02T17:30", ends_at="2027-11-02T19:00")
        seed(booking_repository, 11)

        [item] = client.get("/booking-requests", headers=staff).json()

        [clash] = item["clashes"]
        assert clash["bookingId"] == "10"
        assert clash["status"] == "Confirmed"
        assert (clash["occupiedFrom"], clash["occupiedTo"]) == (
            "2027-11-02T17:00",
            "2027-11-02T19:45",
        )

    def test_tc_d05_an_empty_queue_is_an_empty_list(self, client, staff):
        assert client.get("/booking-requests", headers=staff).json() == []

    def test_tc_d05b_an_event_with_no_coordinator_shows_none(
        self, client, staff, event_repository, booking_repository
    ):
        seed_event(event_repository, coordinator_id=None)
        seed(booking_repository, 11)
        [item] = client.get("/booking-requests", headers=staff).json()
        assert item["coordinatorName"] == ""


class TestApproving:
    """AC2: Approve -> Confirmed, with the conflict check run again at approval."""

    def test_tc_d06_approving_confirms_the_booking(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)

        response = approve(client, staff, 11)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Confirmed"
        assert body["decision"]["byName"] == "Sam"
        assert body["decision"]["byId"] == str(VENUE_STAFF_ID)
        assert body["decision"]["at"]
        assert body["decision"]["reason"] == ""
        assert status_of(booking_repository, 11) is BookingStatus.CONFIRMED

    def test_tc_d07_two_requests_for_one_slot_cannot_both_be_approved(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, event_id=OTHER_EVENT,
             starts_at="2027-11-02T12:00", ends_at="2027-11-02T14:00")

        assert approve(client, staff, 11).status_code == 200
        detail = refused(approve(client, staff, 12))

        assert detail["reason"] == "slot-taken"
        assert "Great Hall is already taken for this slot" in detail["message"]
        assert '"Faculty Welcome Night" (Confirmed' in detail["message"]
        assert [clash["bookingId"] for clash in detail["clashes"]] == ["11"]
        assert status_of(booking_repository, 12) is BookingStatus.REQUESTED

    def test_tc_d08_a_pending_request_does_not_block_another(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, event_id=OTHER_EVENT)
        assert approve(client, staff, 12).status_code == 200

    def test_tc_d09_setup_and_turnaround_count_toward_the_clash(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED,
             starts_at="2027-11-02T06:00", ends_at="2027-11-02T08:00")
        seed(booking_repository, 11)
        # 08:00 + 45 minutes' turnaround overlaps 09:00 - 30 minutes' setup.
        assert refused(approve(client, staff, 11))["reason"] == "slot-taken"

    def test_tc_d10_back_to_back_after_the_buffers_is_no_clash(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED,
             starts_at="2027-11-02T06:00", ends_at="2027-11-02T07:45")
        seed(booking_repository, 11)
        # Its turnaround ends at 08:30, exactly when this one's setup starts.
        assert approve(client, staff, 11).status_code == 200

    def test_tc_d11_the_same_slot_at_another_venue_is_no_clash(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED)
        seed(booking_repository, 11, venue_id=2)
        assert approve(client, staff, 11).status_code == 200

    def test_tc_d12_an_unexpired_hold_takes_the_slot(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.HELD,
             hold_expires_at="2027-10-08T17:00")
        seed(booking_repository, 11)
        assert refused(approve(client, staff, 11))["clashes"][0]["status"] == "Held"

    def test_tc_d13_an_expired_hold_does_not(
        self, client, staff, events, booking_repository, frozen_now
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.HELD,
             hold_expires_at="2027-10-08T17:00")
        seed(booking_repository, 11)
        frozen_now(datetime(2027, 10, 8, 17, 0))
        assert approve(client, staff, 11).status_code == 200

    def test_tc_d14_a_rejected_or_cancelled_booking_does_not(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 9, event_id=OTHER_EVENT, status=BookingStatus.REJECTED)
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CANCELLED)
        seed(booking_repository, 11)
        assert approve(client, staff, 11).status_code == 200

    def test_tc_d15b_the_store_rechecks_the_clash_itself(self, events, booking_repository):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED)
        seed(booking_repository, 11)
        with pytest.raises(SlotTaken):
            booking_repository.approve(11, actor_id=VENUE_STAFF_ID)

    def test_tc_d15_a_clash_taken_between_the_check_and_the_write_is_shown(
        self, client, staff, events, booking_repository, monkeypatch
    ):
        seed(booking_repository, 11)

        def lost_the_race(*_args, **_kwargs):
            raise SlotTaken

        monkeypatch.setattr(booking_repository, "approve", lost_the_race)
        assert refused(approve(client, staff, 11))["reason"] == "slot-taken"

    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (BookingStatus.CONFIRMED, "This booking has already been confirmed."),
            (BookingStatus.REJECTED, "This booking has already been rejected."),
            (BookingStatus.CANCELLED, "The Coordinator cancelled this booking."),
            (
                BookingStatus.HELD,
                "This is a tentative hold. The Coordinator has not requested it yet.",
            ),
        ],
    )
    def test_tc_d16_only_a_requested_booking_can_be_approved(
        self, client, staff, events, booking_repository, status, message
    ):
        seed(booking_repository, 11, status=status, hold_expires_at="2027-10-08T17:00")
        detail = refused(approve(client, staff, 11))
        assert (detail["reason"], detail["message"]) == ("not-requested", message)

    def test_tc_d17_approving_twice_at_once_is_decided_once(
        self, client, staff, events, booking_repository, monkeypatch
    ):
        seed(booking_repository, 11)
        real_approve = booking_repository.approve

        def someone_else_first(booking_id, **kwargs):
            real_approve(booking_id, **kwargs)
            return real_approve(booking_id, **kwargs)

        monkeypatch.setattr(booking_repository, "approve", someone_else_first)
        assert refused(approve(client, staff, 11))["message"] == (
            "This booking has already been confirmed."
        )

    @pytest.mark.parametrize("booking_id", ["999", "abc"])
    def test_tc_d18_an_unknown_booking_is_not_found(self, client, staff, booking_id):
        assert approve(client, staff, booking_id).status_code == 404
        assert reject(client, staff, booking_id, reason="No").status_code == 404


class TestRejecting:
    """AC3: Reject -> reason required, optional suggestion, Rejected, slot freed."""

    def test_tc_d19_rejecting_with_a_reason_and_a_suggestion(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)

        response = reject(
            client, staff, 11,
            reason="The hall is closed for repairs that week.",
            suggestion="Bertha Room, or the Great Hall on 9 Nov",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Rejected"
        assert body["decision"]["reason"] == "The hall is closed for repairs that week."
        assert body["decision"]["suggestion"] == "Bertha Room, or the Great Hall on 9 Nov"
        assert body["decision"]["byName"] == "Sam"

    def test_tc_d20_the_suggestion_is_optional(self, client, staff, events, booking_repository):
        seed(booking_repository, 11)
        body = reject(client, staff, 11, reason="Too many people for this room.").json()
        assert body["decision"]["suggestion"] == ""

    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_tc_d21_a_reason_is_required(
        self, client, staff, events, booking_repository, reason
    ):
        seed(booking_repository, 11)
        body = {} if reason is None else {"reason": reason}
        assert bad_request(reject(client, staff, 11, **body)) == (
            "Give the Coordinator a reason for rejecting this booking."
        )
        assert status_of(booking_repository, 11) is BookingStatus.REQUESTED

    def test_tc_d22_the_reason_and_suggestion_have_a_limit(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        assert "2000 characters" in bad_request(reject(client, staff, 11, reason="x" * 2001))
        assert "2000 characters" in bad_request(
            reject(client, staff, 11, reason="No", suggestion="x" * 2001)
        )
        assert reject(client, staff, 11, reason="x" * 2000).status_code == 200

    def test_tc_d23_a_rejected_booking_frees_its_slot(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, event_id=OTHER_EVENT)
        approve(client, staff, 11)
        assert refused(approve(client, staff, 12))["reason"] == "slot-taken"

        seed(booking_repository, 13, event_id=OTHER_EVENT)
        reject(client, staff, 12, reason="Clashes with another event.")

        assert booking_repository.get_booking(12).holds_venue is False

    def test_tc_d24_after_a_rejection_the_slot_can_be_confirmed(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, event_id=OTHER_EVENT)
        reject(client, staff, 11, reason="Changed plans.")
        assert approve(client, staff, 12).status_code == 200

    def test_tc_d25_only_a_requested_booking_can_be_rejected(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11, status=BookingStatus.CONFIRMED)
        assert refused(reject(client, staff, 11, reason="No"))["reason"] == "not-requested"

    def test_tc_d26_rejecting_twice_at_once_is_decided_once(
        self, client, staff, events, booking_repository, monkeypatch
    ):
        seed(booking_repository, 11)
        real_reject = booking_repository.reject

        def someone_else_first(booking_id, **kwargs):
            real_reject(booking_id, **kwargs)
            return real_reject(booking_id, **kwargs)

        monkeypatch.setattr(booking_repository, "reject", someone_else_first)
        assert refused(reject(client, staff, 11, reason="No"))["message"] == (
            "This booking has already been rejected."
        )


class TestOnlyThisBooking:
    """AC4: approving or rejecting one booking doesn't change the event's other bookings."""

    @pytest.mark.parametrize("decide", ["approve", "reject"])
    def test_tc_d27_other_bookings_and_the_event_are_unchanged(
        self, client, staff, events, booking_repository, decide
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, venue_id=2)
        seed(booking_repository, 13, venue_id=2, status=BookingStatus.HELD,
             starts_at="2027-11-03T09:00", ends_at="2027-11-03T10:00",
             hold_expires_at="2027-10-08T17:00")
        before = [b for b in booking_repository.bookings if b.id != 11]
        event_before = events.get_event(EVENT_ID)

        if decide == "approve":
            approve(client, staff, 11)
        else:
            reject(client, staff, 11, reason="No")

        assert [b for b in booking_repository.bookings if b.id != 11] == before
        assert events.get_event(EVENT_ID) == event_before
        assert events.get_event(EVENT_ID).status is EventStatus.APPROVED


class TestTheCoordinatorIsTold:
    """AC5: the assigned Coordinator is notified of the decision and reason (US10.2)."""

    def notices(self, notification_repository):
        return [(n.user_id, n.kind, n.message) for n in notification_repository.notifications]

    def test_tc_d28_an_approval_notifies_the_coordinator(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 11)
        approve(client, staff, 11)
        assert self.notices(notification_repository) == [
            (
                COORDINATOR_ID,
                "booking-confirmed",
                'Venue Staff confirmed Great Hall for "Faculty Welcome Night".',
            )
        ]

    def test_tc_d29_a_rejection_notifies_with_the_reason_and_suggestion(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 11)
        reject(client, staff, 11, reason="Closed that week.", suggestion="Bertha Room")
        assert self.notices(notification_repository) == [
            (
                COORDINATOR_ID,
                "booking-rejected",
                'Venue Staff rejected Great Hall for "Faculty Welcome Night". '
                "Reason: Closed that week. Suggested instead: Bertha Room",
            )
        ]

    def test_tc_d30_a_rejection_without_a_suggestion_says_only_why(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 11)
        reject(client, staff, 11, reason="Closed that week.")
        [(_, _, message)] = self.notices(notification_repository)
        assert message.endswith("Reason: Closed that week.")

    def test_tc_d31_a_blocked_approval_notifies_nobody(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 10, event_id=OTHER_EVENT, status=BookingStatus.CONFIRMED)
        seed(booking_repository, 11)
        approve(client, staff, 11)
        assert notification_repository.notifications == []

    def test_tc_d32_a_failed_notice_does_not_undo_the_decision(
        self, client, staff, events, booking_repository, notification_repository, monkeypatch
    ):
        def broken(**_kwargs):
            raise RuntimeError("notifications table missing")

        monkeypatch.setattr(notification_repository, "create_notice", broken)
        seed(booking_repository, 11)
        assert approve(client, staff, 11).status_code == 200
        assert status_of(booking_repository, 11) is BookingStatus.CONFIRMED

    def test_tc_d33_the_coordinator_sees_the_decision_on_the_event(
        self, client, staff, coordinator, events, booking_repository
    ):
        seed(booking_repository, 11)
        reject(client, staff, 11, reason="Closed that week.", suggestion="Bertha Room")

        [listed] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()

        assert listed["status"] == "Rejected"
        assert listed["decision"]["reason"] == "Closed that week."
        assert listed["decision"]["suggestion"] == "Bertha Room"
        assert listed["decision"]["byName"] == "Sam"

    def test_tc_d34_the_notice_reaches_the_coordinators_list(
        self, client, staff, coordinator, events, booking_repository
    ):
        seed(booking_repository, 11)
        approve(client, staff, 11)
        [notice] = client.get("/notifications", headers=coordinator).json()
        assert notice["kind"] == "booking-confirmed"
        assert notice["read"] is False


class TestVenueStaffOnly:
    """AC6: Venue Staff only. The decision is logged with who and when."""

    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_d35_other_roles_cannot_see_or_decide(
        self, client, auth_headers, events, booking_repository, role
    ):
        seed(booking_repository, 11)
        headers = auth_headers(role)
        assert client.get("/booking-requests", headers=headers).status_code == 403
        assert approve(client, headers, 11).status_code == 403
        assert reject(client, headers, 11, reason="No").status_code == 403
        assert status_of(booking_repository, 11) is BookingStatus.REQUESTED

    def test_tc_d36_signed_out_is_refused(self, client):
        assert client.get("/booking-requests").status_code == 401
        assert client.post("/booking-requests/1/approve").status_code == 401

    def test_tc_d37_the_decision_records_who_and_when(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        approve(client, staff, 11)
        decision = booking_repository.get_booking(11).decision
        assert decision.by_id == VENUE_STAFF_ID
        assert decision.by_name == "Sam"
        assert decision.at


class TestThePlaceholderRule:
    """The US15.1 placeholder `availability.find_clashes`, on its own."""

    def booking(self, booking_id, status, starts, ends, venue_id=1, expires=""):
        return Booking(
            id=booking_id, event_id=EVENT_ID, venue_id=venue_id, venue_name="",
            starts_at=starts, ends_at=ends, status=status, requested_by_id=None,
            requested_at="", hold_expires_at=expires,
        )

    def test_tc_d38_only_confirmed_and_unexpired_holds_take_a_slot(self):
        assert availability.takes_slot(
            self.booking(1, BookingStatus.CONFIRMED, "2027-11-02T09:00", "2027-11-02T10:00"), NOW
        )
        assert availability.takes_slot(
            self.booking(1, BookingStatus.HELD, "2027-11-02T09:00", "2027-11-02T10:00",
                         expires="2027-10-02T09:00"), NOW
        )
        for status in (BookingStatus.REQUESTED, BookingStatus.REJECTED, BookingStatus.CANCELLED):
            assert not availability.takes_slot(
                self.booking(1, status, "2027-11-02T09:00", "2027-11-02T10:00"), NOW
            )

    def test_tc_d39_without_a_venue_there_are_no_buffers(self):
        mine = self.booking(1, BookingStatus.REQUESTED, "2027-11-02T10:00", "2027-11-02T11:00")
        before = self.booking(2, BookingStatus.CONFIRMED, "2027-11-02T09:00", "2027-11-02T10:00")
        assert availability.find_clashes(mine, None, [mine, before], now=NOW) == []

    def test_tc_d40_a_booking_with_unreadable_times_is_left_out(self):
        mine = self.booking(1, BookingStatus.REQUESTED, "2027-11-02T10:00", "2027-11-02T11:00")
        broken = self.booking(2, BookingStatus.CONFIRMED, "not a time", "2027-11-02T11:00")
        assert availability.find_clashes(mine, None, [mine, broken], now=NOW) == []


class TestTheSupabaseStore:
    class Fake:
        """Records calls; answers reads with one row and RPCs with `answer`."""

        def __init__(self, answer="confirmed", updated=True):
            self.calls: list[tuple] = []
            self.answer = answer
            self.updated = updated
            self._rpc = False

        def __getattr__(self, name):
            def record(*args, **_kwargs):
                self.calls.append((name, *args))
                if name == "rpc":
                    self._rpc = True
                return self

            return record

        def execute(self):
            if self._rpc:
                self._rpc = False
                return type("R", (), {"data": self.answer})()
            if any(call[0] == "update" for call in self.calls) and not self.updated:
                return type("R", (), {"data": []})()
            row = {
                "id": 11, "event_id": EVENT_ID, "venue_id": 1, "start_at": "2027-11-02T09:00",
                "end_at": "2027-11-02T17:00", "status": "Confirmed", "created_at": "2027-09-01",
                "decided_at": "2027-10-01T01:00:00", "decided_by_id": VENUE_STAFF_ID,
                "decided_by": {"name": "Sam"},
            }
            return type("R", (), {"data": [row]})()

    def use(self, monkeypatch, fake):
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)
        return booking_store.SupabaseBookings()

    def test_tc_d41_approve_calls_the_locking_rpc(self, monkeypatch):
        fake = self.Fake("confirmed")
        confirmed = self.use(monkeypatch, fake).approve(11, actor_id=VENUE_STAFF_ID)
        assert ("rpc", "approve_venue_booking", {"p_booking_id": 11,
                "p_actor_id": VENUE_STAFF_ID}) in fake.calls
        assert confirmed.decision.by_name == "Sam"

    @pytest.mark.parametrize(
        ("answer", "error"),
        [("clash", SlotTaken), ("not-requested", booking_store.StaleBookingStatus)],
    )
    def test_tc_d42_each_rpc_refusal_is_its_own_error(self, monkeypatch, answer, error):
        with pytest.raises(error):
            self.use(monkeypatch, self.Fake(answer)).approve(11, actor_id=VENUE_STAFF_ID)

    def test_tc_d43_reject_writes_only_a_still_requested_row(self, monkeypatch):
        fake = self.Fake()
        self.use(monkeypatch, fake).reject(
            11, actor_id=VENUE_STAFF_ID, reason="Closed.", suggestion=""
        )
        [(_, changes)] = [call for call in fake.calls if call[0] == "update"]
        assert changes["status"] == "Rejected"
        assert changes["rejection_reason"] == "Closed."
        assert changes["suggested_alternative"] is None
        assert changes["decided_by_id"] == VENUE_STAFF_ID
        assert ("eq", "status", "Requested") in fake.calls

    def test_tc_d44_no_row_rejected_means_it_was_already_decided(self, monkeypatch):
        with pytest.raises(booking_store.StaleBookingStatus):
            self.use(monkeypatch, self.Fake(updated=False)).reject(
                11, actor_id=VENUE_STAFF_ID, reason="Closed."
            )

    def test_tc_d45_the_queue_reads_requested_oldest_first(self, monkeypatch):
        fake = self.Fake()
        self.use(monkeypatch, fake).list_requested()
        assert ("eq", "status", "Requested") in fake.calls
        assert fake.calls.index(("order", "created_at")) < fake.calls.index(("order", "id"))

