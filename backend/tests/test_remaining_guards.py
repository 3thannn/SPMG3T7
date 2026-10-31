"""Guards and fallbacks the story tests do not reach, one feature at a time.

Each of these is a refusal or a recovery: a session whose account went away, a
notice that has nobody to go to, a write that lost a race, an id that is not a
number. They are small, but each is a promise the code makes, and a promise
nothing checks is one a refactor can quietly break.
"""

from dataclasses import replace
from datetime import date, datetime

import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from app import permissions, registrations, users
from app.booking_store import TABLE as BOOKINGS_TABLE
from app.booking_store import InMemoryBookings, StaleBookingStatus, SupabaseBookings
from app.event_status import EventStatus
from app.event_store import StaleEventStatus
from app.notifications import notify_event_cancelled, notify_status_change
from app.permissions import Permission, Role, denial_message, denial_message_any
from app.registration_store import (
    InMemoryRegistrations,
    Registration,
    RegistrationStatus,
    StaleRegistrationSettings,
)
from app.registrations import RegistrationIn
from app.suitability import within_hours
from app.venue_store import DuplicateVenueName, SupabaseVenues
from app.venue_unavailability_store import InMemoryUnavailability, UnavailabilityReasonType
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEEDS,
    fixture_users,
)
from tests.test_booking_store import ROW as BOOKING_ROW

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}


@pytest.fixture
def assigned_event(client, auth_headers, event_repository):
    """An event under review with the fixture Coordinator, as the store holds it."""
    organiser = auth_headers("Event Organiser")
    event_id = client.post("/events", json=DRAFT, headers=organiser).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser).status_code == 200
    assigned = client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert assigned.status_code == 200, assigned.text
    return event_repository.get_event(int(event_id))


class TestSessions:
    def test_a_session_whose_account_was_removed_is_void(self, client, sign_in, user_store):
        headers = {"Authorization": f"Bearer {sign_in('Event Organiser')['token']}"}
        user_store.users = [user for user in user_store.users if user.id != ORGANISER_ID]

        removed = client.get("/auth/me", headers=headers)

        assert removed.status_code == 401
        assert removed.json()["detail"]["message"] == "Your account is no longer active."

        # The session went with the account: restoring the account does not revive it.
        user_store.users = fixture_users()
        assert client.get("/auth/me", headers=headers).status_code == 401


class TestDenials:
    """US1.3: a refusal names who may do it — or says nobody may, yet."""

    def test_a_permission_no_role_holds_says_so(self, monkeypatch):
        monkeypatch.setattr(permissions, "permissions_for", lambda _role: frozenset())

        single = denial_message(Role.ORGANISER, Permission.EVENTS_EDIT)
        either = denial_message_any(Role.ORGANISER, [Permission.EVENTS_EDIT])

        assert single.endswith("That is not available to any role yet.")
        assert either.endswith("That is not available to any role yet.")


class TestNotices:
    def test_a_status_with_no_notice_writes_nothing(
        self, assigned_event, notification_repository
    ):
        before = list(notification_repository.notifications)

        notify_status_change(assigned_event, EventStatus.PLANNING)

        assert notification_repository.notifications == before

    def test_a_cancellation_still_completes_when_the_directory_cannot_be_read(
        self, assigned_event, monkeypatch, caplog
    ):
        """US4.6: the cancellation has happened; a failed notice must not undo it."""

        def unreachable():
            raise RuntimeError("directory unavailable")

        monkeypatch.setattr(users, "list_users", unreachable)

        notify_event_cancelled(
            assigned_event,
            actor_id=ORGANISER_ID,
            actor_name="Dylan",
            reason="Storm warning",
            venue_names=["Great Hall"],
            equipment=[],
        )

        assert "Could not look up the US4.6 notice recipients" in caplog.text

    def test_an_attendee_who_cancelled_the_event_is_not_told_about_it(
        self, assigned_event, notification_repository
    ):
        """US4.6: nobody is notified of their own action, even as an Attendee."""
        notify_event_cancelled(
            assigned_event,
            actor_id=ATTENDEE_ID,
            actor_name="Casey",
            reason="Storm warning",
            venue_names=[],
            equipment=[],
            attendee_ids=[ATTENDEE_ID],
        )

        assert all(
            notice.user_id != ATTENDEE_ID for notice in notification_repository.notifications
        )


