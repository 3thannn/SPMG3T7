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






class TestApproving:
    """AC2: Approve -> Confirmed, with the conflict check run again at approval."""











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


    def test_tc_d24_after_a_rejection_the_slot_can_be_confirmed(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 11)
        seed(booking_repository, 12, event_id=OTHER_EVENT)
        reject(client, staff, 11, reason="Changed plans.")
        assert approve(client, staff, 12).status_code == 200


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




class TestVenueStaffOnly:
    """AC6: Venue Staff only. The decision is logged with who and when."""



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


    def test_tc_d39_without_a_venue_there_are_no_buffers(self):
        mine = self.booking(1, BookingStatus.REQUESTED, "2027-11-02T10:00", "2027-11-02T11:00")
        before = self.booking(2, BookingStatus.CONFIRMED, "2027-11-02T09:00", "2027-11-02T10:00")
        assert availability.find_clashes(mine, None, [mine, before], now=NOW) == []



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

