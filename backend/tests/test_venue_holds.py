"""Tentative venue holds — US14.3 (reworked for Week 9) and US14.6.

Week 9: a tentative hold starts after venue approval. The Coordinator requests
a venue, Venue Staff approve it as a hold with an expiry, and the Coordinator
confirms it before it lapses. Venue Staff can change the expiry or release the
hold (US14.6). Test case ids (TC-H…) match the US14.3 and US14.6 test cases; the
classes follow the acceptance criteria in order.

"Now" is pinned to NOW for every test, so expiry is decided by the test rather
than by the day it runs. Fixture venues are 1 (Great Hall) and 2 (Bertha
Room); the fixture Venue Staff member is Sam and the Coordinator is Priya.
"""

from datetime import datetime

import pytest

from app import booking_store
from app.booking_store import BookingStatus, HoldExpired
from app.event_status import EventStatus
from tests.conftest import COORDINATOR_ID, VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, request, seed_event

NOW = datetime(2027, 10, 1, 9, 0)
EXPIRY = "2027-10-08T17:00"


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    """Pin the clock holds are judged by. Returns a setter to move it on."""
    current = {"now": NOW}
    monkeypatch.setattr(booking_store, "local_now", lambda: current["now"])

    def move_to(moment: datetime) -> None:
        current["now"] = moment

    return move_to


@pytest.fixture
def staff(auth_headers):
    return auth_headers("Venue Staff")


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def event(event_repository):
    """A Planning event assigned to the fixture Coordinator."""
    return seed_event(event_repository, status=EventStatus.PLANNING)


@pytest.fixture
def requested(client, coordinator, event) -> str:
    """The id of a Requested booking of the Great Hall, 2 Nov 09:00-17:00."""
    response = request(client, coordinator)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def approve(client, headers, booking_id: str, hold_until: str | None = EXPIRY):
    body = {} if hold_until is None else {"holdUntil": hold_until}
    return client.post(f"/booking-requests/{booking_id}/approve", json=body, headers=headers)


def confirm(client, headers, booking_id: str, event_id: int = EVENT_ID):
    return client.post(f"/events/{event_id}/bookings/{booking_id}/confirm", headers=headers)


def bad_request(response) -> str:
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_booking"
    return detail["message"]


def refused(response) -> dict:
    assert response.status_code == 409, response.text
    return response.json()["detail"]


def notices(notification_repository, kind: str) -> list[str]:
    return [item.message for item in notification_repository.notifications if item.kind == kind]


class TestTheHoldStartsAfterApproval:
    """AC1: Venue Staff approve a request as a tentative hold; it is Held, with
    the approval recorded, linked to the event and its Coordinator."""

    def test_tc_h01_venue_staff_approve_a_request_as_a_hold(
        self, client, staff, requested
    ):
        response = approve(client, staff, requested)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Held"
        assert body["eventId"] == str(EVENT_ID)
        assert body["venueName"] == "Great Hall"
        assert body["holdExpiresAt"] == EXPIRY
        assert body["holdExpired"] is False
        assert body["heldByName"] == "Sam"

    def test_tc_h02_the_approval_is_recorded_on_the_hold(
        self, client, staff, requested, booking_repository
    ):
        approve(client, staff, requested)

        [stored] = booking_repository.bookings
        assert stored.status is BookingStatus.HELD
        assert stored.requested_by_id == COORDINATOR_ID
        assert stored.held_by_id == VENUE_STAFF_ID
        assert stored.decision is not None
        assert stored.decision.by_id == VENUE_STAFF_ID

    def test_tc_h03_there_is_no_hold_before_a_request(self, client, staff, event):
        assert client.post("/holds", json={}, headers=staff).status_code == 405

    def test_tc_h04_approving_without_an_expiry_still_confirms_outright(
        self, client, staff, requested
    ):
        assert approve(client, staff, requested, hold_until=None).json()["status"] == "Confirmed"

    def test_tc_h05_the_coordinator_is_told_to_confirm_in_time(
        self, client, staff, requested, notification_repository
    ):
        approve(client, staff, requested)

        [message] = notices(notification_repository, "hold-placed")
        assert "as a tentative hold until 08 Oct 2027, 17:00" in message
        assert "Confirm the booking before then" in message

    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_h06_only_venue_staff_approve_holds(self, client, auth_headers, requested, role):
        assert approve(client, auth_headers(role), requested).status_code == 403


