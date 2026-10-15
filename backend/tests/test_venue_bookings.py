"""Venue bookings for an event — US14.1.

An assigned Coordinator requests one or more venues for a single event, so a
bigger event can use a main hall and its breakout rooms at once. The classes
below follow the acceptance criteria in order, then the status rule, then every
way a request can be refused, then the one place bookings reach back into the
venue catalogue (a booked venue cannot be deleted).

Fixture venues are 1 (Great Hall), 2 (Bertha Room) and 3 (Seminar Room 4); see
conftest. No bookings exist until a test requests one.
"""

from datetime import date

import pytest

from app.booking_store import BookingStatus
from app.event_status import BOOKABLE, BookingRefusal, EventStatus, check_booking
from app.event_store import Event
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

EVENT_ID = 900
GREAT_HALL = "1"
BERTHA_ROOM = "2"
SEMINAR_ROOM = "3"

#: A valid request. Tests override one field at a time, so a failure names the
#: field that broke rather than the whole request.
BOOKING = {
    "venueId": GREAT_HALL,
    "startsAt": "2027-11-02T09:00",
    "endsAt": "2027-11-02T17:00",
}


def seed_event(
    event_repository,
    *,
    event_id: int = EVENT_ID,
    status: EventStatus = EventStatus.APPROVED,
    coordinator_id: int | None = COORDINATOR_ID,
    organiser_id: int = ORGANISER_ID,
    # Small enough for every fixture venue (Bertha Room holds 40), so the US14.1
    # tests are about booking, not about US18.1's suitability check.
    expected_attendance: int | None = 30,
) -> Event:
    """An event straight into the store, at whatever status the test needs."""
    event = Event(
        id=event_id,
        title="Faculty Welcome Night",
        purpose="Welcome the new intake.",
        description="",
        starts_at="2027-11-02T09:00",
        ends_at="2027-11-02T17:00",
        expected_attendance=expected_attendance,
        status=status,
        organiser_id=organiser_id,
        organiser_name="Dylan",
        created_at="2026-10-01T09:00:00",
        updated_at="2026-10-01T09:00:00",
        coordinator_id=coordinator_id,
    )
    event_repository.events.append(event)
    return event


def path(event_id: int = EVENT_ID) -> str:
    return f"/events/{event_id}/bookings"


