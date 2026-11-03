"""US9.3 follow-up: the catalogue filters the brief asks for beyond capacity,
location and accessibility — supported layout, required facilities, and a time.

The time filter leaves out every venue a booking request for that time would be
refused at (US15.1's own rule, setup and turnaround included), so the catalogue
never offers a venue the booking form would then turn down.
"""

from dataclasses import replace

import pytest

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






class TestTime:

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







