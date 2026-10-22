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

from app import booking_store
from app.booking_store import HOLDS_VENUE, BookingStatus, StaleBookingStatus
from app.event_status import EventStatus
from app.events import CANCELLATION_REASON_MAX
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

    def test_the_cancellation_is_stored(
        self, client, coordinator, booked, booking_repository
    ):
        cancel(client, coordinator, booked["id"])

        [stored] = booking_repository.bookings
        assert stored.status is BookingStatus.CANCELLED
        assert stored.cancellation is not None
        assert stored.cancellation.by_id == COORDINATOR_ID
        assert stored.cancellation.reason == REASON

    def test_the_cancelled_booking_stays_on_the_event(self, client, coordinator, booked):
        cancelled = cancel(client, coordinator, booked["id"]).json()

        assert bookings(client, coordinator) == [cancelled]

    def test_the_owning_organiser_sees_who_cancelled_and_why(
        self, client, coordinator, auth_headers, booked
    ):
        cancel(client, coordinator, booked["id"])

        [seen] = bookings(client, auth_headers("Event Organiser"))
        assert seen["status"] == "Cancelled"
        assert seen["cancellation"]["byName"] == "Priya"
        assert seen["cancellation"]["reason"] == REASON

    def test_everything_but_the_status_and_cancellation_is_as_it_was(
        self, client, coordinator, booked
    ):
        cancelled = cancel(client, coordinator, booked["id"]).json()

        unchanged = {k: v for k, v in cancelled.items() if k not in ("status", "cancellation")}
        assert unchanged == {k: v for k, v in booked.items() if k not in ("status", "cancellation")}

    def test_the_reason_is_trimmed(self, client, coordinator, booked):
        body = cancel(client, coordinator, booked["id"], reason=f"  {REASON}\n").json()

        assert body["cancellation"]["reason"] == REASON


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

    def test_bookings_on_other_events_are_untouched(
        self, client, coordinator, event, event_repository
    ):
        seed_event(event_repository, event_id=901)
        here = request(client, coordinator).json()
        # US15.1: the Great Hall's slot is taken by `here`, so `there` is elsewhere.
        there = request(client, coordinator, event_id=901, venueId=SEMINAR_ROOM).json()

        cancel(client, coordinator, here["id"])

        assert bookings(client, coordinator, event_id=901) == [there]


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

    def test_cancelling_the_last_booking_still_leaves_the_event_alone(
        self, client, coordinator, booked
    ):
        before = client.get(f"/events/{EVENT_ID}", headers=coordinator).json()

        cancel(client, coordinator, booked["id"])

        after = client.get(f"/events/{EVENT_ID}", headers=coordinator).json()
        assert after["status"] == before["status"]
        assert after["history"] == before["history"]
        assert after["updatedAt"] == before["updatedAt"]


