"""Booking conflict detection — US15.1 and US15.2.

US15.1: availability is checked against the full time a venue is occupied,
setup and turnaround included, and against its unavailability periods.
US15.2: bookings that clash after a setup/turnaround change are flagged
"Conflict – review needed", never removed, and the flag clears once resolved.

Test case ids (TC-C… for US15.1, TC-F… for US15.2) match
`test_cases_us15_1_us15_2.md`; the classes follow the acceptance criteria in
order. Bookings are seeded straight into the store so each test controls
status, times and holds. "Now" is pinned to NOW.

Fixture venues: 1 Great Hall, 2 Bertha Room, 3 Seminar Room 4. The US15.1
classes give the Great Hall the customer's 30 minutes' setup and 45 minutes'
turnaround; the US15.2 classes start it at 0 and change it through the API.
Events 900 and 901 are Priya's (the fixture Coordinator); 902 belongs to
another Coordinator, so Priya must not see its title.
"""

import logging
from dataclasses import replace
from datetime import date, datetime

import pytest

from app import availability, booking_store, conflict_flags, notification_store
from app.availability import check_slot
from app.booking_store import (
    Booking,
    BookingStatus,
    ConflictFlag,
    SlotTaken,
    StaleBookingStatus,
    SupabaseBookings,
)
from app.event_store import StaleEventStatus
from app.venue_unavailability_store import Unavailability
from tests.conftest import COORDINATOR_ID, COORDINATOR_LEAD_ID, VENUE_STAFF_ID
from tests.test_venue_bookings import EVENT_ID, seed_event

NOW = datetime(2027, 10, 1, 9, 0)
OTHER_EVENT = 901
STRANGER_EVENT = 902
GREAT_HALL = 1
DAY = "2027-11-02"

HALL_FIELDS = {
    "name": "Great Hall",
    "location": "Main Campus, Building A",
    "capacity": 500,
    "facilities": "Stage, PA system, projector",
    "accessibilityFeatures": "Step-free access, hearing loop",
    "operatingHours": "08:00-22:00",
}


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    current = {"now": NOW}
    monkeypatch.setattr(booking_store, "local_now", lambda: current["now"])

    def move_to(moment: datetime) -> None:
        current["now"] = moment

    return move_to


@pytest.fixture
def buffered_hall(venue_repository):
    """The customer's example venue: 30 minutes' setup, 45 minutes' turnaround."""
    venue_repository.venues = [
        replace(v, setup_minutes=30, turnaround_minutes=45) if v.id == GREAT_HALL else v
        for v in venue_repository.venues
    ]


@pytest.fixture
def events(event_repository):
    seed_event(event_repository)
    seed_event(event_repository, event_id=OTHER_EVENT)
    stranger = seed_event(
        event_repository, event_id=STRANGER_EVENT, coordinator_id=COORDINATOR_LEAD_ID
    )
    event_repository.events[-1] = replace(stranger, title="Board Retreat")
    return event_repository


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def staff(auth_headers):
    return auth_headers("Venue Staff")


def at(clock: str) -> str:
    return f"{DAY}T{clock}"


def seed(
    booking_repository,
    booking_id: int,
    starts: str,
    ends: str,
    *,
    status: BookingStatus = BookingStatus.CONFIRMED,
    venue_id: int = GREAT_HALL,
    event_id: int = OTHER_EVENT,
    hold_expires_at: str = "",
    conflict: ConflictFlag | None = None,
) -> Booking:
    booking = Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=venue_id,
        venue_name={1: "Great Hall", 2: "Bertha Room", 3: "Seminar Room 4"}[venue_id],
        starts_at=at(starts),
        ends_at=at(ends),
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2027-09-01T09:00:00",
        headcount=30,
        hold_expires_at=hold_expires_at,
        conflict=conflict,
    )
    booking_repository.bookings.append(booking)
    return booking


def blackout(unavailability_repository, start: str, end: str, *, venue_id=GREAT_HALL, reason=""):
    return unavailability_repository.create(
        venue_id=venue_id,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        reason=reason,
        created_by_id=VENUE_STAFF_ID,
    )


def request(client, headers, starts="10:00", ends="12:00", *, venue=GREAT_HALL, event=EVENT_ID):
    return client.post(
        f"/events/{event}/bookings",
        json={"venueId": str(venue), "startsAt": at(starts), "endsAt": at(ends)},
        headers=headers,
    )


def not_available(response) -> dict:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "rule_refused"
    assert detail["reason"] == "not-available"
    return detail


def put_hall(client, headers, **fields):
    return client.put("/venues/1", json={**HALL_FIELDS, **fields}, headers=headers)


def conflict_notices(notification_repository) -> list:
    return [n for n in notification_repository.notifications if n.kind == "booking-conflict"]


# =================================================================================
# US15.1 AC1-AC2 — the effective occupied window
# =================================================================================


