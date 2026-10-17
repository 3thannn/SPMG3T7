"""Venue suitability per booking, through the routes — US18.1.

The rule itself is tested in test_suitability.py. These tests follow the
acceptance criteria: each booking has its own headcount, defaulting to the
event's attendance; picking a venue shows Suitable or Not suitable with the
reasons; and a venue that is not suitable cannot be requested.

Fixture venues (see conftest): 1 Great Hall holds 500, open 08:00-22:00, with a
stage, PA system and projector, step-free access and a hearing loop. 2 Bertha
Room holds 40 and has nothing else recorded. 3 Seminar Room 4 holds 60, open
07:30-19:00, with a boardroom table and screen, and step-free access.
"""

from dataclasses import replace

import pytest

from app.event_status import EventStatus
from app.events import NEED_MAX, NEEDS_MAX
from tests.test_venue_bookings import (
    BERTHA_ROOM,
    BOOKING,
    EVENT_ID,
    GREAT_HALL,
    SEMINAR_ROOM,
    request,
    seed_event,
)


def check(client, headers, event_id: int = EVENT_ID, **overrides):
    """POST to the suitability check with overrides; `None` drops the field."""
    body = {**BOOKING, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(f"/events/{event_id}/bookings/suitability", json=body, headers=headers)


def verdict(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def event(event_repository):
    """An Approved event for 30 people, assigned to the fixture Coordinator."""
    return seed_event(event_repository)


@pytest.fixture
def big_event(event_repository):
    """The Week 7 case: a 300-person event that also wants breakout rooms."""
    return seed_event(event_repository, expected_attendance=300)


@pytest.fixture
def layouts(venue_repository):
    """Give the Great Hall the layouts the fixture leaves unrecorded."""
    venue_repository.venues = [
        replace(v, supported_layouts="Theatre, cabaret") if v.id == 1 else v
        for v in venue_repository.venues
    ]


class TestShownWhenAVenueIsPicked:
    """AC2: Suitable or Not suitable, with the reasons."""

    def test_a_suitable_venue(self, client, coordinator, event):
        body = verdict(check(client, coordinator))

        assert body == {
            "venueId": GREAT_HALL,
            "suitable": True,
            "reasons": [],
            "notes": [],
            # US15.1: the slot is free too, and this is the window it would occupy.
            "available": True,
            "clashes": [],
            "occupiedFrom": "2027-11-02T09:00",
            "occupiedTo": "2027-11-02T17:00",
        }

    def test_a_venue_that_is_not_suitable_says_why(self, client, coordinator, event):
        body = verdict(check(client, coordinator, venueId=BERTHA_ROOM, headcount=41))

        assert body["suitable"] is False
        assert body["reasons"] == ["It holds 40 people, and this booking is for 41."]

    def test_what_could_not_be_checked_is_noted(self, client, coordinator, event):
        """Bertha Room has no hours recorded, so the time is noted, not refused."""
        body = verdict(check(client, coordinator, venueId=BERTHA_ROOM))

        assert body["suitable"] is True
        assert body["notes"] == [
            "Its operating hours are not recorded, so the booking time was not checked."
        ]

    def test_headcount_equal_to_capacity_is_suitable(self, client, coordinator, event):
        assert verdict(check(client, coordinator, venueId=SEMINAR_ROOM, headcount=60))[
            "suitable"
        ]

    def test_headcount_one_over_capacity_is_not_suitable(self, client, coordinator, event):
        body = verdict(check(client, coordinator, venueId=SEMINAR_ROOM, headcount=61))

        assert body["suitable"] is False
        assert body["reasons"] == ["It holds 60 people, and this booking is for 61."]

    def test_a_layout_it_does_not_support(self, client, coordinator, event, layouts):
        body = verdict(check(client, coordinator, layout="Classroom"))

        assert body["reasons"] == [
            "It does not support the Classroom layout. It supports: Theatre, cabaret."
        ]

    def test_a_layout_it_supports(self, client, coordinator, event, layouts):
        assert verdict(check(client, coordinator, layout="theatre"))["suitable"]

    def test_a_missing_facility_and_accessibility_need(self, client, coordinator, event):
        body = verdict(
            check(
                client,
                coordinator,
                venueId=SEMINAR_ROOM,
                facilities=["screen", "projector"],
                accessibilityNeeds=["step-free access", "hearing loop"],
            )
        )

        assert body["reasons"] == [
            "It does not list projector among its facilities.",
            "It does not list hearing loop among its accessibility features.",
        ]

    def test_a_time_outside_its_hours(self, client, coordinator, event):
        body = verdict(
            check(
                client,
                coordinator,
                venueId=SEMINAR_ROOM,
                startsAt="2027-11-02T18:00",
                endsAt="2027-11-02T20:00",
            )
        )

        assert body["reasons"] == [
            "The booking falls outside its operating hours (07:30-19:00)."
        ]

    def test_checking_stores_nothing(self, client, coordinator, event, booking_repository):
        check(client, coordinator)
        check(client, coordinator, venueId=BERTHA_ROOM, headcount=41)

        assert booking_repository.bookings == []


class TestEachBookingHasItsOwnHeadcount:
    """AC1: per booking, defaulting to the event's expected attendance."""

    def test_left_out_it_is_the_events_attendance(self, client, coordinator, big_event):
        response = request(client, coordinator)

        assert response.status_code == 201, response.text
        assert response.json()["headcount"] == 300

    def test_a_booking_can_give_its_own(self, client, coordinator, big_event, booking_repository):
        response = request(client, coordinator, headcount=120)

        assert response.json()["headcount"] == 120
        assert booking_repository.bookings[0].headcount == 120

    def test_a_breakout_room_is_not_checked_against_the_whole_event(
        self, client, coordinator, big_event
    ):
        """Week 7 #3: 300 at the event, 40 in the breakout room that holds 60."""
        hall = request(client, coordinator, venueId=GREAT_HALL)
        breakout = request(
            client,
            coordinator,
            venueId=SEMINAR_ROOM,
            startsAt="2027-11-02T13:00",
            endsAt="2027-11-02T15:00",
            headcount=40,
        )

        assert hall.status_code == 201, hall.text
        assert breakout.status_code == 201, breakout.text
        assert [hall.json()["headcount"], breakout.json()["headcount"]] == [300, 40]

    def test_the_check_uses_the_same_default(self, client, coordinator, big_event):
        body = verdict(check(client, coordinator, venueId=SEMINAR_ROOM))

        assert body["reasons"] == ["It holds 60 people, and this booking is for 300."]

    def test_an_event_with_no_attendance_needs_a_headcount_given(
        self, client, coordinator, event_repository
    ):
        seed_event(event_repository, expected_attendance=None)

        response = request(client, coordinator)

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Give the headcount for this booking. The event has no expected attendance "
            "to start from."
        )
        assert request(client, coordinator, headcount=20).status_code == 201

    def test_a_blank_headcount_is_left_out(self, client, coordinator, big_event):
        assert request(client, coordinator, headcount="  ").json()["headcount"] == 300

    def test_a_headcount_sent_as_text_is_read(self, client, coordinator, event):
        assert request(client, coordinator, headcount=" 25 ").json()["headcount"] == 25

    @pytest.mark.parametrize(
        ("headcount", "message"),
        [
            (0, "The headcount must be at least 1."),
            (-5, "Give the headcount as a whole number of people."),
            ("abc", "Give the headcount as a whole number of people."),
            ("1.5", "Give the headcount as a whole number of people."),
            (2_147_483_648, "That headcount is larger than any venue this system can hold."),
        ],
    )
    def test_a_headcount_that_is_not_a_count_of_people(
        self, client, coordinator, event, booking_repository, headcount, message
    ):
        response = request(client, coordinator, headcount=headcount)

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_booking"
        assert detail["message"] == message
        assert booking_repository.bookings == []


class TestANotSuitableVenueCannotBeRequested:
    """AC4: refused with every reason, and nothing stored."""

    def test_one_over_capacity_is_refused(self, client, coordinator, event, booking_repository):
        response = request(client, coordinator, venueId=SEMINAR_ROOM, headcount=61)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "rule_refused"
        assert detail["reason"] == "not-suitable"
        assert detail["reasons"] == ["It holds 60 people, and this booking is for 61."]
        assert detail["message"].startswith("Seminar Room 4 is not suitable for this booking.")
        assert booking_repository.bookings == []

    def test_exactly_at_capacity_is_requested(self, client, coordinator, event):
        assert request(client, coordinator, venueId=SEMINAR_ROOM, headcount=60).status_code == 201

    def test_outside_its_hours_is_refused(self, client, coordinator, event):
        response = request(client, coordinator, startsAt="2027-11-02T06:00")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-suitable"

    def test_the_refusal_gives_the_same_reasons_the_check_showed(
        self, client, coordinator, event, layouts
    ):
        needs = {
            "venueId": SEMINAR_ROOM,
            "headcount": 80,
            "layout": "Theatre",
            "facilities": ["projector"],
            "accessibilityNeeds": ["lift"],
            "startsAt": "2027-11-02T19:00",
            "endsAt": "2027-11-02T21:00",
        }

        shown = verdict(check(client, coordinator, **needs))["reasons"]
        refused = request(client, coordinator, **needs).json()["detail"]["reasons"]

        assert len(shown) == 5
        assert refused == shown

    def test_an_unsuitable_venue_does_not_block_another(self, client, coordinator, big_event):
        """US14.1 AC3, now that suitability is one of the per-booking checks."""
        refused = request(client, coordinator, venueId=BERTHA_ROOM)
        hall = request(client, coordinator, venueId=GREAT_HALL)

        assert refused.status_code == 409
        assert hall.status_code == 201, hall.text


class TestWhatABookingNeedsIsKept:
    def test_layout_facilities_and_accessibility_are_stored_and_returned(
        self, client, coordinator, event, layouts, booking_repository
    ):
        body = request(
            client,
            coordinator,
            layout=" Theatre ",
            facilities=["projector", " PA  system "],
            accessibilityNeeds=["hearing loop"],
        ).json()

        assert body["requiredLayout"] == "Theatre"
        assert body["requiredFacilities"] == ["projector", "PA system"]
        assert body["accessibilityNeeds"] == ["hearing loop"]
        [stored] = booking_repository.bookings
        assert stored.required_facilities == ("projector", "PA system")

    def test_no_needs_is_an_empty_layout_and_empty_lists(self, client, coordinator, event):
        body = request(client, coordinator).json()

        assert body["requiredLayout"] == ""
        assert body["requiredFacilities"] == []
        assert body["accessibilityNeeds"] == []

    def test_a_comma_separated_string_is_read_as_a_list(self, client, coordinator, event):
        body = request(client, coordinator, facilities="projector, stage,, ").json()

        assert body["requiredFacilities"] == ["projector", "stage"]

    def test_a_need_named_twice_is_kept_once(self, client, coordinator, event):
        body = request(client, coordinator, facilities=["Projector", "projector"]).json()

        assert body["requiredFacilities"] == ["Projector"]

    def test_an_overlong_need_is_refused(self, client, coordinator, event):
        response = request(client, coordinator, facilities=["x" * (NEED_MAX + 1)])

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            f"Keep each facility to {NEED_MAX} characters or fewer."
        )

    def test_an_overlong_layout_is_refused(self, client, coordinator, event):
        response = request(client, coordinator, layout="x" * (NEED_MAX + 1))

        assert response.status_code == 400

    def test_too_many_needs_are_refused(self, client, coordinator, event):
        response = request(
            client, coordinator, accessibilityNeeds=[f"need {n}" for n in range(NEEDS_MAX + 1)]
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            f"List at most {NEEDS_MAX} accessibility needs."
        )


