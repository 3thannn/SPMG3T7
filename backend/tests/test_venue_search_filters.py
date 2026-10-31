"""US9.3 follow-up: the catalogue filters the brief asks for beyond capacity,
location and accessibility — supported layout, required facilities, and a time.

The time filter leaves out every venue a booking request for that time would be
refused at (US15.1's own rule, setup and turnaround included), so the catalogue
never offers a venue the booking form would then turn down.
"""

from dataclasses import replace
from datetime import date

import pytest

from app.venue_store import SupabaseVenues, VenueFilters
from app.venue_unavailability_store import UnavailabilityReasonType
from tests.test_change_review_us11_2 import booking

COORDINATOR = "Event Coordinator"


def search(client, auth_headers, **params) -> list[str]:
    response = client.get("/venues", params=params, headers=auth_headers(COORDINATOR))
    assert response.status_code == 200, response.text
    return [venue["name"] for venue in response.json()]


def refused(client, auth_headers, **params) -> str:
    response = client.get("/venues", params=params, headers=auth_headers(COORDINATOR))
    assert response.status_code == 400, response.text
    return response.json()["detail"]["message"]


@pytest.fixture
def layouts(venue_repository):
    """Great Hall seats theatre and banquet; Seminar Room 4 is a boardroom."""
    venue_repository.venues = [
        replace(venue, supported_layouts={1: "Theatre, Banquet", 3: "Boardroom"}.get(venue.id, ""))
        for venue in venue_repository.venues
    ]


class TestLayout:
    def test_only_venues_that_take_the_layout(self, client, auth_headers, layouts):
        assert search(client, auth_headers, layout="theatre") == ["Great Hall"]

    def test_a_layout_no_venue_takes_finds_none(self, client, auth_headers, layouts):
        assert search(client, auth_headers, layout="Cabaret") == []


class TestFacilities:
    def test_every_listed_facility_must_be_there(self, client, auth_headers):
        assert search(client, auth_headers, facilities="stage, projector") == ["Great Hall"]

    def test_one_missing_facility_rules_a_venue_out(self, client, auth_headers):
        assert search(client, auth_headers, facilities="stage, screen") == []

    def test_blank_entries_between_commas_are_ignored(self, client, auth_headers):
        assert search(client, auth_headers, facilities=" screen, , ") == ["Seminar Room 4"]

    def test_combined_with_the_other_filters(self, client, auth_headers, layouts):
        found = search(
            client, auth_headers, facilities="Stage", layout="Banquet", minCapacity="400"
        )

        assert found == ["Great Hall"]

    def test_a_filter_too_long_to_be_real_is_refused(self, client, auth_headers):
        message = refused(client, auth_headers, facilities="x" * 201)

        assert message == "Keep the facilities filter to 200 characters or fewer."


class TestTime:
    def test_a_venue_booked_then_is_left_out(self, client, auth_headers, booking_repository):
        booking_repository.bookings = [booking(900, venue_id=1, venue_name="Great Hall")]

        found = search(client, auth_headers, startsAt="2027-11-02T19:00", endsAt="2027-11-02T20:00")

        assert "Great Hall" not in found
        assert {"Bertha Room", "Seminar Room 4"} <= set(found)

    def test_setup_and_turnaround_count_as_taken(
        self, client, auth_headers, booking_repository, venue_repository
    ):
        """18:00-21:00 with an hour's turnaround keeps the hall until 22:00."""
        venue_repository.venues = [
            replace(venue, turnaround_minutes=60) if venue.id == 1 else venue
            for venue in venue_repository.venues
        ]
        booking_repository.bookings = [booking(900, venue_id=1, venue_name="Great Hall")]

        during_turnaround = search(
            client, auth_headers, startsAt="2027-11-02T21:30", endsAt="2027-11-02T22:00"
        )
        after_it = search(
            client, auth_headers, startsAt="2027-11-02T22:00", endsAt="2027-11-02T23:00"
        )

        assert "Great Hall" not in during_turnaround
        assert "Great Hall" in after_it

    def test_a_cancelled_booking_does_not_count(self, client, auth_headers, booking_repository):
        booking_repository.bookings = [
            booking(900, venue_id=1, venue_name="Great Hall", status="Cancelled")
        ]

        found = search(client, auth_headers, startsAt="2027-11-02T19:00", endsAt="2027-11-02T20:00")

        assert "Great Hall" in found

    def test_a_venue_closed_that_day_is_left_out(
        self, client, auth_headers, unavailability_repository
    ):
        unavailability_repository.create(
            venue_id=3,
            start_date=date(2027, 11, 2),
            end_date=date(2027, 11, 2),
            reason_type=UnavailabilityReasonType.MAINTENANCE,
            other_reason="",
            created_by_id=4,
        )

        found = search(client, auth_headers, startsAt="2027-11-02T09:00", endsAt="2027-11-02T10:00")

        assert "Seminar Room 4" not in found

    @pytest.mark.parametrize(
        ("params", "message"),
        [
            (
                {"startsAt": "2027-11-02T19:00"},
                "Give both a start and an end time to find the venues free then.",
            ),
            (
                {"endsAt": "2027-11-02T19:00"},
                "Give both a start and an end time to find the venues free then.",
            ),
            (
                {"startsAt": "tomorrow", "endsAt": "2027-11-02T19:00"},
                "Give the start time as a date and time, such as 2027-03-03T09:30.",
            ),
            (
                {"startsAt": "2027-11-02T19:00", "endsAt": "2027-02-30T10:00"},
                "The end time 2027-02-30T10:00 is not a real date and time.",
            ),
            (
                {"startsAt": "2027-11-02T19:00", "endsAt": "2027-11-02T19:00"},
                "The end time must be after the start time.",
            ),
        ],
        ids=["start-only", "end-only", "not-a-time", "not-a-real-day", "not-after"],
    )
    def test_a_time_it_cannot_read_is_refused(self, client, auth_headers, params, message):
        assert refused(client, auth_headers, **params) == message


class TestTheDatabaseQuery:
    def test_layout_and_each_facility_are_separate_conditions(self, fake):
        SupabaseVenues().list_venues(VenueFilters(layout="theatre", facilities=("Stage", "PA")))

        conditions = fake.on("venues")[0].named("ilike")
        assert ("ilike", "supported_layouts", "%theatre%") in conditions
        assert ("ilike", "facilities", "%Stage%") in conditions
        assert ("ilike", "facilities", "%PA%") in conditions


@pytest.mark.parametrize(
    "filters",
    [VenueFilters(layout="Theatre"), VenueFilters(facilities=("Stage",))],
    ids=["layout", "facilities"],
)
def test_each_new_filter_counts_as_applied(filters):
    assert filters.applied