class TestTheOccupiedWindow:
    def test_tc_c01_the_customer_s_worked_example(self, venue_repository, buffered_hall):
        found = check_slot(
            venue_repository.get_venue(GREAT_HALL), at("10:00"), at("12:00"), bookings_at_venue=[]
        )
        assert (found.occupied_from, found.occupied_to) == (
            datetime(2027, 11, 2, 9, 30),
            datetime(2027, 11, 2, 12, 45),
        )
        assert found.available

    def test_tc_c02_without_a_venue_there_are_no_buffers(self):
        found = check_slot(None, at("10:00"), at("12:00"), bookings_at_venue=[])
        assert (found.occupied_from, found.occupied_to) == (
            datetime(2027, 11, 2, 10, 0),
            datetime(2027, 11, 2, 12, 0),
        )

    def test_tc_c02b_the_request_response_carries_the_window(
        self, client, coordinator, events, buffered_hall
    ):
        checked = client.post(
            f"/events/{EVENT_ID}/bookings/suitability",
            json={"venueId": "1", "startsAt": at("10:00"), "endsAt": at("12:00")},
            headers=coordinator,
        ).json()
        assert (checked["occupiedFrom"], checked["occupiedTo"]) == (at("09:30"), at("12:45"))


# =================================================================================
# US15.1 AC3 — blocked by another active booking's window at the same venue
# =================================================================================