class TestTheVenueIsFreed:
    """AC4: a cancelled booking no longer holds the venue for its slot (US15.1)."""

    def test_a_requested_booking_holds_the_venue(self, booked, booking_repository):
        assert booking_repository.bookings[0].holds_venue

    def test_a_cancelled_booking_does_not(
        self, client, coordinator, booked, booking_repository
    ):
        cancel(client, coordinator, booked["id"])

        assert not booking_repository.bookings[0].holds_venue

    def test_only_requested_held_and_confirmed_can_hold_a_venue(self):
        # US14.3: a Held booking holds the venue too, until it expires.
        # US16.1: so does a Confirmed one; a Rejected one frees it.
        assert HOLDS_VENUE == {
            BookingStatus.REQUESTED,
            BookingStatus.HELD,
            BookingStatus.CONFIRMED,
        }
        assert BookingStatus.REJECTED not in HOLDS_VENUE
        assert BookingStatus.CANCELLED not in HOLDS_VENUE

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

    def test_the_owning_organiser_cannot_cancel(self, client, auth_headers, booked):
        response = cancel(client, auth_headers("Event Organiser"), booked["id"])

        assert response.status_code == 403
        assert response.json()["detail"]["required"] == "bookings:request"

    def test_venue_staff_cannot_cancel(self, client, auth_headers, booked):
        assert cancel(client, auth_headers("Venue Staff"), booked["id"]).status_code == 403

    def test_a_coordinator_no_longer_assigned_cannot_cancel(
        self, client, coordinator, booked, event_repository, booking_repository
    ):
        # Reassigned to someone else after the booking was made.
        event_repository.events = [replace(event_repository.events[0], coordinator_id=99)]

        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 404
        assert booking_repository.bookings[0].status is BookingStatus.REQUESTED

    def test_a_signed_out_caller_is_asked_to_sign_in(self, client, booked):
        response = client.post(cancel_path(booked["id"]), json={"reason": REASON})

        assert response.status_code == 401

    @pytest.mark.parametrize("event_status", [EventStatus.REJECTED, EventStatus.COMPLETED])
    def test_a_booking_on_a_closed_event_can_still_be_cancelled(
        self, client, coordinator, event_repository, booking_repository, event_status
    ):
        """Cancelling the hall for an event that will not run is how it is given back."""
        seed_event(event_repository, status=event_status)
        booking = booking_repository.create(
            event_id=EVENT_ID,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=COORDINATOR_ID,
            headcount=30,
        )

        response = cancel(client, coordinator, str(booking.id))

        assert response.status_code == 200, response.text

    def test_a_cancelled_event_is_read_only(
        self, client, coordinator, event_repository, booking_repository
    ):
        """US4.6: cancelling the event already gave its bookings back, and it is
        read-only from then on."""
        seed_event(event_repository, status=EventStatus.CANCELLED)
        booking = booking_repository.create(
            event_id=EVENT_ID,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=COORDINATOR_ID,
            headcount=30,
        )

        response = cancel(client, coordinator, str(booking.id))

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-cancelled"
        assert booking_repository.get_booking(booking.id).status is BookingStatus.REQUESTED


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

    def test_an_overlong_reason_is_refused(self, client, coordinator, booked):
        response = cancel(
            client, coordinator, booked["id"], reason="x" * (CANCELLATION_REASON_MAX + 1)
        )

        assert response.status_code == 400
        assert str(CANCELLATION_REASON_MAX) in response.json()["detail"]["message"]

    def test_a_booking_that_is_not_there_is_not_found(self, client, coordinator, booked):
        response = cancel(client, coordinator, "12345")

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "booking_not_found"

    def test_a_non_numeric_booking_id_is_not_found(self, client, coordinator, booked):
        response = cancel(client, coordinator, "abc")

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "booking_not_found"

    def test_a_booking_on_another_event_is_not_found_through_this_one(
        self, client, coordinator, booked, event_repository
    ):
        seed_event(event_repository, event_id=901)

        response = cancel(client, coordinator, booked["id"], event_id=901)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "booking_not_found"

    def test_a_missing_event_is_not_found(self, client, coordinator, booked):
        response = cancel(client, coordinator, booked["id"], event_id=12345)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "event_not_found"


class TestCancellingTwice:
    def test_a_second_cancel_is_refused_with_the_reason(self, client, coordinator, booked):
        cancel(client, coordinator, booked["id"])

        response = cancel(client, coordinator, booked["id"], reason="Changed my mind again.")

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "rule_refused"
        assert detail["reason"] == "already-cancelled"

    def test_the_first_cancellation_is_kept(self, client, coordinator, booked):
        first = cancel(client, coordinator, booked["id"]).json()

        cancel(client, coordinator, booked["id"], reason="Changed my mind again.")

        assert bookings(client, coordinator) == [first]

    def test_the_status_is_checked_before_the_reason(self, client, coordinator, booked):
        cancel(client, coordinator, booked["id"])

        assert cancel(client, coordinator, booked["id"], reason="").status_code == 409

    def test_losing_a_race_to_another_cancel_is_refused_not_crashed(
        self, client, coordinator, booked, monkeypatch
    ):
        """The booking was Requested when read, and Cancelled by the time of the write."""

        def cancelled_meanwhile(*_args, **_kwargs):
            raise StaleBookingStatus

        monkeypatch.setattr(booking_store.repository(), "cancel", cancelled_meanwhile)

        response = cancel(client, coordinator, booked["id"])

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "already-cancelled"