class TestExpiry:
    """AC2: the expiry is in the future and no later than the booking starts."""

    def test_tc_h11_a_malformed_expiry_is_refused(self, client, staff, requested):
        assert bad_request(approve(client, staff, requested, "next week")) == (
            "Give the expiry as YYYY-MM-DDTHH:MM."
        )

    def test_tc_h16_expiry_exactly_now_is_refused(self, client, staff, requested):
        assert bad_request(approve(client, staff, requested, "2027-10-01T09:00")) == (
            "The hold must expire in the future."
        )

    def test_tc_h17_expiry_a_minute_from_now_is_accepted(self, client, staff, requested):
        assert approve(client, staff, requested, "2027-10-01T09:01").status_code == 200

    def test_tc_h18_expiry_after_the_booking_starts_is_refused(self, client, staff, requested):
        assert bad_request(approve(client, staff, requested, "2027-11-02T09:01")) == (
            "The hold must expire no later than the booking starts."
        )

    def test_tc_h19_expiry_exactly_at_the_start_is_accepted(self, client, staff, requested):
        assert approve(client, staff, requested, "2027-11-02T09:00").status_code == 200


class TestTheSlotIsTaken:
    """AC3: while Held and not expired, the slot counts as taken (US15.1, US9.4)."""

    def test_tc_h23_a_minute_before_expiry_it_still_holds(
        self, client, staff, requested, booking_repository, frozen_now
    ):
        approve(client, staff, requested)
        frozen_now(datetime(2027, 10, 8, 16, 59))
        assert booking_repository.bookings[0].holds_venue is True

    def test_tc_h24_at_expiry_the_slot_is_free(
        self, client, staff, requested, booking_repository, frozen_now
    ):
        approve(client, staff, requested)
        frozen_now(datetime(2027, 10, 8, 17, 0))
        assert booking_repository.bookings[0].holds_venue is False


class TestTheCoordinatorConfirms:
    """AC4: the Coordinator confirms the hold before it expires; after, it cannot be."""

    def test_tc_h27_the_coordinator_confirms_a_held_venue(
        self, client, staff, coordinator, requested, booking_repository
    ):
        approve(client, staff, requested)

        response = confirm(client, coordinator, requested)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Confirmed"
        assert body["holdExpiresAt"] == EXPIRY
        [stored] = booking_repository.bookings
        assert stored.status is BookingStatus.CONFIRMED
        assert stored.holds_venue is True

    def test_tc_h28_only_the_assigned_coordinator_confirms(
        self, client, staff, auth_headers, requested
    ):
        approve(client, staff, requested)
        assert confirm(client, staff, requested).status_code == 403

    def test_tc_h29_a_request_not_yet_approved_cannot_be_confirmed(
        self, client, coordinator, requested
    ):
        detail = refused(confirm(client, coordinator, requested))
        assert detail["reason"] == "not-held"
        assert "not approved this booking as a hold yet" in detail["message"]

    def test_tc_h30_an_expired_hold_cannot_be_confirmed(
        self, client, staff, coordinator, requested, booking_repository, frozen_now
    ):
        approve(client, staff, requested)
        frozen_now(datetime(2027, 10, 8, 17, 0))

        detail = refused(confirm(client, coordinator, requested))

        assert detail["reason"] == "hold-expired"
        assert "expired at 2027-10-08 17:00" in detail["message"]
        assert booking_repository.bookings[0].status is BookingStatus.HELD

    def test_tc_h31_a_confirmed_hold_cannot_be_confirmed_twice(
        self, client, staff, coordinator, requested
    ):
        approve(client, staff, requested)
        confirm(client, coordinator, requested)
        assert refused(confirm(client, coordinator, requested))["message"] == (
            "This booking is already confirmed."
        )


