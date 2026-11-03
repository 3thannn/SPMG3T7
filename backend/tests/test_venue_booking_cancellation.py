"""Cancelling one venue booking — US14.2.

The assigned Coordinator cancels a single booking with a reason, so one room
can change without redoing the plan. The classes follow the acceptance criteria
in order (the booking, the other bookings, the event, the venue's slot), then
who may cancel, then every way a cancel can be refused.

Bookings are made through US14.1's route, so these tests also hold the two
stories to the same shapes. Fixture venues are 1 (Great Hall), 2 (Bertha Room)
and 3 (Seminar Room 4); see conftest.
"""

from dataclasses import replace

import pytest

from app.booking_store import BookingStatus
from app.event_status import EventStatus
from tests.conftest import COORDINATOR_ID
from tests.test_venue_bookings import EVENT_ID, SEMINAR_ROOM, request, seed_event

REASON = "The hall is too big now that numbers have dropped."


def cancel_path(booking_id: str, event_id: int = EVENT_ID) -> str:
    return f"/events/{event_id}/bookings/{booking_id}/cancel"


def cancel(client, headers, booking_id: str, reason: str | None = REASON, event_id=EVENT_ID):
    body = {} if reason is None else {"reason": reason}
    return client.post(cancel_path(booking_id, event_id), json=body, headers=headers)


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


@pytest.fixture
def event(event_repository):
    return seed_event(event_repository)


@pytest.fixture
def booked(client, coordinator, event) -> dict:
    """One Requested booking for the Great Hall on the fixture event."""
    response = request(client, coordinator)
    assert response.status_code == 201, response.text
    return response.json()


def bookings(client, headers, event_id: int = EVENT_ID) -> list[dict]:
    response = client.get(f"/events/{event_id}/bookings", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


class TestCancellingOneBooking:
    """AC1: status to Cancelled, a reason required, and who and when kept."""

    def test_the_assigned_coordinator_cancels_a_booking(self, client, coordinator, booked):
        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == booked["id"]
        assert body["status"] == "Cancelled"

    def test_who_when_and_why_are_kept_on_the_booking(self, client, coordinator, booked):
        body = cancel(client, coordinator, booked["id"]).json()

        cancellation = body["cancellation"]
        assert set(cancellation) == {"at", "byId", "byName", "reason"}
        assert cancellation["byId"] == str(COORDINATOR_ID)
        assert cancellation["byName"] == "Priya"
        assert cancellation["reason"] == REASON
        assert cancellation["at"]







class TestOtherBookingsAreUnchanged:
    """AC2: cancelling one leaves every other booking on the event exactly as it was."""

    def test_only_the_cancelled_booking_changes(self, client, coordinator, event):
        hall = request(client, coordinator).json()
        breakout = request(
            client,
            coordinator,
            venueId=SEMINAR_ROOM,
            startsAt="2027-11-02T13:00",
            endsAt="2027-11-02T15:00",
        ).json()
        evening = request(
            client, coordinator, startsAt="2027-11-02T18:00", endsAt="2027-11-02T21:00"
        ).json()

        cancel(client, coordinator, breakout["id"])

        after = {booking["id"]: booking for booking in bookings(client, coordinator)}
        assert after[hall["id"]] == hall
        assert after[evening["id"]] == evening
        assert after[breakout["id"]]["status"] == "Cancelled"



class TestTheEventIsUnchanged:
    """AC3: the event's status, and the rest of it, do not move."""

    @pytest.mark.parametrize(
        "event_status",
        [EventStatus.APPROVED, EventStatus.PLANNING],
    )
    def test_the_event_status_is_unchanged(
        self, client, coordinator, event_repository, event_status
    ):
        seed_event(event_repository, status=event_status)
        booking = request(client, coordinator).json()
        before = client.get(f"/events/{EVENT_ID}", headers=coordinator).json()

        cancel(client, coordinator, booking["id"])

        after = client.get(f"/events/{EVENT_ID}", headers=coordinator).json()
        assert after["status"] == before["status"]
        assert after == before



class TestTheVenueIsFreed:
    """AC4: a cancelled booking no longer holds the venue for its slot (US15.1)."""




    def test_the_same_venue_and_slot_can_be_requested_again(
        self, client, coordinator, booked, booking_repository
    ):
        cancel(client, coordinator, booked["id"])

        again = request(client, coordinator)

        assert again.status_code == 201, again.text
        holding = [b for b in booking_repository.bookings if b.holds_venue]
        assert [b.id for b in holding] == [int(again.json()["id"])]


class TestWhoMayCancel:
    """The rule US14.1 set for requesting (US8.6) holds for cancelling too."""



    def test_a_coordinator_no_longer_assigned_cannot_cancel(
        self, client, coordinator, booked, event_repository, booking_repository
    ):
        # Reassigned to someone else after the booking was made.
        event_repository.events = [replace(event_repository.events[0], coordinator_id=99)]

        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 404
        assert booking_repository.bookings[0].status is BookingStatus.REQUESTED





class TestRefusals:
    """Every way a cancel can be refused, and the booking left as it was each time."""

    @pytest.fixture(autouse=True)
    def _still_requested(self, booked, booking_repository):
        yield
        assert all(b.status is BookingStatus.REQUESTED for b in booking_repository.bookings)

    def test_a_reason_is_required(self, client, coordinator, booked):
        response = cancel(client, coordinator, booked["id"], reason=None)

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_booking"
        assert detail["message"] == "Give a reason for cancelling this booking."

    def test_a_blank_reason_is_no_reason(self, client, coordinator, booked):
        assert cancel(client, coordinator, booked["id"], reason=" \n\t ").status_code == 400







class TestCancellingTwice:
    def test_a_second_cancel_is_refused_with_the_reason(self, client, coordinator, booked):
        cancel(client, coordinator, booked["id"])

        response = cancel(client, coordinator, booked["id"], reason="Changed my mind again.")

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "rule_refused"
        assert detail["reason"] == "already-cancelled"





class TestCancellingAConfirmedOrFlaggedBooking:
    """D7 (CODE_AUDIT.md): US12.2 AC5 and US15.2 AC4 clear a flag by cancelling the booking,
    and Week 7 #3 speaks of cancelling one venue arrangement. So a Confirmed booking and one
    flagged Needs replacement can be cancelled too, and a closed one says why it cannot."""

    @pytest.mark.parametrize(
        "status", [BookingStatus.CONFIRMED, BookingStatus.NEEDS_REPLACEMENT]
    )
    def test_it_can_be_cancelled_with_a_reason(
        self, client, coordinator, booked, booking_repository, status
    ):
        booking_repository.bookings = [
            replace(b, status=status) for b in booking_repository.bookings
        ]

        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Cancelled"
        assert response.json()["cancellation"]["reason"] == REASON
        assert not booking_repository.get_booking(int(booked["id"])).holds_venue

    @pytest.mark.parametrize(
        "status", [BookingStatus.REJECTED, BookingStatus.REPLACED]
    )
    def test_a_closed_booking_says_it_holds_nothing_to_cancel(
        self, client, coordinator, booked, booking_repository, status
    ):
        booking_repository.bookings = [
            replace(b, status=status) for b in booking_repository.bookings
        ]

        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "not-cancellable"
        assert detail["message"] == (
            f"This booking is {status}, so it no longer holds the venue. There is nothing "
            "to cancel."
        )
        assert booking_repository.get_booking(int(booked["id"])).status is status
