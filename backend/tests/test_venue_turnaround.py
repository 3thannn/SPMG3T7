"""US9.4 — Venue Staff set a setup time and turnaround time for each venue.

Acceptance criteria:

AC1  Two fields per venue: setup time and turnaround time, in minutes, whole
     number >= 0, default 0.
AC2  Settable on create and edit, Venue Staff only.
AC3  Shown on the venue detail view for Coordinators (US9.2).
AC4  Changing either value kicks off the re-check in US15.2: existing bookings
     that become problematic are identified rather than silently removed.

The worked example from the requirement: 10:00-12:00 with 30 minutes' setup and
45 minutes' turnaround occupies the venue from 09:30 to 12:45.
"""


import pytest

from app.booking_store import Booking, BookingStatus
from app.venue_turnaround import (
    MINUTES_MAX,
)

STAFF = "Venue Staff"
COORDINATOR = "Event Coordinator"
ORGANISER = "Event Organiser"

NEW_VENUE = {
    "name": "Atrium",
    "location": "Science Quarter",
    "capacity": 90,
}

WHOLE_NUMBER = "Give the {label} as a whole number of minutes, 0 or more."


def booking(
    booking_id: int,
    starts_at: str,
    ends_at: str,
    *,
    venue_id: int = 1,
    event_id: int | None = None,
    status: BookingStatus = BookingStatus.REQUESTED,
) -> Booking:
    return Booking(
        id=booking_id,
        event_id=event_id if event_id is not None else 900 + booking_id,
        venue_id=venue_id,
        venue_name="Great Hall",
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        requested_by_id=2,
        requested_at="2026-10-01T09:00:00",
    )


def create(client, headers, **fields) -> dict:
    response = client.post("/venues", json={**NEW_VENUE, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def put(client, headers, venue_id: str, **fields):
    return client.put(f"/venues/{venue_id}", json={**NEW_VENUE, **fields}, headers=headers)


# =================================================================================
# AC1 — whole minutes, >= 0, default 0 (the rule, as a plain function)
# =================================================================================




# =================================================================================
# The occupied window and conflicts
# =================================================================================








# =================================================================================
# The stores
# =================================================================================






# =================================================================================
# AC1 + AC2 through the routes
# =================================================================================


class TestCreating:
    def test_both_default_to_0(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF))

        assert (venue["setupMinutes"], venue["turnaroundMinutes"]) == (0, 0)


    @pytest.mark.parametrize(
        ("sent", "stored"),
        [(None, 0), ("", 0), ("15", 15), (0, 0), (MINUTES_MAX, MINUTES_MAX), (20.0, 20)],
    )
    def test_accepted_values(self, client, auth_headers, sent, stored):
        venue = create(client, auth_headers(STAFF), setupMinutes=sent, turnaroundMinutes=sent)

        assert (venue["setupMinutes"], venue["turnaroundMinutes"]) == (stored, stored)

    @pytest.mark.parametrize(
        ("field", "sent", "message"),
        [
            ("setupMinutes", -1, "The setup time cannot be negative."),
            ("turnaroundMinutes", -5, "The turnaround time cannot be negative."),
            ("setupMinutes", 1.5, WHOLE_NUMBER.format(label="setup time")),
            ("turnaroundMinutes", "abc", WHOLE_NUMBER.format(label="turnaround time")),
            ("setupMinutes", True, WHOLE_NUMBER.format(label="setup time")),
            (
                "setupMinutes",
                MINUTES_MAX + 1,
                "Keep the setup time to 1440 minutes (24 hours) or fewer.",
            ),
            (
                "turnaroundMinutes",
                MINUTES_MAX + 1,
                "Keep the turnaround time to 1440 minutes (24 hours) or fewer.",
            ),
        ],
    )
    def test_refused_values_name_the_field(
        self, client, auth_headers, venue_repository, field, sent, message
    ):
        before = len(venue_repository.venues)

        response = client.post(
            "/venues", json={**NEW_VENUE, field: sent}, headers=auth_headers(STAFF)
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {"code": "invalid_venue", "message": message}
        assert len(venue_repository.venues) == before



class TestEditing:



    @pytest.mark.parametrize("role", [COORDINATOR, ORGANISER, "Safety Officer"])
    def test_only_venue_staff_may_edit(self, client, auth_headers, role):
        response = put(client, auth_headers(role), "1", setupMinutes=30)

        assert response.status_code == 403



# =================================================================================
# AC3 — shown on the venue detail view for Coordinators
# =================================================================================


class TestCoordinatorsSeeThem:
    def test_on_the_detail_view(self, client, auth_headers):
        venue = create(client, auth_headers(STAFF), setupMinutes=30, turnaroundMinutes=45)

        response = client.get(f"/venues/{venue['id']}", headers=auth_headers(COORDINATOR))

        assert response.status_code == 200
        assert (response.json()["setupMinutes"], response.json()["turnaroundMinutes"]) == (30, 45)



# =================================================================================
# AC4 — changing either value kicks off the re-check; problems are identified
# =================================================================================

GREAT_HALL = {
    "name": "Great Hall",
    "location": "Main Campus, Building A",
    "capacity": 500,
    "facilities": "Stage, PA system, projector",
    "accessibilityFeatures": "Step-free access, hearing loop",
    "operatingHours": "08:00-22:00",
}


@pytest.fixture
def hall_bookings(booking_repository):
    """Two clear bookings at the Great Hall (venue 1), one cancelled, one elsewhere."""
    booking_repository.bookings.extend(
        [
            booking(1, "2027-03-01T10:00", "2027-03-01T12:00"),
            booking(2, "2027-03-01T12:30", "2027-03-01T14:00"),
            booking(3, "2027-03-01T11:00", "2027-03-01T13:00", status=BookingStatus.CANCELLED),
            booking(4, "2027-03-01T10:00", "2027-03-01T12:00", venue_id=2),
        ]
    )
    return booking_repository


def put_hall(client, auth_headers, **fields):
    return client.put("/venues/1", json={**GREAT_HALL, **fields}, headers=auth_headers(STAFF))


class TestRecheckOnChange:

    @pytest.mark.parametrize(
        "change", [{"setupMinutes": 45}, {"turnaroundMinutes": 45}], ids=["setup", "turnaround"]
    )
    def test_changing_either_value_rechecks_and_identifies_the_clash(
        self, client, auth_headers, hall_bookings, change
    ):
        response = put_hall(client, auth_headers, **change)

        assert response.status_code == 200, response.text
        result = response.json()["recheck"]
        assert result["checkedBookings"] == 2
        assert len(result["conflicts"]) == 1
        conflict = result["conflicts"][0]
        assert conflict["causedByChange"] is True
        assert conflict["first"]["bookingId"] == "1"
        assert conflict["first"]["eventId"] == "901"
        assert conflict["second"]["bookingId"] == "2"