class TestNeverConfirmedOnItsOwn:
    """AC5: a Held booking is never shown or counted as Confirmed until the
    Coordinator confirms it, and Venue Staff cannot decide it twice."""

    def test_tc_h41_venue_staff_cannot_approve_a_hold_again(
        self, client, staff, requested, booking_repository
    ):
        approve(client, staff, requested)

        detail = refused(approve(client, staff, requested, hold_until=None))

        assert detail["reason"] == "not-requested"
        assert "already approved as a tentative hold" in detail["message"]
        assert booking_repository.bookings[0].status is BookingStatus.HELD

    def test_tc_h42_a_hold_is_reported_as_held_however_long_it_waits(
        self, client, staff, coordinator, requested, frozen_now
    ):
        approve(client, staff, requested)
        for moment in (NOW, datetime(2027, 10, 8, 17, 0), datetime(2027, 11, 3, 0, 0)):
            frozen_now(moment)
            [listed] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
            assert listed["status"] == "Held"

    def test_tc_h43_a_held_booking_holds_up_the_safety_check(
        self, client, staff, coordinator, requested
    ):
        approve(client, staff, requested)
        response = client.post(f"/events/{EVENT_ID}/safety-check", headers=coordinator)
        assert response.status_code == 409


def hold_path(booking_id: str, action: str = "") -> str:
    return f"/holds/{booking_id}" + (f"/{action}" if action else "")


class TestVenueStaffUpdateTheExpiry:
    """US14.6 AC1-AC2: Venue Staff change a hold's expiry, under the same rules,
    and the Coordinator is told."""

    def test_tc_h60_venue_staff_extend_a_hold(
        self, client, staff, requested, booking_repository, notification_repository
    ):
        approve(client, staff, requested)

        response = client.patch(
            hold_path(requested), json={"expiresAt": "2027-10-15T12:00"}, headers=staff
        )

        assert response.status_code == 200, response.text
        assert response.json()["holdExpiresAt"] == "2027-10-15T12:00"
        assert booking_repository.bookings[0].hold_expires_at == "2027-10-15T12:00"
        [message] = notices(notification_repository, "hold-updated")
        assert "it now expires 15 Oct 2027, 12:00" in message

    def test_tc_h61_venue_staff_shorten_a_hold(self, client, staff, requested):
        approve(client, staff, requested)
        response = client.patch(
            hold_path(requested), json={"expiresAt": "2027-10-02T09:00"}, headers=staff
        )
        assert response.json()["holdExpiresAt"] == "2027-10-02T09:00"

    @pytest.mark.parametrize(
        ("expiry", "message"),
        [
            (None, "Give the hold an expiry date and time."),
            ("2027-10-01T09:00", "The hold must expire in the future."),
            ("2027-11-02T09:01", "The hold must expire no later than the booking starts."),
        ],
    )
    def test_tc_h62_the_new_expiry_follows_the_hold_rules(
        self, client, staff, requested, expiry, message
    ):
        approve(client, staff, requested)
        body = {} if expiry is None else {"expiresAt": expiry}
        assert bad_request(client.patch(hold_path(requested), json=body, headers=staff)) == message

    def test_tc_h63_an_expired_hold_cannot_be_changed(
        self, client, staff, requested, frozen_now
    ):
        approve(client, staff, requested)
        frozen_now(datetime(2027, 10, 8, 17, 0))
        response = client.patch(
            hold_path(requested), json={"expiresAt": "2027-10-20T09:00"}, headers=staff
        )
        assert refused(response)["reason"] == "hold-expired"

    def test_tc_h64_a_confirmed_booking_is_no_longer_a_hold(
        self, client, staff, coordinator, requested
    ):
        approve(client, staff, requested)
        confirm(client, coordinator, requested)
        response = client.patch(
            hold_path(requested), json={"expiresAt": "2027-10-20T09:00"}, headers=staff
        )
        assert refused(response)["message"] == "The Coordinator has already confirmed this booking."

    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_h65_only_venue_staff_change_holds(
        self, client, staff, auth_headers, requested, role
    ):
        approve(client, staff, requested)
        response = client.patch(
            hold_path(requested), json={"expiresAt": "2027-10-20T09:00"}, headers=auth_headers(role)
        )
        assert response.status_code == 403

    def test_tc_h66_an_unknown_hold_is_404(self, client, staff, event):
        response = client.patch(hold_path("999"), json={"expiresAt": EXPIRY}, headers=staff)
        assert response.status_code == 404