class TestBlockedByAnotherBooking:
    @pytest.mark.parametrize(
        ("status", "expires"),
        [
            (BookingStatus.CONFIRMED, ""),
            (BookingStatus.REQUESTED, ""),
            (BookingStatus.HELD, "2027-10-08T17:00"),
        ],
        ids=["confirmed", "requested", "held"],
    )
    def test_tc_c03_held_requested_and_confirmed_count(
        self, client, coordinator, events, booking_repository, buffered_hall, status, expires
    ):
        seed(booking_repository, 10, "11:00", "13:00", status=status, hold_expires_at=expires)

        detail = not_available(request(client, coordinator))

        assert f", {status}) occupying" in detail["clashes"][0]
        assert len(booking_repository.bookings) == 1

    def test_tc_c04_an_expired_hold_does_not(
        self, client, coordinator, events, booking_repository, buffered_hall, frozen_now
    ):
        seed(booking_repository, 10, "11:00", "13:00", status=BookingStatus.HELD,
             hold_expires_at="2027-10-08T17:00")
        frozen_now(datetime(2027, 10, 8, 17, 0))

        assert request(client, coordinator).status_code == 201

    @pytest.mark.parametrize("status", [BookingStatus.CANCELLED, BookingStatus.REJECTED])
    def test_tc_c05_cancelled_and_rejected_do_not(
        self, client, coordinator, events, booking_repository, buffered_hall, status
    ):
        seed(booking_repository, 10, "11:00", "13:00", status=status)
        assert request(client, coordinator).status_code == 201

    def test_tc_c06_clashing_only_once_setup_and_turnaround_are_counted(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        # 08:00-09:00 is clear of 10:00-12:00, but its turnaround runs to 09:45
        # and this request's setup starts at 09:30.
        seed(booking_repository, 10, "08:00", "09:00")
        detail = not_available(request(client, coordinator))
        assert "2027-11-02 07:30 to 2027-11-02 09:45" in detail["clashes"][0]

    def test_tc_c07_the_same_slot_at_another_venue_is_free(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "10:00", "12:00", venue_id=3)
        assert request(client, coordinator).status_code == 201

    def test_tc_c08_the_event_s_own_booking_still_counts(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
             status=BookingStatus.REQUESTED)
        not_available(request(client, coordinator, "11:00", "13:00"))

    def test_tc_c09_a_booking_with_unreadable_times_is_left_out(self, booking_repository):
        broken = replace(
            seed(booking_repository, 10, "10:00", "12:00"), starts_at="not a time"
        )
        found = check_slot(None, at("10:00"), at("12:00"), bookings_at_venue=[broken])
        assert found.available

    def test_tc_c10_a_slot_taken_between_the_check_and_the_write(
        self, client, coordinator, events, booking_repository, buffered_hall, monkeypatch
    ):
        def raced(**_kwargs):
            seed(booking_repository, 77, "11:00", "12:00")
            raise SlotTaken

        monkeypatch.setattr(booking_repository, "create", raced)

        detail = not_available(request(client, coordinator))
        assert "booking #77" in detail["clashes"][0]

    def test_tc_c10b_a_race_whose_winner_is_gone_again_still_explains_itself(
        self, client, coordinator, events, booking_repository, buffered_hall, monkeypatch
    ):
        def raced(**_kwargs):
            raise SlotTaken

        monkeypatch.setattr(booking_repository, "create", raced)

        detail = not_available(request(client, coordinator))
        assert detail["clashes"] == ["a booking made a moment ago"]

    def test_tc_c10c_an_event_that_moved_meanwhile_is_still_a_stale_request(
        self, client, coordinator, events, booking_repository, buffered_hall, monkeypatch
    ):
        def moved(**_kwargs):
            raise StaleEventStatus

        monkeypatch.setattr(booking_repository, "create", moved)

        response = request(client, coordinator)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["reason"] != "not-available"

    def test_tc_c11_the_store_re_checks_under_its_lock(
        self, events, booking_repository, buffered_hall
    ):
        from app.event_status import EventStatus

        seed(booking_repository, 10, "11:00", "13:00")
        with pytest.raises(SlotTaken):
            booking_repository.create(
                event_id=EVENT_ID, venue_id=GREAT_HALL, starts_at=at("10:00"),
                ends_at=at("12:00"), requested_by_id=COORDINATOR_ID, headcount=30,
                expected_status=EventStatus.APPROVED,
            )


# =================================================================================
# US15.1 AC4 — blocked by a venue unavailability period (US12.1)
# =================================================================================


class TestBlockedByUnavailability:
    @pytest.fixture(autouse=True)
    def open_all_night(self, venue_repository, buffered_hall):
        """Midnight bookings below; the hall's 08:00-22:00 hours would refuse them (US18.1)."""
        venue_repository.venues = [
            replace(v, operating_hours="") if v.id == GREAT_HALL else v
            for v in venue_repository.venues
        ]

    def test_tc_c12_a_period_on_the_booking_s_day(
        self, client, coordinator, events, unavailability_repository, buffered_hall
    ):
        blackout(unavailability_repository, DAY, DAY, reason="Maintenance")

        detail = not_available(request(client, coordinator))

        assert detail["clashes"] == ["the venue's unavailable period 2027-11-02 (Maintenance)"]

    def test_tc_c13_setup_reaching_back_into_a_closed_day(
        self, client, coordinator, events, unavailability_repository, buffered_hall
    ):
        # Closed on the 1st; 00:15 on the 2nd needs setup from 23:45 on the 1st.
        blackout(unavailability_repository, "2027-11-01", "2027-11-01")
        detail = not_available(request(client, coordinator, "00:15", "02:00"))
        assert detail["clashes"] == ["the venue's unavailable period 2027-11-01"]

    def test_tc_c14_setup_starting_at_midnight_after_a_closed_day_is_allowed(
        self, client, coordinator, events, unavailability_repository, buffered_hall
    ):
        blackout(unavailability_repository, "2027-10-30", "2027-11-01")
        assert request(client, coordinator, "00:30", "02:00").status_code == 201

    def test_tc_c15_a_multi_day_period_is_named_by_both_dates(
        self, client, coordinator, events, unavailability_repository, buffered_hall
    ):
        blackout(unavailability_repository, "2027-11-01", "2027-11-03", reason="Closure")
        detail = not_available(request(client, coordinator))
        assert detail["clashes"] == [
            "the venue's unavailable period 2027-11-01 to 2027-11-03 (Closure)"
        ]

    def test_tc_c16_a_period_at_another_venue_does_not_count(
        self, client, coordinator, events, unavailability_repository, buffered_hall
    ):
        blackout(unavailability_repository, DAY, DAY, venue_id=3)
        assert request(client, coordinator).status_code == 201


# =================================================================================
# US15.1 AC5 — a blocked request says which booking or period it clashes with
# =================================================================================


class TestTheRefusalSaysWhatItClashesWith:
    def test_tc_c17_the_message_names_the_window_and_every_clash_in_order(
        self, client, coordinator, events, booking_repository, unavailability_repository,
        buffered_hall,
    ):
        seed(booking_repository, 11, "11:30", "12:30")
        seed(booking_repository, 10, "08:00", "09:15", status=BookingStatus.REQUESTED)
        blackout(unavailability_repository, DAY, DAY)

        detail = not_available(request(client, coordinator))

        assert (detail["occupiedFrom"], detail["occupiedTo"]) == (at("09:30"), at("12:45"))
        assert detail["clashes"] == [
            'booking #10 ("Faculty Welcome Night", Requested) occupying '
            "2027-11-02 07:30 to 2027-11-02 10:00",
            'booking #11 ("Faculty Welcome Night", Confirmed) occupying '
            "2027-11-02 11:00 to 2027-11-02 13:15",
            "the venue's unavailable period 2027-11-02",
        ]
        assert detail["message"].startswith(
            "Great Hall is not available for this booking. With setup and turnaround it "
            "would occupy 2027-11-02 09:30 to 2027-11-02 12:45, which overlaps booking #10"
        )
        assert detail["message"].endswith("; and the venue's unavailable period 2027-11-02.")

    def test_tc_c18_another_coordinator_s_event_is_not_named(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "11:00", "13:00", event_id=STRANGER_EVENT)

        detail = not_available(request(client, coordinator))

        assert detail["clashes"] == [
            "booking #10 (Confirmed) occupying 2027-11-02 10:30 to 2027-11-02 13:45"
        ]
        assert "Board Retreat" not in detail["message"]

    def test_tc_c19_venue_staff_placing_a_hold_see_the_other_event(
        self, client, staff, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "11:00", "13:00", event_id=STRANGER_EVENT,
             status=BookingStatus.REQUESTED)

        response = client.post(
            "/holds",
            json={"venueId": "1", "eventId": str(EVENT_ID), "startsAt": at("10:00"),
                  "endsAt": at("12:00"), "expiresAt": "2027-10-20T17:00"},
            headers=staff,
        )

        detail = not_available(response)
        assert detail["clashes"][0].startswith('booking #10 ("Board Retreat", Requested)')
        assert [b.id for b in booking_repository.bookings] == [10]

    def test_tc_c20_the_suitability_check_shows_it_before_requesting(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "11:00", "13:00")

        checked = client.post(
            f"/events/{EVENT_ID}/bookings/suitability",
            json={"venueId": "1", "startsAt": at("10:00"), "endsAt": at("12:00")},
            headers=coordinator,
        )

        assert checked.status_code == 200, checked.text
        body = checked.json()
        assert body["suitable"] is True
        assert body["available"] is False
        assert body["clashes"][0].startswith('booking #10 ("Faculty Welcome Night", Confirmed)')
        assert len(booking_repository.bookings) == 1


# =================================================================================
# US15.1 AC6 — windows that only touch are allowed
# =================================================================================


class TestTouchingWindows:
    def test_tc_c21_starting_as_the_other_s_turnaround_ends(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        # 10:00-12:00 occupies to 12:45; 13:15 with 30 minutes' setup starts at 12:45.
        seed(booking_repository, 10, "10:00", "12:00")
        assert request(client, coordinator, "13:15", "15:00").status_code == 201

    def test_tc_c22_one_minute_earlier_clashes(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        seed(booking_repository, 10, "10:00", "12:00")
        not_available(request(client, coordinator, "13:14", "15:00"))

    def test_tc_c23_ending_as_the_other_s_setup_starts(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        # 14:00 with setup starts at 13:30; 10:00-12:45 has turnaround to 13:30.
        seed(booking_repository, 10, "14:00", "16:00")
        assert request(client, coordinator, "10:00", "12:45").status_code == 201

    def test_tc_c24_touching_a_closed_day_at_midnight(self, unavailability_repository):
        entry = blackout(unavailability_repository, "2027-11-03", "2027-11-03")
        found = check_slot(
            None, at("22:00"), "2027-11-03T00:00", bookings_at_venue=[], unavailability=[entry]
        )
        assert found.available


# =================================================================================
# US15.1 across the other booking routes: holds and approval
# =================================================================================


class TestHoldsAndApproval:
    def test_tc_c25_a_hold_that_clashes_since_cannot_become_a_request(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        hold = seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
                    status=BookingStatus.HELD, hold_expires_at="2027-10-20T17:00")
        seed(booking_repository, 11, "12:30", "14:00")

        response = client.post(
            f"/events/{EVENT_ID}/bookings/{hold.id}/request", headers=coordinator
        )

        detail = not_available(response)
        assert detail["clashes"][0].startswith('booking #11 ("Faculty Welcome Night"')
        assert booking_repository.get_booking(10).status is BookingStatus.HELD

    def test_tc_c26_a_clear_hold_becomes_a_request(
        self, client, coordinator, events, booking_repository, buffered_hall
    ):
        hold = seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
                    status=BookingStatus.HELD, hold_expires_at="2027-10-20T17:00")
        response = client.post(
            f"/events/{EVENT_ID}/bookings/{hold.id}/request", headers=coordinator
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Requested"

    def test_tc_c27_approval_is_blocked_by_an_unavailability_period(
        self, client, staff, events, booking_repository, unavailability_repository,
        buffered_hall,
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
             status=BookingStatus.REQUESTED)
        blackout(unavailability_repository, DAY, DAY, reason="Flooded")

        [queued] = client.get("/booking-requests", headers=staff).json()
        response = client.post("/booking-requests/10/approve", headers=staff)

        assert queued["unavailable"] == [
            {"id": "101", "startDate": DAY, "endDate": DAY, "reason": "Flooded"}
        ]
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["reason"] == "slot-taken"
        assert detail["message"] == (
            "Great Hall is unavailable for this slot: the venue's unavailable period "
            "2027-11-02 (Flooded). Reject this request, or resolve the clash first."
        )
        assert detail["clashes"] == []
        assert booking_repository.get_booking(10).status is BookingStatus.REQUESTED

    def test_tc_c28_a_booking_and_a_period_are_both_named(
        self, client, staff, events, booking_repository, unavailability_repository,
        buffered_hall,
    ):
        seed(booking_repository, 9, "11:00", "13:00")
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
             status=BookingStatus.REQUESTED)
        blackout(unavailability_repository, DAY, DAY)

        detail = client.post("/booking-requests/10/approve", headers=staff).json()["detail"]

        assert detail["message"].startswith("Great Hall is already taken for this slot by ")
        assert "Great Hall is unavailable for this slot" in detail["message"]
        assert [c["bookingId"] for c in detail["clashes"]] == ["9"]
        assert len(detail["unavailable"]) == 1

    def test_tc_c29_the_store_s_approval_counts_periods_too(
        self, events, booking_repository, unavailability_repository, buffered_hall
    ):
        seed(booking_repository, 10, "10:00", "12:00", status=BookingStatus.REQUESTED)
        blackout(unavailability_repository, DAY, DAY)
        with pytest.raises(SlotTaken):
            booking_repository.approve(10, actor_id=VENUE_STAFF_ID)

    def test_tc_c30_approval_is_still_not_blocked_by_another_request(self, booking_repository):
        mine = seed(booking_repository, 10, "10:00", "12:00", status=BookingStatus.REQUESTED)
        theirs = seed(booking_repository, 11, "10:00", "12:00", status=BookingStatus.REQUESTED)
        assert availability.find_clashes(mine, None, [mine, theirs], now=NOW) == []
        assert availability.find_clashes(
            mine, None, [mine, theirs], now=NOW, counting_requests=True
        )[0].booking is theirs

    def test_tc_c31_a_booking_whose_own_times_cannot_be_read_clashes_with_nothing(
        self, booking_repository
    ):
        mine = replace(seed(booking_repository, 10, "10:00", "12:00"), ends_at="never")
        assert availability.find_clashes(mine, None, booking_repository.bookings, now=NOW) == []


# =================================================================================
# US15.2 AC1-AC2 — re-check on change; newly clashing bookings flagged, never removed
# =================================================================================


class TestFlaggingOnChange:
    def test_tc_f01_a_change_flags_both_sides_of_a_new_clash(
        self, client, staff, events, booking_repository, notification_repository
    ):
        # Clear at 0 minutes. With 30/45, 10:00-12:00 runs to 12:45 and
        # 12:30-14:00 starts at 12:00.
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", status=BookingStatus.REQUESTED)

        response = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        assert response.status_code == 200, response.text
        recheck = response.json()["recheck"]
        assert recheck["flaggedBookingIds"] == ["10", "11"]
        assert recheck["clearedBookingIds"] == []
        first, second = booking_repository.get_booking(10), booking_repository.get_booking(11)
        assert first.conflict.reason == (
            "With 30 minutes setup and 45 minutes turnaround it occupies 2027-11-02 09:30 "
            "to 2027-11-02 12:45, which overlaps booking #11 (Requested) occupying "
            "2027-11-02 12:00 to 2027-11-02 14:45."
        )
        assert first.conflict.flagged_at
        assert "booking #10 (Confirmed)" in second.conflict.reason

    def test_tc_f02_nothing_is_deleted_cancelled_or_moved(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", status=BookingStatus.REQUESTED)
        before = [(b.id, b.status, b.starts_at, b.ends_at) for b in booking_repository.bookings]

        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        assert [
            (b.id, b.status, b.starts_at, b.ends_at) for b in booking_repository.bookings
        ] == before

    def test_tc_f03_the_assigned_coordinator_is_notified(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", event_id=STRANGER_EVENT)

        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        notices = conflict_notices(notification_repository)
        assert {(n.user_id, n.event_id) for n in notices} == {
            (COORDINATOR_ID, EVENT_ID),
            (COORDINATOR_LEAD_ID, STRANGER_EVENT),
        }
        mine = next(n for n in notices if n.user_id == COORDINATOR_ID)
        assert mine.message.startswith(
            'The booking of Great Hall for "Faculty Welcome Night" needs attention: With 30'
        )
        # The reason names the other booking, never the other event.
        assert "Board Retreat" not in mine.message

    def test_tc_f04_only_active_bookings_at_this_venue_are_flagged(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", status=BookingStatus.CANCELLED)
        seed(booking_repository, 12, "12:30", "14:00", status=BookingStatus.REJECTED)
        seed(booking_repository, 13, "12:30", "14:00", status=BookingStatus.HELD,
             hold_expires_at="2027-09-30T17:00")
        seed(booking_repository, 14, "12:30", "14:00", venue_id=3)

        recheck = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45).json()["recheck"]

        assert recheck["flaggedBookingIds"] == []
        assert booking_repository.list_flagged() == []

    def test_tc_f05_bookings_that_have_finished_are_not_rechecked(
        self, client, staff, events, booking_repository, frozen_now
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", status=BookingStatus.REQUESTED)
        frozen_now(datetime(2027, 11, 3, 9, 0))

        recheck = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45).json()["recheck"]

        assert recheck["flaggedBookingIds"] == []

    def test_tc_f06_a_bigger_setup_pushing_into_a_closed_day_is_flagged(
        self, client, staff, events, booking_repository, unavailability_repository
    ):
        seed(booking_repository, 10, "00:30", "02:00", event_id=EVENT_ID)
        blackout(unavailability_repository, "2027-11-01", "2027-11-01", reason="Exams")

        recheck = put_hall(client, staff, setupMinutes=60).json()["recheck"]

        assert recheck["flaggedBookingIds"] == ["10"]
        assert recheck["conflicts"] == []  # US9.4's pairs: no other booking involved
        assert booking_repository.get_booking(10).conflict.reason.endswith(
            "which overlaps the venue's unavailable period 2027-11-01 (Exams)."
        )

    def test_tc_f07_an_already_flagged_booking_is_not_flagged_or_notified_again(
        self, client, staff, events, booking_repository, notification_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", status=BookingStatus.REQUESTED)
        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)
        first_flag = booking_repository.get_booking(10).conflict

        recheck = put_hall(client, staff, setupMinutes=40, turnaroundMinutes=45).json()["recheck"]

        assert recheck["flaggedBookingIds"] == []
        assert booking_repository.get_booking(10).conflict == first_flag
        assert len(conflict_notices(notification_repository)) == 2

    def test_tc_f08_no_setup_or_turnaround_change_no_flagging(
        self, client, staff, events, booking_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "10:00", "12:00", status=BookingStatus.REQUESTED)

        response = put_hall(client, staff, capacity=450)

        assert response.json()["recheck"] is None
        assert booking_repository.list_flagged() == []

    def test_tc_f09_a_booking_with_unreadable_times_is_skipped(
        self, client, staff, events, booking_repository
    ):
        booking_repository.bookings.append(
            replace(seed(booking_repository, 10, "10:00", "12:00"), id=12, starts_at="bad")
        )
        recheck = put_hall(client, staff, setupMinutes=30).json()["recheck"]
        assert recheck["flaggedBookingIds"] == []

    def test_tc_f10_a_booking_whose_event_is_gone_is_flagged_without_a_notice(
        self, client, staff, booking_repository, notification_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=999)
        seed(booking_repository, 11, "12:30", "14:00", event_id=999)

        recheck = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45).json()["recheck"]

        assert recheck["flaggedBookingIds"] == ["10", "11"]
        assert conflict_notices(notification_repository) == []

    def test_tc_f11_a_notice_that_cannot_be_written_does_not_undo_the_flag(
        self, client, staff, events, booking_repository, monkeypatch
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00")

        def broken(**_kwargs):
            raise RuntimeError("notifications table missing")

        monkeypatch.setattr(notification_store.repository(), "create_notice", broken)

        response = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        assert response.status_code == 200
        assert response.json()["recheck"]["flaggedBookingIds"] == ["10", "11"]

    def test_tc_f12_a_flagging_failure_does_not_fail_the_saved_change(
        self, client, staff, events, booking_repository, venue_repository, monkeypatch, caplog
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00")

        def broken(*_args, **_kwargs):
            raise RuntimeError("conflict columns missing")

        monkeypatch.setattr(booking_repository, "flag_conflict", broken)

        with caplog.at_level(logging.ERROR):
            response = put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        assert response.status_code == 200
        recheck = response.json()["recheck"]
        assert len(recheck["conflicts"]) == 1  # still identified by US9.4's re-check
        assert recheck["flaggedBookingIds"] == []
        assert venue_repository.get_venue(GREAT_HALL).buffers == (30, 45)
        assert "Could not flag the US15.2 booking conflicts at venue 1" in caplog.text


# =================================================================================
# US15.2 AC3 — Venue Staff see the flagged list; the Coordinator sees the flag
# =================================================================================


class TestTheFlaggedList:
    def flag_pair(self, client, staff, booking_repository):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID)
        seed(booking_repository, 11, "12:30", "14:00", event_id=STRANGER_EVENT,
             status=BookingStatus.REQUESTED)
        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

    def test_tc_f13_venue_staff_see_every_flagged_booking_soonest_first(
        self, client, staff, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)

        listed = client.get("/booking-conflicts", headers=staff)

        assert listed.status_code == 200, listed.text
        first, second = listed.json()
        assert (first["id"], second["id"]) == ("10", "11")
        assert first["label"] == "Conflict – review needed"
        assert first["conflict"]["label"] == "Conflict – review needed"
        assert first["conflict"]["reason"].startswith("With 30 minutes setup")
        assert first["eventTitle"] == "Faculty Welcome Night"
        assert first["coordinatorName"] == "Priya"
        assert (first["occupiedFrom"], first["occupiedTo"]) == (at("09:30"), at("12:45"))
        assert (first["setupMinutes"], first["turnaroundMinutes"]) == (30, 45)
        # Under US15.1's own rule, so the Requested booking counts, with its title.
        [clash] = first["clashes"]
        assert (clash["bookingId"], clash["eventTitle"], clash["status"]) == (
            "11", "Board Retreat", "Requested"
        )
        assert second["clashes"][0]["bookingId"] == "10"

    def test_tc_f14_an_empty_list(self, client, staff):
        assert client.get("/booking-conflicts", headers=staff).json() == []

    @pytest.mark.parametrize(
        "role",
        ["Event Organiser", "Event Coordinator", "Event Coordinator Lead", "Safety Officer",
         "Technical Support"],
    )
    def test_tc_f15_only_venue_staff(self, client, auth_headers, role):
        assert client.get("/booking-conflicts", headers=auth_headers(role)).status_code == 403

    def test_tc_f16_signed_out_is_refused(self, client):
        assert client.get("/booking-conflicts").status_code == 401

    def test_tc_f17_the_coordinator_sees_the_flag_on_the_event(
        self, client, staff, coordinator, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)

        [booking] = client.get(f"/events/{EVENT_ID}/bookings", headers=coordinator).json()

        assert booking["status"] == "Confirmed"
        assert booking["conflict"]["label"] == "Conflict – review needed"
        assert "booking #11 (Requested)" in booking["conflict"]["reason"]
        assert "Board Retreat" not in booking["conflict"]["reason"]
        assert booking["conflict"]["flaggedAt"]

    def test_tc_f18_the_booking_request_queue_shows_the_flag(
        self, client, staff, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)
        [queued] = client.get("/booking-requests", headers=staff).json()
        assert queued["id"] == "11"
        assert queued["conflict"]["label"] == "Conflict – review needed"


# =================================================================================
# US15.2 AC4 — the flag clears once the clash is resolved
# =================================================================================


class TestTheFlagClears:
    def flag_pair(self, client, staff, booking_repository, **second):
        seed(booking_repository, 10, "10:00", "12:00", event_id=EVENT_ID,
             status=BookingStatus.REQUESTED)
        seed(booking_repository, 11, "12:30", "14:00", **second)
        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)
        assert {b.id for b in booking_repository.list_flagged()} == {10, 11}

    def test_tc_f19_cancelling_one_side_clears_both(
        self, client, staff, coordinator, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)

        response = client.post(
            f"/events/{EVENT_ID}/bookings/10/cancel",
            json={"reason": "Moving to the Seminar Room"},
            headers=coordinator,
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"
        assert response.json()["conflict"] is None
        assert booking_repository.list_flagged() == []

    def test_tc_f20_rejecting_one_side_clears_both(
        self, client, staff, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)

        response = client.post(
            "/booking-requests/10/reject", json={"reason": "Clashes after the reset change"},
            headers=staff,
        )

        assert response.status_code == 200, response.text
        assert response.json()["conflict"] is None
        assert booking_repository.list_flagged() == []

    def test_tc_f20b_rejecting_a_booking_whose_event_is_gone_still_clears(
        self, client, staff, booking_repository, notification_repository
    ):
        seed(booking_repository, 10, "10:00", "12:00", event_id=999,
             status=BookingStatus.REQUESTED)
        seed(booking_repository, 11, "12:30", "14:00", event_id=999)
        put_hall(client, staff, setupMinutes=30, turnaroundMinutes=45)

        response = client.post(
            "/booking-requests/10/reject", json={"reason": "Event withdrawn"}, headers=staff
        )

        assert response.status_code == 200, response.text
        assert booking_repository.list_flagged() == []
        assert notification_repository.notifications == []

    def test_tc_f21_lowering_the_times_again_clears_them(
        self, client, staff, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)

        recheck = put_hall(client, staff, setupMinutes=0, turnaroundMinutes=0).json()["recheck"]

        assert recheck["clearedBookingIds"] == ["10", "11"]
        assert booking_repository.list_flagged() == []

    def test_tc_f22_an_expired_hold_clears_when_the_list_is_read(
        self, client, staff, events, booking_repository, frozen_now
    ):
        self.flag_pair(client, staff, booking_repository, status=BookingStatus.HELD,
                       hold_expires_at="2027-10-08T17:00")
        frozen_now(datetime(2027, 10, 8, 17, 0))

        assert client.get("/booking-conflicts", headers=staff).json() == []
        assert booking_repository.list_flagged() == []

    def test_tc_f23_the_flag_stays_while_the_clash_remains(
        self, client, staff, coordinator, events, booking_repository
    ):
        self.flag_pair(client, staff, booking_repository)
        seed(booking_repository, 12, "18:00", "19:00", event_id=EVENT_ID,
             status=BookingStatus.REQUESTED)

        client.post(
            f"/events/{EVENT_ID}/bookings/12/cancel", json={"reason": "Not needed"},
            headers=coordinator,
        )

        assert {b.id for b in booking_repository.list_flagged()} == {10, 11}

    def test_tc_f24_a_finished_booking_drops_its_flag(
        self, client, staff, events, booking_repository, frozen_now
    ):
        self.flag_pair(client, staff, booking_repository)
        frozen_now(datetime(2027, 11, 3, 9, 0))

        assert client.get("/booking-conflicts", headers=staff).json() == []

    def test_tc_f25_a_venue_that_is_gone_has_nothing_to_resolve(self):
        assert conflict_flags.resolve_venue(404) == conflict_flags.Review()

    def test_tc_f26_a_venue_with_no_flags_is_not_rechecked(
        self, booking_repository, venue_repository, unavailability_repository, monkeypatch
    ):
        seed(booking_repository, 10, "10:00", "12:00")

        def unexpected(_venue_id):
            raise AssertionError("no flags, so no blackouts to read")

        monkeypatch.setattr(unavailability_repository, "list_for_venue", unexpected)
        assert conflict_flags.resolve_venue(GREAT_HALL) == conflict_flags.Review()

    def test_tc_f27_a_clearing_failure_does_not_fail_the_cancellation(
        self, client, staff, coordinator, events, booking_repository, monkeypatch, caplog
    ):
        self.flag_pair(client, staff, booking_repository)

        def broken(*_args, **_kwargs):
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(booking_repository, "clear_conflict", broken)

        with caplog.at_level(logging.ERROR):
            response = client.post(
                f"/events/{EVENT_ID}/bookings/10/cancel", json={"reason": "Moving"},
                headers=coordinator,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"
        assert "Could not clear the US15.2 booking conflicts at venue 1" in caplog.text


# =================================================================================
# The rule's phrasing, on its own
# =================================================================================


class TestThePhrasing:
    def entry(self, start, end, reason=""):
        return Unavailability(
            id=1, venue_id=GREAT_HALL, start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end), reason=reason, created_by_id=None, created_at="",
        )

    def test_tc_f28_one_minute_is_singular(self, venue_repository):
        venue = replace(venue_repository.get_venue(GREAT_HALL), setup_minutes=1,
                        turnaround_minutes=0)
        found = check_slot(venue, at("10:00"), at("12:00"), bookings_at_venue=[],
                           unavailability=[self.entry(DAY, DAY)])
        assert conflict_flags.reason_for(found, venue).startswith(
            "With 1 minute setup and 0 minutes turnaround"
        )

    def test_tc_f29_a_period_without_a_reason(self):
        assert availability.describe_blackout(self.entry(DAY, DAY)) == (
            "the venue's unavailable period 2027-11-02"
        )

    def test_tc_f30_an_unnamed_venue_is_this_venue(self):
        found = check_slot(None, at("10:00"), at("12:00"), bookings_at_venue=[])
        assert availability.unavailable_message("", found, ["x"]).startswith(
            "This venue is not available"
        )


# =================================================================================
# The Supabase store's half of both stories
# =================================================================================


class FakeClient:
    """Records the query chain; answers reads with `rows` and RPCs with `answer`."""

    def __init__(self, rows=None, answer=None):
        self.calls: list[tuple] = []
        self.rows = rows if rows is not None else []
        self.answer = answer
        self._rpc = False

    def __getattr__(self, name):
        def record(*args, **_kwargs):
            self.calls.append((name, *args))
            if name == "rpc":
                self._rpc = True
            return self

        return record

    @property
    def not_(self):
        self.calls.append(("not_",))
        return self

    def execute(self):
        if self._rpc:
            self._rpc = False
            return type("R", (), {"data": self.answer})()
        return type("R", (), {"data": self.rows})()


ROW = {
    "id": 11, "event_id": EVENT_ID, "venue_id": 1, "start_at": at("10:00"),
    "end_at": at("12:00"), "status": "Confirmed", "created_at": "2027-09-01",
    "conflict_flagged_at": "2027-10-01T01:00:00", "conflict_reason": "Overlaps booking #12.",
}


class TestTheSupabaseStore:
    def use(self, monkeypatch, fake):
        monkeypatch.setattr(booking_store.supabase_client, "admin", lambda: fake)
        return SupabaseBookings()

    def test_tc_f31_every_read_selects_the_flag(self):
        assert "conflict_flagged_at, conflict_reason" in booking_store.COLUMNS

    def test_tc_f32_a_row_reads_its_flag_or_none(self):
        flagged = booking_store.to_booking(ROW)
        assert flagged.conflict == ConflictFlag(
            flagged_at="2027-10-01T01:00:00", reason="Overlaps booking #12."
        )
        clear = booking_store.to_booking({**ROW, "conflict_flagged_at": None})
        assert clear.conflict is None
        unexplained = booking_store.to_booking({**ROW, "conflict_reason": None})
        assert unexplained.conflict.reason == ""

    def test_tc_f33_flagging_writes_when_and_why_and_nothing_else(self, monkeypatch):
        fake = FakeClient(rows=[ROW])
        flagged = self.use(monkeypatch, fake).flag_conflict(11, reason="Overlaps booking #12.")
        [(_, changes)] = [call for call in fake.calls if call[0] == "update"]
        assert set(changes) == {"conflict_flagged_at", "conflict_reason"}
        assert changes["conflict_reason"] == "Overlaps booking #12."
        assert ("eq", "id", 11) in fake.calls
        assert flagged.status is BookingStatus.CONFIRMED

    def test_tc_f34_clearing_writes_both_back_to_null(self, monkeypatch):
        fake = FakeClient(rows=[{**ROW, "conflict_flagged_at": None}])
        cleared = self.use(monkeypatch, fake).clear_conflict(11)
        [(_, changes)] = [call for call in fake.calls if call[0] == "update"]
        assert changes == {"conflict_flagged_at": None, "conflict_reason": None}
        assert cleared.conflict is None

    @pytest.mark.parametrize("method", ["flag", "clear"])
    def test_tc_f35_a_booking_that_is_gone_is_stale(self, monkeypatch, method):
        store = self.use(monkeypatch, FakeClient(rows=[]))
        with pytest.raises(StaleBookingStatus):
            if method == "flag":
                store.flag_conflict(11, reason="x")
            else:
                store.clear_conflict(11)

    def test_tc_f36_the_flagged_list_reads_flagged_rows_soonest_first(self, monkeypatch):
        fake = FakeClient(rows=[ROW])
        [booking] = self.use(monkeypatch, fake).list_flagged()
        assert ("not_",) in fake.calls
        assert ("is_", "conflict_flagged_at", "null") in fake.calls
        assert fake.calls.index(("order", "start_at")) < fake.calls.index(("order", "id"))
        assert booking.conflict is not None

    def test_tc_f36b_no_rows_is_an_empty_list(self, monkeypatch):
        fake = FakeClient(rows=None)
        fake.rows = None
        assert self.use(monkeypatch, fake).list_flagged() == []

    def test_tc_c32_a_taken_slot_from_the_request_rpc_is_slot_taken(self, monkeypatch):
        from app.event_status import EventStatus

        store = self.use(monkeypatch, FakeClient(rows=[ROW], answer=booking_store.RPC_CLASH))
        with pytest.raises(SlotTaken):
            store.create(event_id=EVENT_ID, venue_id=1, starts_at=at("10:00"),
                         ends_at=at("12:00"), requested_by_id=COORDINATOR_ID, headcount=30,
                         expected_status=EventStatus.APPROVED)

    def test_tc_c33_a_stale_event_is_still_its_own_answer(self, monkeypatch):
        from app.event_status import EventStatus

        store = self.use(monkeypatch, FakeClient(rows=[ROW], answer=None))
        with pytest.raises(StaleEventStatus):
            store.create(event_id=EVENT_ID, venue_id=1, starts_at=at("10:00"),
                         ends_at=at("12:00"), requested_by_id=COORDINATOR_ID, headcount=30,
                         expected_status=EventStatus.APPROVED)


class TestTheInMemoryStore:
    def test_tc_f37_flag_and_clear_keep_the_status(self, booking_repository):
        seed(booking_repository, 10, "10:00", "12:00", status=BookingStatus.HELD,
             hold_expires_at="2027-10-08T17:00")
        flagged = booking_repository.flag_conflict(10, reason="Overlaps.")
        assert flagged.status is BookingStatus.HELD
        assert flagged.conflict.reason == "Overlaps."
        assert booking_repository.clear_conflict(10).conflict is None

    def test_tc_f38_a_missing_booking_is_stale(self, booking_repository):
        with pytest.raises(StaleBookingStatus):
            booking_repository.flag_conflict(5, reason="x")
