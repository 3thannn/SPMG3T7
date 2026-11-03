"""Tentative venue holds — US14.3.

Venue Staff place a hold on a venue with an expiry, to keep a slot for a
Coordinator who is still finalising without blocking the venue forever. Test
case ids (TC-H…) match the US14.3 test cases document; the classes follow the
acceptance criteria in order.

"Now" is pinned to NOW for every test, so expiry is decided by the test rather
than by the day it runs. Fixture venues are 1 (Great Hall) and 2 (Bertha
Room); the fixture Venue Staff member is Sam and the Coordinator is Priya.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app import booking_store
from app.booking_store import BookingStatus, HoldExpired
from app.event_status import EventStatus
from app.venue_turnaround import find_conflicts
from tests.conftest import COORDINATOR_ID, VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, request, seed_event

NOW = datetime(2027, 10, 1, 9, 0)
GREAT_HALL = "1"

#: A valid hold. Tests override one field at a time.
HOLD = {
    "venueId": GREAT_HALL,
    "eventId": str(EVENT_ID),
    "startsAt": "2027-11-02T09:00",
    "endsAt": "2027-11-02T17:00",
    "expiresAt": "2027-10-08T17:00",
}


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
    """An Approved event assigned to the fixture Coordinator."""
    return seed_event(event_repository)


def place(client, headers, **overrides):
    """POST a hold with overrides; `None` drops the field from the body."""
    body = {**HOLD, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post("/holds", json=body, headers=headers)


def to_request(client, headers, booking_id: str, event_id: int = EVENT_ID):
    return client.post(f"/events/{event_id}/bookings/{booking_id}/request", headers=headers)


def bad_request(response) -> str:
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_booking"
    return detail["message"]


def refused(response) -> dict:
    assert response.status_code == 409, response.text
    return response.json()["detail"]


class TestPlacingAHold:
    """AC1: a hold is a venue booking with status Held, linked to an event and its Coordinator."""

    def test_tc_h01_venue_staff_place_a_hold(self, client, staff, event):
        response = place(client, staff)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "Held"
        assert body["eventId"] == str(EVENT_ID)
        assert body["eventTitle"] == "Faculty Welcome Night"
        assert body["venueName"] == "Great Hall"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["endsAt"] == "2027-11-02T17:00"
        assert body["holdExpiresAt"] == "2027-10-08T17:00"
        assert body["holdExpired"] is False
        assert body["heldByName"] == "Sam"

    def test_tc_h02_it_is_stored_as_a_booking_nobody_has_requested_yet(
        self, client, staff, event, booking_repository
    ):
        place(client, staff)

        [stored] = booking_repository.bookings
        assert stored.status is BookingStatus.HELD
        assert stored.event_id == EVENT_ID
        assert stored.held_by_id == VENUE_STAFF_ID
        assert stored.requested_by_id is None
        assert stored.headcount == 30

    def test_tc_h03_the_events_coordinator_sees_it_on_the_event(
        self, client, staff, coordinator, event
    ):
        place(client, staff)

        listed = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()
        assert [(item["status"], item["venueName"]) for item in listed] == [("Held", "Great Hall")]

    def test_tc_h04_placing_a_hold_does_not_move_the_event(
        self, client, staff, event, event_repository
    ):
        place(client, staff)
        assert event_repository.get_event(EVENT_ID).status is EventStatus.APPROVED

    def test_tc_h05_a_hold_can_be_placed_for_a_planning_event(
        self, client, staff, event_repository
    ):
        seed_event(event_repository, status=EventStatus.PLANNING)
        assert place(client, staff).status_code == 201

    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead"]
    )
    def test_tc_h06_only_venue_staff_place_holds(self, client, auth_headers, event, role):
        assert place(client, auth_headers(role)).status_code == 403

    def test_tc_h07_an_event_with_no_coordinator_cannot_be_held_for(
        self, client, staff, event_repository
    ):
        seed_event(event_repository, coordinator_id=None)
        assert refused(place(client, staff))["reason"] == "no-coordinator"

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (EventStatus.SUBMITTED, "not-approved"),
            (EventStatus.UNDER_REVIEW, "not-approved"),
            (EventStatus.REJECTED, "event-closed"),
            (EventStatus.CANCELLED, "event-closed"),
        ],
    )
    def test_tc_h08_only_an_event_that_can_take_bookings_can_be_held_for(
        self, client, staff, event_repository, status, reason
    ):
        seed_event(event_repository, status=status)
        assert refused(place(client, staff))["reason"] == reason

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"venueId": None}, "Choose a venue."),
            ({"venueId": "999"}, "That venue is not in the catalogue."),
            ({"venueId": "abc"}, "That venue is not in the catalogue."),
            ({"eventId": None}, "Choose the event to hold this venue for."),
            ({"eventId": "999"}, "That event does not exist."),
            ({"eventId": "abc"}, "That event does not exist."),
            ({"startsAt": None}, "Give the booking a start time."),
            ({"endsAt": "2027-11-02T08:00"}, "The booking must end after it starts."),
            (
                {"startsAt": "2027-02-30T09:00"},
                "The start time 2027-02-30T09:00 is not a real date and time.",
            ),
        ],
        ids=["no-venue", "unknown-venue", "bad-venue-id", "no-event", "unknown-event",
             "bad-event-id", "no-start", "end-before-start", "impossible-date"],
    )
    def test_tc_h09_a_bad_hold_is_refused_with_a_sentence(
        self, client, staff, event, overrides, message
    ):
        assert bad_request(place(client, staff, **overrides)) == message

    def test_tc_h10_a_draft_event_is_not_offered(self, client, staff, event_repository):
        seed_event(event_repository, status=EventStatus.DRAFT)
        assert bad_request(place(client, staff)) == "That event does not exist."


class TestExpiry:
    """AC2: expiry date/time is required and must be in the future."""

    def test_tc_h11_expiry_is_required(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt=None)) == (
            "Give the hold an expiry date and time."
        )


    @pytest.mark.parametrize("raw", ["next week", "2027-10-08", "08/10/2027 17:00"])
    def test_tc_h13_expiry_must_be_a_date_and_time(self, client, staff, event, raw):
        assert bad_request(place(client, staff, expiresAt=raw)) == (
            "Give the expiry as YYYY-MM-DDTHH:MM."
        )

    def test_tc_h14_expiry_must_be_a_real_date(self, client, staff, event):
        assert "is not a real date and time" in bad_request(
            place(client, staff, expiresAt="2027-10-32T10:00")
        )

    def test_tc_h15_expiry_in_the_past_is_refused(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="2027-09-30T09:00")) == (
            "The hold must expire in the future."
        )



    def test_tc_h18_expiry_after_the_booking_starts_is_refused(self, client, staff, event):
        assert bad_request(place(client, staff, expiresAt="2027-11-02T09:01")) == (
            "The hold must expire no later than the booking starts."
        )


    def test_tc_h20_a_hold_cannot_start_in_the_past(self, client, staff, event):
        assert bad_request(
            place(client, staff, startsAt="2027-09-30T09:00", endsAt="2027-09-30T17:00")
        ) == "A hold cannot start in the past."


class TestTheSlotIsTaken:
    """AC3: while Held and not expired, the slot counts as taken (US15.1, US9.4)."""





    def test_tc_h25_an_expired_hold_clashes_with_nothing(
        self, client, staff, coordinator, event, booking_repository, frozen_now
    ):
        place(client, staff)
        frozen_now(datetime(2027, 10, 9, 9, 0))
        # US15.1: once the hold has expired the slot is free to request.
        assert request(client, coordinator).status_code == 201

        conflicts = find_conflicts(
            booking_repository.list_for_venue(1), setup_minutes=0, turnaround_minutes=0
        )
        assert conflicts == ()



class TestTurningAHoldIntoARequest:
    """AC4: the Coordinator can turn the hold into a booking request before it expires."""

    def test_tc_h27_the_coordinator_requests_a_held_venue(
        self, client, staff, coordinator, event, booking_repository
    ):
        hold = place(client, staff).json()

        response = to_request(client, coordinator, hold["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Requested"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["holdExpiresAt"] == "2027-10-08T17:00"
        assert body["holdExpired"] is False
        [stored] = booking_repository.bookings
        assert stored.requested_by_id == COORDINATOR_ID
        assert stored.holds_venue is True

    def test_tc_h28_the_first_request_moves_an_approved_event_to_planning(
        self, client, staff, coordinator, event, event_repository
    ):
        hold = place(client, staff).json()
        to_request(client, coordinator, hold["id"])
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

    def test_tc_h29_a_planning_event_stays_planning(
        self, client, staff, coordinator, event_repository
    ):
        seed_event(event_repository, status=EventStatus.PLANNING)
        hold = place(client, staff).json()
        assert to_request(client, coordinator, hold["id"]).status_code == 200
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

    def test_tc_h30_an_expired_hold_cannot_be_requested(
        self, client, staff, coordinator, event, booking_repository, frozen_now
    ):
        hold = place(client, staff).json()
        frozen_now(datetime(2027, 10, 8, 17, 0))

        detail = refused(to_request(client, coordinator, hold["id"]))

        assert detail["reason"] == "hold-expired"
        assert "expired at 2027-10-08 17:00" in detail["message"]
        assert booking_repository.bookings[0].status is BookingStatus.HELD


    def test_tc_h32_a_hold_is_requested_only_once(self, client, staff, coordinator, event):
        hold = place(client, staff).json()
        to_request(client, coordinator, hold["id"])

        detail = refused(to_request(client, coordinator, hold["id"]))
        assert detail["reason"] == "not-held"
        assert detail["message"] == "This hold has already been turned into a booking request."

    def test_tc_h33_a_released_hold_cannot_be_requested(
        self, client, staff, coordinator, event
    ):
        hold = place(client, staff).json()
        client.post(
            f"/events/{EVENT_ID}/bookings/{hold['id']}/cancel",
            json={"reason": "Not needed after all."},
            headers=coordinator,
        )

        assert refused(to_request(client, coordinator, hold["id"]))["message"] == (
            "This hold has been cancelled."
        )


    def test_tc_h35_another_coordinator_cannot_see_it(
        self, client, staff, coordinator, event_repository
    ):
        seed_event(event_repository, coordinator_id=99)
        hold = place(client, staff).json()
        assert to_request(client, coordinator, hold["id"]).status_code == 404



    @pytest.mark.parametrize("booking_id", ["999", "abc"])
    def test_tc_h38_an_unknown_booking_is_not_found(
        self, client, coordinator, event, booking_id
    ):
        assert to_request(client, coordinator, booking_id).status_code == 404

    def test_tc_h39_a_closed_event_cannot_take_the_request(
        self, client, staff, coordinator, event, event_repository
    ):
        hold = place(client, staff).json()
        event_repository.events = [
            replace(item, status=EventStatus.CANCELLED) if item.id == EVENT_ID else item
            for item in event_repository.events
        ]
        assert refused(to_request(client, coordinator, hold["id"]))["reason"] == "event-closed"

    def test_tc_h40_expiring_between_the_check_and_the_write_is_refused(
        self, client, staff, coordinator, event, booking_repository, monkeypatch
    ):
        hold = place(client, staff).json()

        def lapsed(*_args, **_kwargs):
            raise HoldExpired

        monkeypatch.setattr(booking_repository, "request_hold", lapsed)
        assert refused(to_request(client, coordinator, hold["id"]))["reason"] == "hold-expired"


class TestNeverConfirmed:
    """AC5: a Held booking is never shown or counted as Confirmed."""



    def test_tc_h43_a_requested_hold_is_requested_not_confirmed(
        self, client, staff, coordinator, event
    ):
        hold = place(client, staff).json()
        assert to_request(client, coordinator, hold["id"]).json()["status"] == "Requested"


class TestReleasingAHold:
    def test_tc_h44_the_coordinator_can_release_a_hold(
        self, client, staff, coordinator, event, booking_repository
    ):
        hold = place(client, staff).json()

        response = client.post(
            f"/events/{EVENT_ID}/bookings/{hold['id']}/cancel",
            json={"reason": "Not needed after all."},
            headers=coordinator,
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"
        assert booking_repository.bookings[0].holds_venue is False


class TestWhatVenueStaffSee:
    def test_tc_h45_only_events_that_can_take_a_hold_are_offered(
        self, client, staff, event_repository
    ):
        seed_event(event_repository, event_id=901)
        seed_event(event_repository, event_id=902, status=EventStatus.PLANNING)
        seed_event(event_repository, event_id=903, coordinator_id=None)
        seed_event(event_repository, event_id=904, status=EventStatus.UNDER_REVIEW)
        seed_event(event_repository, event_id=905, status=EventStatus.DRAFT)

        response = client.get("/holds/events", headers=staff)

        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()] == ["901", "902"]
        assert response.json()[0]["coordinatorName"] == "Priya"

    def test_tc_h46_the_venue_lists_its_holds_and_flags_expired_ones(
        self, client, staff, coordinator, event, frozen_now
    ):
        place(client, staff)
        place(client, staff, startsAt="2027-11-03T09:00", endsAt="2027-11-03T17:00",
              expiresAt="2027-10-20T17:00")
        request(client, coordinator, startsAt="2027-11-04T09:00", endsAt="2027-11-04T17:00")
        frozen_now(datetime(2027, 10, 10, 9, 0))

        listed = client.get("/holds", params={"venueId": GREAT_HALL}, headers=staff).json()

        assert [(item["startsAt"], item["holdExpired"]) for item in listed] == [
            ("2027-11-02T09:00", True),
            ("2027-11-03T09:00", False),
        ]
        assert listed[0]["eventTitle"] == "Faculty Welcome Night"

    @pytest.mark.parametrize("venue_id", ["", "abc"])
    def test_tc_h47_the_venue_id_must_be_a_number(self, client, staff, venue_id):
        response = client.get("/holds", params={"venueId": venue_id}, headers=staff)
        assert bad_request(response) == "That venue is not in the catalogue."



HELD_ROW = {
    "id": 41,
    "event_id": EVENT_ID,
    "venue_id": 1,
    "start_at": "2027-11-02T09:00:00",
    "end_at": "2027-11-02T17:00:00",
    "status": "Held",
    "requested_by_id": None,
    "created_at": "2027-10-01T09:00:00",
    "headcount": 30,
    "hold_expires_at": "2027-10-08T17:00:00",
    "held_by_id": VENUE_STAFF_ID,
    "venues": {"name": "Great Hall"},
    "held_by": {"name": "Sam"},
}


class FakeSupabase:
    """Records inserts and RPC calls; answers reads with HELD_ROW."""

    def __init__(self, rpc_answer: str = "requested"):
        self.inserted: list[dict] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.rpc_answer = rpc_answer

    def table(self, _name):
        return self

    def insert(self, row):
        self.inserted.append(row)
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
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
    def test_tc_h49_place_hold_writes_a_held_row_with_its_expiry(self, monkeypatch):
        fake = FakeSupabase()
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)

        hold = booking_store.SupabaseBookings().place_hold(
            event_id=EVENT_ID, venue_id=1, starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00", expires_at="2027-10-08T17:00",
            held_by_id=VENUE_STAFF_ID, headcount=30,
        )

        [row] = fake.inserted
        assert row["status"] == "Held"
        assert row["hold_expires_at"] == "2027-10-08T17:00"
        assert row["held_by_id"] == VENUE_STAFF_ID
        assert row["requested_by_id"] is None
        assert hold.status is BookingStatus.HELD
        assert hold.held_by_name == "Sam"
        assert hold.hold_expires_at == "2027-10-08T17:00:00"

    def test_tc_h50_request_hold_calls_the_rpc_with_the_expected_status(self, monkeypatch):
        fake = FakeSupabase("requested")
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)

        booking_store.SupabaseBookings().request_hold(
            41, actor_id=COORDINATOR_ID, expected_status=EventStatus.APPROVED
        )

        assert fake.rpcs == [
            (
                "request_held_booking",
                {"p_booking_id": 41, "p_expected_status": "Approved",
                 "p_requested_by_id": COORDINATOR_ID},
            )
        ]

    @pytest.mark.parametrize(
        ("answer", "error"),
        [
            ("expired", HoldExpired),
            ("stale-event", booking_store.event_store.StaleEventStatus),
            ("not-held", booking_store.StaleBookingStatus),
        ],
    )
    def test_tc_h51_each_rpc_refusal_becomes_its_own_error(self, monkeypatch, answer, error):
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: FakeSupabase(answer))
        with pytest.raises(error):
            booking_store.SupabaseBookings().request_hold(
                41, actor_id=COORDINATOR_ID, expected_status=EventStatus.APPROVED
            )


class TestRacesAndBadData:
    """What happens when something changes between the route's check and the write."""

    def test_tc_h52_an_unreadable_expiry_counts_as_expired(self, booking_repository):
        hold = booking_repository.place_hold(
            event_id=EVENT_ID, venue_id=1, starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00", expires_at="not a time",
            held_by_id=VENUE_STAFF_ID, headcount=30,
        )
        # A hold must never block a venue longer than anyone agreed to.
        assert hold.hold_expired is True
        assert hold.holds_venue is False

    def test_tc_h53_a_hold_released_during_the_request_says_so(
        self, client, staff, coordinator, event, booking_repository, monkeypatch
    ):
        hold = place(client, staff).json()
        real_request = booking_repository.request_hold

        def released_first(booking_id, **kwargs):
            booking_repository.cancel(booking_id, actor_id=COORDINATOR_ID, reason="Released.")
            return real_request(booking_id, **kwargs)

        monkeypatch.setattr(booking_repository, "request_hold", released_first)
        detail = refused(to_request(client, coordinator, hold["id"]))
        assert detail["reason"] == "not-held"
        assert detail["message"] == "This hold has been cancelled."

    def test_tc_h54_an_event_that_moves_during_the_request_is_refused(
        self, client, staff, coordinator, event, event_repository, booking_repository,
        monkeypatch,
    ):
        hold = place(client, staff).json()
        real_request = booking_repository.request_hold

        def moved_first(booking_id, **kwargs):
            event_repository.events = [
                replace(item, status=EventStatus.CANCELLED) if item.id == EVENT_ID else item
                for item in event_repository.events
            ]
            return real_request(booking_id, **kwargs)

        monkeypatch.setattr(booking_repository, "request_hold", moved_first)
        detail = refused(to_request(client, coordinator, hold["id"]))
        assert detail["message"].startswith("This event changed while you were working on it.")
        assert booking_repository.bookings[0].status is BookingStatus.HELD

    def test_tc_h55_the_store_rechecks_the_hold_itself(
        self, client, staff, event, booking_repository, frozen_now
    ):
        hold = int(place(client, staff).json()["id"])
        frozen_now(datetime(2027, 10, 9, 9, 0))
        with pytest.raises(HoldExpired):
            booking_repository.request_hold(
                hold, actor_id=COORDINATOR_ID, expected_status=EventStatus.APPROVED
            )
        with pytest.raises(booking_store.StaleBookingStatus):
            booking_repository.request_hold(
                999, actor_id=COORDINATOR_ID, expected_status=EventStatus.APPROVED
            )