class TestRegistration:
    def test_settings_that_lost_a_race_are_a_conflict(
        self, client, auth_headers, assigned_event, event_repository, registration_repository,
        monkeypatch,
    ):
        event_repository._replace(replace(assigned_event, status=EventStatus.CONFIRMED))

        def stale(*_args, **_kwargs):
            raise StaleRegistrationSettings

        monkeypatch.setattr(registration_repository, "set_settings", stale)

        response = client.put(
            f"/events/{assigned_event.id}/registration",
            json={"open": True, "capacity": 30},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 409

    @pytest.mark.parametrize(
        ("name", "email", "expected"),
        [
            ("x" * 256, "casey@example.com", "Keep your name to 255 characters or fewer."),
            (
                "Casey",
                "casey@" + "x" * 250 + ".com",
                "Keep your email address to 255 characters or fewer.",
            ),
        ],
        ids=["name-over-limit", "email-over-limit"],
    )
    def test_a_name_or_email_over_255_characters_is_refused(self, name, email, expected):
        with pytest.raises(HTTPException) as refused:
            registrations._validated(RegistrationIn(name=name, email=email))

        assert refused.value.detail["message"] == expected

    def test_settings_for_an_event_that_is_gone_are_stale(self):
        with pytest.raises(StaleRegistrationSettings):
            InMemoryRegistrations().set_settings(
                404, actor_id=COORDINATOR_ID, is_open=True, capacity=10
            )

    def test_a_registration_whose_event_is_gone_carries_no_event(self, registration_repository):
        registration_repository.registrations.append(
            Registration(
                id=1,
                event_id=404,
                attendee_id=ATTENDEE_ID,
                name="Casey",
                email="casey@example.com",
                status=RegistrationStatus.REGISTERED,
                created_at="2026-10-01T09:00:00",
            )
        )

        [mine] = registration_repository.list_for_attendee(ATTENDEE_ID)

        assert mine.event is None

    def test_no_full_notice_for_an_event_that_is_gone(self, notification_repository):
        registrations._tell_full(404)

        assert notification_repository.notifications == []


class TestReplacementVenues:
    """US14.5: a booking id that is not a number names no booking."""

    def test_searching_from_a_booking_id_that_is_not_a_number_is_not_found(
        self, client, auth_headers
    ):
        response = client.get(
            "/bookings/abc/replacement-venues", headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 404

    def test_replacing_a_booking_id_that_is_not_a_number_is_not_found(
        self, client, auth_headers
    ):
        response = client.post(
            "/bookings/abc/request-replacement",
            json={"venueId": "2"},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 404

    def test_a_replacement_reads_back_the_booking_the_database_created(self, fake):
        fake.rpc_answers = {"request_replacement_venue": 55}
        fake.rows = {BOOKINGS_TABLE: [dict(BOOKING_ROW, id=55)]}

        booking = SupabaseBookings().request_replacement(7, venue_id=2, actor_id=COORDINATOR_ID)

        assert booking.id == 55

    def test_a_replacement_that_cannot_be_read_back_is_stale(self, fake):
        fake.rpc_answers = {"request_replacement_venue": 55}

        with pytest.raises(StaleBookingStatus):
            SupabaseBookings().request_replacement(7, venue_id=2, actor_id=COORDINATOR_ID)

    def test_the_stand_in_refuses_an_unknown_booking_too(self):
        with pytest.raises(StaleBookingStatus):
            InMemoryBookings().request_replacement(404, venue_id=2, actor_id=COORDINATOR_ID)


def test_a_guarded_booking_for_an_event_that_is_gone_is_stale():
    with pytest.raises(StaleEventStatus):
        InMemoryBookings().create(
            event_id=404,
            venue_id=1,
            starts_at="2027-11-02T09:00",
            ends_at="2027-11-02T17:00",
            requested_by_id=COORDINATOR_ID,
            headcount=10,
            expected_status=EventStatus.APPROVED,
        )


class TestVenueWrites:
    """US9.1a-b: a name clash is reported as one; any other failure is not."""

    VENUE = dict(
        name="Great Hall",
        location="Main Campus",
        capacity=500,
        facilities="Stage",
        accessibility_features="",
        operating_hours="",
        supported_layouts="",
    )

    @pytest.fixture
    def failing(self, monkeypatch):
        """Install a client whose writes fail with the error the test chooses."""
        from app import supabase_client

        class FailingWrite:
            error: Exception = RuntimeError("unset")

            def table(self, _name):
                return self

            def insert(self, _row):
                return self

            def update(self, _changes):
                return self

            def eq(self, *_args):
                return self

            def execute(self):
                raise self.error

        client = FailingWrite()
        monkeypatch.setattr(supabase_client, "admin", lambda: client)
        return client

    @staticmethod
    def database_error(code: str) -> APIError:
        return APIError({"code": code, "details": None, "hint": None, "message": code})

    def test_adding_a_venue_with_a_taken_name_is_a_duplicate(self, failing):
        failing.error = self.database_error("23505")

        with pytest.raises(DuplicateVenueName):
            SupabaseVenues().create_venue(**self.VENUE)

    def test_renaming_a_venue_to_a_taken_name_is_a_duplicate(self, failing):
        failing.error = self.database_error("23505")

        with pytest.raises(DuplicateVenueName):
            SupabaseVenues().save_venue(1, **self.VENUE)

    def test_any_other_write_failure_is_raised_as_it_is(self, failing):
        failing.error = self.database_error("XX000")

        with pytest.raises(APIError):
            SupabaseVenues().save_venue(1, **self.VENUE)


def test_a_zero_length_booking_needs_no_open_window():
    """US18.1: a booking with no duration occupies no moment, so no hours can refuse it."""
    moment = datetime(2027, 11, 2, 9, 0)

    assert within_hours({}, moment, moment) is True


def test_the_stand_in_accepts_a_reason_type_already_parsed():
    entry = InMemoryUnavailability().create(
        venue_id=1,
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 6),
        reason_type=UnavailabilityReasonType.MAINTENANCE,
        other_reason="",
        created_by_id=4,
    )

    assert entry.reason_type is UnavailabilityReasonType.MAINTENANCE


def test_a_custom_unavailability_reason_is_only_for_other(client, auth_headers):
    """US12.2: the free-text reason belongs to the "other" type alone."""
    response = client.post(
        "/venues/1/unavailability",
        json={
            "startDate": "2026-11-02",
            "endDate": "2026-11-06",
            "reasonType": "maintenance",
            "otherReason": "Repainting",
        },
        headers=auth_headers("Venue Staff"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == (
        'Only provide a custom reason when reason type is "other".'
    )
