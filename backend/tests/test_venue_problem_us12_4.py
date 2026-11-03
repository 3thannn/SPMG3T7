"""US12.4: a venue problem on a Confirmed event reopens planning.

Acceptance criteria, and the tests that hold each one:

* A booking on a Confirmed event flagged "Needs replacement" (US12.2) does not
  change the event's status; the Coordinator acts -> `TestTheFlagAlone`. The
  flag is written by the database's trigger, so the notices it writes (the
  Coordinator's and, now, the Organiser's) are held by
  integration/test_us12_4_db.py.
* Requesting a replacement (US14.5) on a Confirmed event moves it
  Confirmed -> Planning, with the reason recorded; its other bookings are
  untouched -> `TestRequestingAReplacement`. The database half is
  SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql.
* The Organiser is told it is back in Planning (US10.3) -> `TestNotices`.
* Venue Staff approve the replacement, the event goes through the safety check
  again and the Coordinator confirms it (US4.7) -> `TestTheFullPath`.
* It cannot be confirmed while a booking still Needs replacement -> held by
  US4.7, `test_confirm_event_us4_7.py`.

The story's tests: the flag test is integration/test_us12_4_db.py;
`test_a_replacement_moves_it_to_planning` and
`test_back_to_confirmed_through_every_approval`.
"""

import pytest

from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus
from app.event_store import Event, StatusChange
from app.notifications import CoordinatorNotice
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEED_ATTRS

EVENT_ID = 960
FLAGGED, OTHER = 41, 42
GREAT_HALL, BERTHA_ROOM, THIRD_VENUE = 1, 2, 3
STARTS, ENDS = "2099-11-02T09:00", "2099-11-02T17:00"
FIRST_CHECK = "2099-01-02T10:00:00"
CONFIRMED_AT = "2099-01-02T12:00:00"

COORDINATOR = "Event Coordinator"
OFFICER = "Safety Officer"
STAFF = "Venue Staff"

REASON = (
    "Great Hall is unavailable (scheduled maintenance), so Bertha Room was requested "
    "instead. It needs Venue Staff's approval and a new safety check before the event "
    "is Confirmed again."
)


def booking(booking_id, venue_id, venue_name, status, **extra) -> Booking:
    return Booking(
        id=booking_id,
        event_id=EVENT_ID,
        venue_id=venue_id,
        venue_name=venue_name,
        starts_at=STARTS,
        ends_at=ENDS,
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
        **extra,
    )


@pytest.fixture
def flagged(event_repository, booking_repository):
    """A Confirmed event whose Great Hall booking a closure flagged, beside a second venue."""

    def _seed(status: EventStatus = EventStatus.CONFIRMED) -> Event:
        event = Event(
            id=EVENT_ID,
            title="Open House",
            purpose="Welcome visitors",
            description="Tours and talks.",
            starts_at=STARTS,
            ends_at=ENDS,
            expected_attendance=30,
            status=status,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="2099-01-01T09:00:00",
            updated_at=CONFIRMED_AT,
            coordinator_id=COORDINATOR_ID,
            history=(
                StatusChange(
                    EventStatus.PLANNING,
                    EventStatus.PENDING_SAFETY_CHECK,
                    FIRST_CHECK,
                    COORDINATOR_ID,
                    "Priya",
                ),
                StatusChange(
                    EventStatus.PENDING_SAFETY_CHECK,
                    EventStatus.CONFIRMED,
                    CONFIRMED_AT,
                    COORDINATOR_ID,
                    "Priya",
                ),
            ),
            **SUBMITTABLE_NEED_ATTRS,
        )
        event_repository.events.append(event)
        booking_repository.bookings.extend(
            [
                booking(
                    FLAGGED,
                    GREAT_HALL,
                    "Great Hall",
                    BookingStatus.NEEDS_REPLACEMENT,
                    replacement_reason="scheduled maintenance",
                ),
                booking(OTHER, THIRD_VENUE, "Third Venue", BookingStatus.CONFIRMED),
            ]
        )
        return event

    return _seed


def replace_with_bertha(client, auth_headers):
    return client.post(
        f"/bookings/{FLAGGED}/request-replacement",
        json={"venueId": str(BERTHA_ROOM)},
        headers=auth_headers(COORDINATOR),
    )


def event_json(client, auth_headers) -> dict:
    response = client.get(f"/events/{EVENT_ID}", headers=auth_headers(COORDINATOR))
    assert response.status_code == 200, response.text
    return response.json()


class TestTheFlagAlone:
    def test_the_event_stays_confirmed(self, client, auth_headers, flagged):
        flagged()

        assert event_json(client, auth_headers)["status"] == "Confirmed"


class TestRequestingAReplacement:
    def test_a_replacement_moves_it_to_planning(self, client, auth_headers, flagged):
        flagged()

        response = replace_with_bertha(client, auth_headers)

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "Requested"
        assert event_json(client, auth_headers)["status"] == "Planning"


    def test_the_other_bookings_are_untouched(
        self, client, auth_headers, flagged, booking_repository
    ):
        flagged()

        replace_with_bertha(client, auth_headers)

        statuses = {b.id: b.status for b in booking_repository.bookings}
        assert statuses[FLAGGED] is BookingStatus.REPLACED
        assert statuses[OTHER] is BookingStatus.CONFIRMED




class TestNotices:
    def test_the_organiser_is_told_and_why(
        self, client, auth_headers, flagged, notification_repository
    ):
        flagged()

        replace_with_bertha(client, auth_headers)

        told = [
            (notice.user_id, notice.message)
            for notice in notification_repository.notifications
            if notice.kind == CoordinatorNotice.BACK_IN_PLANNING
        ]
        assert told == [(ORGANISER_ID, f'"Open House" is back in Planning. {REASON}')]



class TestTheFullPath:
    def test_back_to_confirmed_through_every_approval(self, client, auth_headers, flagged):
        flagged()
        replacement = replace_with_bertha(client, auth_headers).json()

        # Venue Staff approve the replacement (US16.1).
        approved = client.post(
            f"/booking-requests/{replacement['id']}/approve", headers=auth_headers(STAFF)
        )
        assert approved.status_code == 200, approved.text
        # The Coordinator sends it for its safety check again (US4.4).
        sent = client.post(f"/events/{EVENT_ID}/safety-check", headers=auth_headers(COORDINATOR))
        assert sent.status_code == 200, sent.text
        # The Safety Officer approves this check, not the earlier one (US17.2).
        review = client.get(f"/events/{EVENT_ID}/safety-review", headers=auth_headers(OFFICER))
        assert review.json()["waitingSince"] != FIRST_CHECK
        signed = client.post(
            f"/events/{EVENT_ID}/safety-check/approve",
            json={"checkStartedAt": review.json()["waitingSince"]},
            headers=auth_headers(OFFICER),
        )
        assert signed.status_code == 200, signed.text
        # And the Coordinator confirms it (US4.7).
        confirmed = client.post(f"/events/{EVENT_ID}/confirm", headers=auth_headers(COORDINATOR))

        assert confirmed.status_code == 200, confirmed.text
        assert [(e["from"], e["to"]) for e in confirmed.json()["history"][-3:]] == [
            ("Confirmed", "Planning"),
            ("Planning", "Pending Safety Check"),
            ("Pending Safety Check", "Confirmed"),
        ]