class TestTheCheckIsRefusedLikeARequest:
    def test_the_owning_organiser_cannot_check(self, client, auth_headers, event):
        assert check(client, auth_headers("Event Organiser")).status_code == 403

    def test_venue_staff_cannot_check(self, client, auth_headers, event):
        assert check(client, auth_headers("Venue Staff")).status_code == 403

    def test_a_coordinator_not_assigned_cannot_check(self, client, coordinator, event_repository):
        seed_event(event_repository, coordinator_id=99)

        assert check(client, coordinator).status_code == 404

    def test_a_closed_event_cannot_be_checked(self, client, coordinator, event_repository):
        seed_event(event_repository, status=EventStatus.REJECTED)

        response = check(client, coordinator)

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-closed"

    def test_a_past_start_is_refused_before_any_verdict(self, client, coordinator, event):
        response = check(
            client, coordinator, startsAt="2020-01-01T09:00", endsAt="2020-01-01T17:00"
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "A booking cannot start in the past."

    def test_a_venue_not_in_the_catalogue(self, client, coordinator, event):
        response = check(client, coordinator, venueId="999")

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "That venue is not in the catalogue."

    def test_signed_out(self, client, event):
        response = client.post(f"/events/{EVENT_ID}/bookings/suitability", json=BOOKING)

        assert response.status_code == 401