def request(client, headers, event_id: int = EVENT_ID, **overrides):
    """POST a booking with overrides; `None` drops the field from the body."""
    body = {**BOOKING, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(path(event_id), json=body, headers=headers)


def refusal(response) -> dict:
    """The 400 body, asserting it is the shape this story promises."""
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_booking"
    return detail


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def organiser(auth_headers):
    return auth_headers("Event Organiser")


@pytest.fixture
def event(event_repository):
    """An Approved event, assigned to the fixture Coordinator."""
    return seed_event(event_repository)


class TestRequestingABooking:
    """AC1 and AC5: a booking is its own record, and it starts Requested."""

    def test_the_assigned_coordinator_requests_a_venue(self, client, coordinator, event):
        response = request(client, coordinator)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["eventId"] == str(EVENT_ID)
        assert body["venueId"] == GREAT_HALL
        assert body["venueName"] == "Great Hall"
        assert body["startsAt"] == "2027-11-02T09:00"
        assert body["endsAt"] == "2027-11-02T17:00"
        assert body["requestedAt"]

    def test_a_new_booking_is_requested_and_waits_for_venue_staff(
        self, client, coordinator, event
    ):
        assert request(client, coordinator).json()["status"] == "Requested"

    def test_the_response_uses_the_wire_names_and_nothing_else(self, client, coordinator, event):
        body = request(client, coordinator).json()

        assert set(body) == {
            "id",
            "eventId",
            "venueId",
            "venueName",
            "startsAt",
            "endsAt",
            "status",
            "requestedAt",
            "headcount",
            "requiredLayout",
            "requiredFacilities",
            "accessibilityNeeds",
            "cancellation",
            # US14.3: empty and False on a booking that was never a hold.
            "holdExpiresAt",
            "holdExpired",
            "heldByName",
        }
        assert isinstance(body["id"], str)
        # US14.2: only a cancelled booking says who cancelled it.
        assert body["cancellation"] is None

    def test_the_booking_is_stored_against_the_event_and_the_venue(
        self, client, coordinator, event, booking_repository
    ):
        request(client, coordinator)

        [stored] = booking_repository.bookings
        assert stored.event_id == EVENT_ID
        assert stored.venue_id == 1
        assert stored.starts_at == "2027-11-02T09:00"
        assert stored.ends_at == "2027-11-02T17:00"
        assert stored.status is BookingStatus.REQUESTED

    def test_the_record_keeps_who_requested_it(
        self, client, coordinator, event, booking_repository
    ):
        request(client, coordinator)

        assert booking_repository.bookings[0].requested_by_id == COORDINATOR_ID

    def test_a_venue_id_sent_as_a_number_is_accepted(self, client, coordinator, event):
        response = request(client, coordinator, venueId=1)

        assert response.status_code == 201, response.text
        assert response.json()["venueId"] == GREAT_HALL

    def test_times_with_seconds_are_accepted(self, client, coordinator, event):
        response = request(
            client, coordinator, startsAt="2027-11-02T09:00:00", endsAt="2027-11-02T17:00:00"
        )

        assert response.status_code == 201, response.text

    def test_values_are_trimmed_before_they_are_read(self, client, coordinator, event):
        response = request(
            client,
            coordinator,
            venueId=f" {GREAT_HALL} ",
            startsAt="  2027-11-02T09:00 ",
            endsAt="\t2027-11-02T17:00\n",
        )

        assert response.status_code == 201, response.text
        assert response.json()["startsAt"] == "2027-11-02T09:00"

    def test_the_booking_need_not_match_the_event_times(self, client, coordinator, event):
        """A breakout room may be wanted for the afternoon only, or a hall the night before."""
        response = request(
            client, coordinator, startsAt="2027-11-01T18:00", endsAt="2027-11-01T22:00"
        )

        assert response.status_code == 201, response.text


class TestManyBookingsForOneEvent:
    """AC1 and AC3: one event can have many, and each stands on its own."""

    def test_an_event_can_have_several_venues(self, client, coordinator, event):
        hall = request(client, coordinator, venueId=GREAT_HALL).json()
        breakout_a = request(client, coordinator, venueId=SEMINAR_ROOM).json()
        breakout_b = request(client, coordinator, venueId=BERTHA_ROOM).json()

        listed = client.get(path(), headers=coordinator).json()

        assert {booking["id"] for booking in listed} == {
            hall["id"],
            breakout_a["id"],
            breakout_b["id"],
        }
        assert len({hall["id"], breakout_a["id"], breakout_b["id"]}) == 3

    def test_the_same_venue_can_be_booked_twice_for_one_event(self, client, coordinator, event):
        """Two days in the same hall is two bookings. Clashes are US15.1's to judge."""
        first = request(client, coordinator)
        second = request(
            client, coordinator, startsAt="2027-11-03T09:00", endsAt="2027-11-03T17:00"
        )

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

    def test_a_refused_booking_does_not_block_the_others(self, client, coordinator, event):
        hall = request(client, coordinator, venueId=GREAT_HALL)
        refused = request(client, coordinator, venueId="999")
        breakout = request(client, coordinator, venueId=SEMINAR_ROOM)

        assert hall.status_code == 201, hall.text
        refusal(refused)
        assert breakout.status_code == 201, breakout.text
        listed = client.get(path(), headers=coordinator).json()
        assert [booking["venueName"] for booking in listed] == ["Great Hall", "Seminar Room 4"]

    def test_a_refused_booking_leaves_an_earlier_one_untouched(self, client, coordinator, event):
        created = request(client, coordinator).json()

        request(client, coordinator, endsAt="2027-11-02T08:00")

        assert client.get(path(), headers=coordinator).json() == [created]

    def test_bookings_belong_to_the_event_they_were_requested_for(
        self, client, coordinator, event, event_repository
    ):
        seed_event(event_repository, event_id=901)
        request(client, coordinator, event_id=EVENT_ID)

        assert client.get(path(901), headers=coordinator).json() == []


class TestBookingsShowOnTheEvent:
    """AC4: every booking for the event, together, readable on the event page."""

    def test_no_bookings_is_an_empty_list(self, client, coordinator, event):
        response = client.get(path(), headers=coordinator)

        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_a_stored_booking_reads_back(self, client, coordinator, event):
        created = request(client, coordinator).json()

        assert client.get(path(), headers=coordinator).json() == [created]

    def test_bookings_come_back_soonest_first(self, client, coordinator, event):
        request(
            client,
            coordinator,
            venueId=SEMINAR_ROOM,
            startsAt="2027-11-02T13:00",
            endsAt="2027-11-02T15:00",
        )
        request(client, coordinator, venueId=GREAT_HALL)
        request(
            client,
            coordinator,
            venueId=BERTHA_ROOM,
            startsAt="2027-11-02T09:00",
            endsAt="2027-11-02T12:00",
        )

        listed = client.get(path(), headers=coordinator).json()

        # Great Hall and Bertha Room both start at 09:00; the earlier end leads.
        assert [booking["venueName"] for booking in listed] == [
            "Bertha Room",
            "Great Hall",
            "Seminar Room 4",
        ]

    def test_the_owning_organiser_sees_the_bookings(self, client, coordinator, organiser, event):
        created = request(client, coordinator).json()

        response = client.get(path(), headers=organiser)

        assert response.status_code == 200, response.text
        assert response.json() == [created]

    def test_another_organisers_event_is_not_found(self, client, organiser, event_repository):
        seed_event(event_repository, organiser_id=99)

        response = client.get(path(), headers=organiser)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "event_not_found"

    def test_a_coordinator_not_assigned_to_the_event_does_not_see_them(
        self, client, coordinator, event_repository
    ):
        seed_event(event_repository, coordinator_id=99)

        assert client.get(path(), headers=coordinator).status_code == 404

    def test_venue_staff_cannot_read_an_events_bookings(self, client, auth_headers, event):
        response = client.get(path(), headers=auth_headers("Venue Staff"))

        assert response.status_code == 403

    def test_a_missing_event_is_not_found(self, client, coordinator):
        assert client.get(path(12345), headers=coordinator).status_code == 404

    def test_a_non_numeric_event_id_is_not_found(self, client, coordinator):
        assert client.get("/events/abc/bookings", headers=coordinator).status_code == 404


class TestOnlyTheAssignedCoordinatorRequests:
    """AC6 (US8.6): the role, and then the assignment."""

    def test_the_owning_organiser_cannot_request(
        self, client, organiser, event, booking_repository
    ):
        response = request(client, organiser)

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert detail["required"] == "bookings:request"
        assert booking_repository.bookings == []

    def test_venue_staff_cannot_request(self, client, auth_headers, event, booking_repository):
        response = request(client, auth_headers("Venue Staff"))

        assert response.status_code == 403
        assert booking_repository.bookings == []

    def test_a_coordinator_not_assigned_to_the_event_cannot_request(
        self, client, coordinator, event_repository, booking_repository
    ):
        seed_event(event_repository, coordinator_id=99)

        response = request(client, coordinator)

        # The same answer US8.1 gives for the event itself: not theirs, not found.
        assert response.status_code == 404
        assert booking_repository.bookings == []

    def test_an_unassigned_event_cannot_have_venues_requested(
        self, client, coordinator, event_repository, booking_repository
    ):
        seed_event(event_repository, coordinator_id=None)

        assert request(client, coordinator).status_code == 404
        assert booking_repository.bookings == []

    def test_a_signed_out_caller_is_asked_to_sign_in(self, client, event):
        assert client.post(path(), json=BOOKING).status_code == 401
        assert client.get(path()).status_code == 401

    def test_only_the_coordinator_role_holds_the_permission(self):
        from app.permissions import Permission, Role, roles_with

        assert roles_with(Permission.BOOKINGS_REQUEST) == [Role.COORDINATOR]


class TestEventStatus:
    """Venues can be requested only after approval and during planning."""

    @pytest.mark.parametrize("event_status", BOOKABLE)
    def test_an_open_event_takes_requests(
        self, client, coordinator, event_repository, event_status
    ):
        seed_event(event_repository, status=event_status)

        assert request(client, coordinator).status_code == 201

    @pytest.mark.parametrize(
        "event_status",
        [EventStatus.REJECTED, EventStatus.CANCELLED, EventStatus.CONFIRMED, EventStatus.COMPLETED],
    )
    def test_a_closed_event_is_refused_with_the_reason(
        self, client, coordinator, event_repository, booking_repository, event_status
    ):
        seed_event(event_repository, status=event_status)

        response = request(client, coordinator)

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "rule_refused"
        assert detail["reason"] == "event-closed"
        assert detail["message"]
        assert booking_repository.bookings == []

    def test_a_closed_event_still_shows_the_bookings_it_had(
        self, client, coordinator, event_repository, booking_repository
    ):
        seed_event(event_repository, status=EventStatus.CANCELLED)
        booking_repository.create(
            event_id=EVENT_ID,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=COORDINATOR_ID,
            headcount=30,
        )

        assert len(client.get(path(), headers=coordinator).json()) == 1

    def test_a_draft_is_not_found_by_a_coordinator(
        self, client, coordinator, event_repository
    ):
        """The Coordinator cannot see a Draft, so the status rule is never reached."""
        seed_event(event_repository, status=EventStatus.DRAFT)

        assert request(client, coordinator).status_code == 404

    def test_the_rule_on_its_own(self):
        assert check_booking(status=EventStatus.DRAFT) is BookingRefusal.NOT_YET_SUBMITTED
        assert check_booking(status=EventStatus.SUBMITTED) is BookingRefusal.NOT_APPROVED
        assert check_booking(status=EventStatus.UNDER_REVIEW) is BookingRefusal.NOT_APPROVED
        assert check_booking(status=EventStatus.REJECTED) is BookingRefusal.EVENT_CLOSED
        assert all(check_booking(status=status) is None for status in BOOKABLE)

    def test_the_status_is_checked_before_the_body(self, client, coordinator, event_repository):
        """A closed event is refused for being closed, not for a missing venue."""
        seed_event(event_repository, status=EventStatus.REJECTED)

        assert request(client, coordinator, venueId=None).status_code == 409

    def test_visibility_is_checked_before_the_status(
        self, client, coordinator, event_repository
    ):
        seed_event(event_repository, status=EventStatus.REJECTED, coordinator_id=99)

        assert request(client, coordinator).status_code == 404


class TestRefusals:
    """Every way a well-addressed request can still be wrong, and nothing is stored."""

    @pytest.fixture(autouse=True)
    def _event(self, event):
        return event

    @pytest.fixture(autouse=True)
    def _nothing_stored(self, booking_repository):
        yield
        assert booking_repository.bookings == []

    def test_a_venue_is_required(self, client, coordinator):
        assert refusal(request(client, coordinator, venueId=None))["message"] == "Choose a venue."

    def test_a_blank_venue_is_no_venue(self, client, coordinator):
        assert refusal(request(client, coordinator, venueId="  "))["message"] == "Choose a venue."

    def test_a_venue_not_in_the_catalogue_is_refused(self, client, coordinator):
        detail = refusal(request(client, coordinator, venueId="999"))

        assert detail["message"] == "That venue is not in the catalogue."

    @pytest.mark.parametrize("venue_id", ["abc", "-1", "1.5", "²"])
    def test_a_venue_id_that_is_not_an_id_is_refused(self, client, coordinator, venue_id):
        detail = refusal(request(client, coordinator, venueId=venue_id))

        assert detail["message"] == "That venue is not in the catalogue."

    def test_a_start_is_required(self, client, coordinator):
        detail = refusal(request(client, coordinator, startsAt=None))

        assert detail["message"] == "Give the booking a start time."

    def test_an_end_is_required(self, client, coordinator):
        detail = refusal(request(client, coordinator, endsAt=None))

        assert detail["message"] == "Give the booking an end time."

    @pytest.mark.parametrize(
        "value", ["2027-11-02", "02/11/2027 09:00", "2027-11-02 09:00", "20271102T0900"]
    )
    def test_a_start_in_another_format_is_refused(self, client, coordinator, value):
        detail = refusal(request(client, coordinator, startsAt=value))

        assert detail["message"] == "Give the start time as YYYY-MM-DDTHH:MM."

    def test_an_impossible_date_is_refused(self, client, coordinator):
        detail = refusal(request(client, coordinator, endsAt="2027-02-30T10:00"))

        assert detail["message"] == "The end time 2027-02-30T10:00 is not a real date and time."

    def test_an_impossible_time_is_refused(self, client, coordinator):
        detail = refusal(request(client, coordinator, startsAt="2027-11-02T25:00"))

        assert "not a real date and time" in detail["message"]

    def test_an_end_before_the_start_is_refused(self, client, coordinator):
        detail = refusal(request(client, coordinator, endsAt="2027-11-02T08:00"))

        assert detail["message"] == "The booking must end after it starts."

    def test_an_end_equal_to_the_start_is_refused(self, client, coordinator):
        """A booking of no length is not a booking; the table's CHECK agrees."""
        detail = refusal(request(client, coordinator, endsAt=BOOKING["startsAt"]))

        assert detail["message"] == "The booking must end after it starts."

    def test_a_start_in_the_past_is_refused(self, client, coordinator):
        detail = refusal(
            request(client, coordinator, startsAt="2020-01-01T09:00", endsAt="2020-01-01T17:00")
        )

        assert detail["message"] == "A booking cannot start in the past."

    def test_the_venue_is_named_first(self, client, coordinator):
        detail = refusal(request(client, coordinator, venueId=None, startsAt=None, endsAt=None))

        assert detail["message"] == "Choose a venue."


def test_a_booking_starting_today_is_accepted(client, auth_headers, event):
    """The past is judged by date, so a time earlier today is not refused as past."""
    today = date.today().isoformat()

    response = request(
        client,
        auth_headers("Event Coordinator"),
        startsAt=f"{today}T09:00",
        endsAt=f"{today}T10:00",
    )

    assert response.status_code == 201, response.text


class TestBookedVenuesStayInTheCatalogue:
    """A venue an event has booked is in use, so US9.1c cannot delete it."""

    def test_a_booked_venue_cannot_be_deleted(
        self, client, coordinator, auth_headers, event, venue_repository
    ):
        request(client, coordinator, venueId=GREAT_HALL)

        response = client.delete(f"/venues/{GREAT_HALL}", headers=auth_headers("Venue Staff"))

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "venue_in_use"
        assert "Great Hall" in detail["message"]
        assert venue_repository.get_venue(1) is not None

    def test_an_unbooked_venue_still_deletes(
        self, client, coordinator, auth_headers, event, venue_repository
    ):
        request(client, coordinator, venueId=GREAT_HALL)

        response = client.delete(f"/venues/{SEMINAR_ROOM}", headers=auth_headers("Venue Staff"))

        assert response.status_code == 204
        assert venue_repository.get_venue(3) is None


def test_the_whole_journey_through_the_routes(client, organiser, coordinator, auth_headers):
    """Created and submitted by the Organiser, assigned, booked, and seen by both.
    US8.6: Coordinator Lead assigns the event to a coordinator."""
    created = client.post(
        "/events",
        json={
            "title": "Open Day",
            "purpose": "Show prospective students around.",
            "description": "Campus tours and talks.",
            "startsAt": "2027-11-02T09:00",
            "endsAt": "2027-11-02T17:00",
            "expectedAttendance": 300,
            **SUBMITTABLE_NEEDS,
        },
        headers=organiser,
    ).json()
    client.post(f"/events/{created['id']}/submit", headers=organiser)

    # US8.6: Coordinator Lead assigns the event
    assigned = client.post(
        f"/events/{created['id']}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    ).json()
    assert assigned["coordinatorId"] == str(COORDINATOR_ID)
    approved = client.post(f"/events/{created['id']}/approve", headers=coordinator)
    assert approved.status_code == 200, approved.text

    hall = client.post(
        f"/events/{created['id']}/bookings", json=BOOKING, headers=coordinator
    )
    # US18.1: the breakout room has its own headcount. Checked against the
    # event's 300 it would not fit Seminar Room 4, which holds 60.
    breakout = client.post(
        f"/events/{created['id']}/bookings",
        json={
            **BOOKING,
            "venueId": SEMINAR_ROOM,
            "startsAt": "2027-11-02T13:00",
            "headcount": 40,
        },
        headers=coordinator,
    )
    assert hall.status_code == 201, hall.text
    assert breakout.status_code == 201, breakout.text

    seen = client.get(f"/events/{created['id']}/bookings", headers=organiser).json()
    assert [(b["venueName"], b["status"], b["headcount"]) for b in seen] == [
        ("Great Hall", "Requested", 300),
        ("Seminar Room 4", "Requested", 40),
    ]