class TestVenueStaffReleaseAHold:
    """US14.6 AC3-AC5: Venue Staff release a hold early, with a reason; the slot
    is free at once, the release is on record, and the Coordinator is told."""

    def test_tc_h70_venue_staff_release_a_hold(
        self, client, staff, requested, booking_repository, notification_repository
    ):
        approve(client, staff, requested)

        response = client.post(
            hold_path(requested, "release"),
            json={"reason": "Hall needed for exams."},
            headers=staff,
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"
        [stored] = booking_repository.bookings
        assert stored.holds_venue is False
        assert stored.cancellation.by_id == VENUE_STAFF_ID
        assert stored.cancellation.reason == "Hall needed for exams."
        [message] = notices(notification_repository, "hold-released")
        assert message.endswith("Reason: Hall needed for exams.")

    def test_tc_h71_a_reason_is_required(self, client, staff, requested):
        approve(client, staff, requested)
        response = client.post(hold_path(requested, "release"), json={"reason": " "}, headers=staff)
        assert bad_request(response) == "Give the Coordinator a reason for releasing this hold."

    def test_tc_h72_a_released_hold_cannot_be_confirmed(
        self, client, staff, coordinator, requested
    ):
        approve(client, staff, requested)
        client.post(hold_path(requested, "release"), json={"reason": "Closed."}, headers=staff)
        assert refused(confirm(client, coordinator, requested))["message"] == (
            "This hold has been released or cancelled."
        )

    def test_tc_h73_a_released_hold_cannot_be_released_again(self, client, staff, requested):
        approve(client, staff, requested)
        client.post(hold_path(requested, "release"), json={"reason": "Closed."}, headers=staff)
        response = client.post(
            hold_path(requested, "release"), json={"reason": "Closed."}, headers=staff
        )
        assert refused(response)["reason"] == "not-held"

    def test_tc_h74_the_venue_list_shows_holds_for_staff(self, client, staff, requested):
        approve(client, staff, requested)
        [listed] = client.get("/holds?venueId=1", headers=staff).json()
        assert (listed["status"], listed["eventTitle"]) == ("Held", "Faculty Welcome Night")


HELD_ROW = {
    "id": 41,
    "event_id": EVENT_ID,
    "venue_id": 1,
    "start_at": "2027-11-02T09:00:00",
    "end_at": "2027-11-02T17:00:00",
    "status": "Held",
    "requested_by_id": COORDINATOR_ID,
    "created_at": "2027-10-01T09:00:00",
    "headcount": 30,
    "hold_expires_at": "2027-10-08T17:00:00",
    "held_by_id": VENUE_STAFF_ID,
    "decided_at": "2027-10-01T09:00:00",
    "decided_by_id": VENUE_STAFF_ID,
    "venues": {"name": "Great Hall"},
    "held_by": {"name": "Sam"},
}


class FakeSupabase:
    """Records updates, filters and RPC calls; answers reads with HELD_ROW."""

    def __init__(self, rpc_answer: str = "held", updated: bool = True):
        self.updates: list[dict] = []
        self.filters: list[tuple] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.rpc_answer = rpc_answer
        self.updated = updated

    def table(self, _name):
        return self

    def update(self, row):
        self.updates.append(row)
        self._answer = [dict(HELD_ROW)] if self.updated else []
        return self

    def select(self, *_args):
        return self

    def eq(self, *args):
        self.filters.append(("eq", *args))
        return self

    def gt(self, *args):
        self.filters.append(("gt", *args))
        return self

    def limit(self, *_args):
        return self

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        self._answer = self.rpc_answer
        return self

    def execute(self):
        if getattr(self, "_answer", None) is not None:
            answer, self._answer = self._answer, None
            return type("Response", (), {"data": answer})()
        return type("Response", (), {"data": [dict(HELD_ROW)]})()


class TestTheSupabaseStore:
    def test_tc_h49_approve_as_hold_calls_the_rpc_with_the_expiry(self, monkeypatch):
        fake = FakeSupabase("held")
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)

        hold = booking_store.SupabaseBookings().approve_as_hold(
            41, actor_id=VENUE_STAFF_ID, expires_at=EXPIRY
        )

        assert fake.rpcs == [
            (
                "approve_venue_booking_as_hold",
                {"p_booking_id": 41, "p_actor_id": VENUE_STAFF_ID, "p_expires_at": EXPIRY},
            )
        ]
        assert hold.status is BookingStatus.HELD
        assert hold.held_by_name == "Sam"

    @pytest.mark.parametrize(
        ("answer", "error"),
        [
            ("clash", booking_store.SlotTaken),
            ("not-requested", booking_store.StaleBookingStatus),
            ("bad-expiry", booking_store.StaleBookingStatus),
        ],
    )
    def test_tc_h50_each_approval_refusal_becomes_its_own_error(
        self, monkeypatch, answer, error
    ):
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: FakeSupabase(answer))
        with pytest.raises(error):
            booking_store.SupabaseBookings().approve_as_hold(
                41, actor_id=VENUE_STAFF_ID, expires_at=EXPIRY
            )

    def test_tc_h51_confirm_hold_calls_the_rpc(self, monkeypatch):
        fake = FakeSupabase("confirmed")
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)

        booking_store.SupabaseBookings().confirm_hold(41, actor_id=COORDINATOR_ID)

        assert fake.rpcs == [
            ("confirm_held_booking", {"p_booking_id": 41, "p_actor_id": COORDINATOR_ID})
        ]

    @pytest.mark.parametrize(
        ("answer", "error"),
        [
            ("expired", HoldExpired),
            ("stale-event", booking_store.event_store.StaleEventStatus),
            ("not-held", booking_store.StaleBookingStatus),
        ],
    )
    def test_tc_h52_each_confirm_refusal_becomes_its_own_error(self, monkeypatch, answer, error):
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: FakeSupabase(answer))
        with pytest.raises(error):
            booking_store.SupabaseBookings().confirm_hold(41, actor_id=COORDINATOR_ID)

    def test_tc_h53_update_hold_matches_only_a_live_hold_and_clears_the_warning(
        self, monkeypatch
    ):
        fake = FakeSupabase()
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)

        booking_store.SupabaseBookings().update_hold(41, expires_at="2027-10-15T12:00")

        assert fake.updates == [{"hold_expires_at": "2027-10-15T12:00", "expiry_warned_at": None}]
        assert ("eq", "status", "Held") in fake.filters
        assert ("gt", "hold_expires_at", "2027-10-01T09:00:00") in fake.filters

    def test_tc_h54_update_hold_that_matched_nothing_is_stale(self, monkeypatch):
        monkeypatch.setattr(
            booking_store.supabase_client, "admin", lambda: FakeSupabase(updated=False)
        )
        with pytest.raises(booking_store.StaleBookingStatus):
            booking_store.SupabaseBookings().update_hold(41, expires_at="2027-10-15T12:00")
