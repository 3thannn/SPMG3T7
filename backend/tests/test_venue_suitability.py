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

from tests.test_venue_bookings import (
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



    def test_headcount_equal_to_capacity_is_suitable(self, client, coordinator, event):
        assert verdict(check(client, coordinator, venueId=SEMINAR_ROOM, headcount=60))[
            "suitable"
        ]

    def test_headcount_one_over_capacity_is_not_suitable(self, client, coordinator, event):
        body = verdict(check(client, coordinator, venueId=SEMINAR_ROOM, headcount=61))

        assert body["suitable"] is False
        assert body["reasons"] == ["It holds 60 people, and this booking is for 61."]







class TestEachBookingHasItsOwnHeadcount:
    """AC1: per booking, defaulting to the event's expected attendance."""

    def test_left_out_it_is_the_events_attendance(self, client, coordinator, big_event):
        response = request(client, coordinator)

        assert response.status_code == 201, response.text
        assert response.json()["headcount"] == 300


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





