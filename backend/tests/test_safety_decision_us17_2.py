"""US17.2: the Safety Officer records a decision.

Acceptance criteria, and the tests that hold each one:

* Approve -> event moves to Confirmed -> `TestApprove`.
* Request changes -> back to Planning; note required; affected venue/equipment
  arrangements flagged for re-review; assigned Coordinator notified (US10.2)
  -> `TestRequestChanges`, `TestReReview`.
* Reject -> reason required; back to Planning with the reason (the story's
  assumption) -> `TestReject`.
* Every decision is timestamped and attributable (US4.2 audit pattern) ->
  `TestDecisionRecord`.
* An event coming back into Pending Safety Check needs a fresh decision ->
  `TestFreshDecision`.

The rules themselves are in `TestRules`, and both stores in `TestInMemoryStore`
and `TestSupabaseStore`.
"""

from types import SimpleNamespace

import pytest

from app.booking_store import Booking, BookingStatus
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_status import EventStatus
from app.event_store import Event, StatusChange
from app.notifications import CoordinatorNotice
from app.safety_check import SAFETY_NOTE_MAX, SafetyCheckRefusal, check_ready_for_safety_check
from app.safety_decisions import (
    FLAGS_ONLY_ON_CHANGES,
    NOTE_REQUIRED,
    UNKNOWN_BOOKING,
    UNKNOWN_EQUIPMENT,
    SafetyOutcome,
    flag_error,
    note_error,
    same_check,
    to_status,
)
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEED_ATTRS,
)

PSC = EventStatus.PENDING_SAFETY_CHECK
EVENT_ID = 700
OTHER_EVENT_ID = 701
#: When the seeded event entered Pending Safety Check: its `waitingSince`.
ENTERED = "2099-01-02T10:00:00"
BOOKING_ID = 11
LINE_ID = 21


def seed_event(event_repository, status=PSC, *, event_id=EVENT_ID, coordinator_id=COORDINATOR_ID):
    history = (
        (StatusChange(EventStatus.PLANNING, PSC, ENTERED, COORDINATOR_ID, "Priya"),)
        if status is PSC
        else ()
    )
    event = Event(
        id=event_id,
        title="Open House",
        purpose="Welcome visitors",
        description="Tours and talks.",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        expected_attendance=30,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00",
        updated_at=ENTERED,
        coordinator_id=coordinator_id,
        history=history,
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    return event


def booking(booking_id=BOOKING_ID, status=BookingStatus.CONFIRMED, *, event_id=EVENT_ID):
    return Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=1,
        venue_name="Great Hall",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
    )


def line(line_id=LINE_ID, status=RESERVED, *, event_id=EVENT_ID):
    return EquipmentRequest(
        id=line_id,
        event_id=event_id,
        equipment_type="Projector",
        quantity=2,
        technical_requirements="HDMI",
        support_notes="",
        starts_at="2099-11-02T08:30",
        ends_at="2099-11-02T17:30",
        status=status,
        requested_by_id=COORDINATOR_ID,
        created_at="2099-01-01T09:00",
        version=1,
    )


@pytest.fixture
def world(event_repository, booking_repository, equipment_repository):
    """An event Pending Safety Check with one Confirmed venue and one reserved line."""
    seed_event(event_repository)
    booking_repository.bookings.append(booking())
    equipment_repository.requests.append(line())
    return SimpleNamespace(
        events=event_repository, bookings=booking_repository, equipment=equipment_repository
    )


@pytest.fixture
def officer(auth_headers):
    return auth_headers("Safety Officer")


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


def decide(client, headers, action, body=None, event_id=EVENT_ID):
    return client.post(f"/events/{event_id}/safety-check/{action}", json=body, headers=headers)


def changes(client, headers, *, bookings=(BOOKING_ID,), equipment=(), **extra):
    body = {
        "note": "Add a second fire exit.",
        "checkStartedAt": ENTERED,
        "flaggedBookingIds": [str(each) for each in bookings],
        "flaggedEquipmentIds": [str(each) for each in equipment],
        **extra,
    }
    return decide(client, headers, "request-changes", body)


def coordinator_notices(notification_repository):
    return [
        notice
        for notice in notification_repository.notifications
        if notice.user_id == COORDINATOR_ID
    ]


# -- The rules -----------------------------------------------------------------


class TestRules:
    def test_each_outcome_goes_where_the_story_says(self):
        # US4.7: an approval leaves the event for its Coordinator to confirm.
        assert to_status(SafetyOutcome.APPROVED) is EventStatus.PENDING_SAFETY_CHECK
        assert to_status(SafetyOutcome.CHANGES_REQUESTED) is EventStatus.PLANNING
        assert to_status(SafetyOutcome.REJECTED) is EventStatus.PLANNING

    def test_an_approval_needs_no_note(self):
        assert note_error(SafetyOutcome.APPROVED, "") is None

    @pytest.mark.parametrize(
        "outcome", [SafetyOutcome.CHANGES_REQUESTED, SafetyOutcome.REJECTED]
    )
    def test_changes_and_rejection_need_words(self, outcome):
        assert note_error(outcome, "") == NOTE_REQUIRED[outcome]
        assert note_error(outcome, "Exit blocked") is None

    def test_the_note_has_a_limit_whatever_the_outcome(self):
        too_long = "x" * (SAFETY_NOTE_MAX + 1)
        for outcome in SafetyOutcome:
            assert "2000 characters" in note_error(outcome, too_long)
        assert note_error(SafetyOutcome.REJECTED, "x" * SAFETY_NOTE_MAX) is None

    def test_no_flags_is_always_fine(self):
        for outcome in SafetyOutcome:
            assert flag_error(
                outcome, booking_ids=[], equipment_ids=[],
                flaggable_bookings=[], flaggable_equipment=[],
            ) is None

    @pytest.mark.parametrize("outcome", [SafetyOutcome.APPROVED, SafetyOutcome.REJECTED])
    def test_only_a_request_for_changes_flags(self, outcome):
        assert flag_error(
            outcome, booking_ids=[1], equipment_ids=[],
            flaggable_bookings=[1], flaggable_equipment=[],
        ) == FLAGS_ONLY_ON_CHANGES

    def test_only_what_was_shown_can_be_flagged(self):
        arguments = {"flaggable_bookings": [1, 2], "flaggable_equipment": [5]}
        assert flag_error(
            SafetyOutcome.CHANGES_REQUESTED, booking_ids=[3], equipment_ids=[], **arguments
        ) == UNKNOWN_BOOKING
        assert flag_error(
            SafetyOutcome.CHANGES_REQUESTED, booking_ids=[1], equipment_ids=[6], **arguments
        ) == UNKNOWN_EQUIPMENT
        assert flag_error(
            SafetyOutcome.CHANGES_REQUESTED, booking_ids=[1, 2, 2], equipment_ids=[5],
            **arguments,
        ) is None

    def test_the_same_check_is_compared_as_a_time(self):
        assert same_check("2099-01-02 10:00:00", "2099-01-02T10:00:00")
        assert same_check("2099-01-02T10:00:00.000000", "2099-01-02T10:00:00")
        assert not same_check("2099-01-02T10:00:01", "2099-01-02T10:00:00")

    def test_a_check_that_is_not_a_time_is_an_error(self):
        with pytest.raises(ValueError):
            same_check("yesterday", ENTERED)

    def test_open_flags_hold_the_event_back(self):
        refusal = check_ready_for_safety_check(
            status=EventStatus.PLANNING, change_requested=False,
            bookings=[booking()], equipment=[], flags_open=True,
        )
        assert refusal is SafetyCheckRefusal.FLAGS_OPEN

    def test_a_pending_change_request_is_named_before_open_flags(self):
        refusal = check_ready_for_safety_check(
            status=EventStatus.PLANNING, change_requested=True,
            bookings=[booking()], equipment=[], flags_open=True,
        )
        assert refusal is SafetyCheckRefusal.CHANGE_PENDING


# -- AC1: Approve -> Confirmed --------------------------------------------------


class TestApprove:
    def test_approval_leaves_it_for_the_coordinator_to_confirm(self, client, officer, world):
        """US4.7: the Safety Officer approves; the Coordinator confirms."""
        response = decide(client, officer, "approve", {"checkStartedAt": ENTERED})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Pending Safety Check"
        assert response.json()["safetyApproved"] is True
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_an_approval_without_a_body_still_works(self, client, officer, world):
        assert decide(client, officer, "approve").json()["safetyApproved"] is True

    def test_an_approval_flags_nothing(self, client, officer, world):
        response = decide(
            client, officer, "approve", {"flaggedBookingIds": [str(BOOKING_ID)]}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == FLAGS_ONLY_ON_CHANGES
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_an_approval_tells_the_coordinator_it_is_theirs_to_confirm(
        self, client, officer, world, notification_repository
    ):
        """US4.7: confirming is the Coordinator's move now, so they hear."""
        decide(client, officer, "approve")
        (notice,) = coordinator_notices(notification_repository)
        assert notice.kind == CoordinatorNotice.SAFETY_APPROVED
        assert notice.message == (
            'The Safety Officer approved the safety check for "Open House". '
            "Confirm the event once its venues and equipment are all in place."
        )


# -- AC2: Request changes -------------------------------------------------------


class TestRequestChanges:
    def test_back_to_planning_with_the_note(self, client, officer, world):
        response = changes(client, officer)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Planning"
        last = body["history"][-1]
        assert (last["from"], last["to"]) == ("Pending Safety Check", "Planning")
        assert last["notes"] == "Add a second fire exit."
        assert last["kind"] == "safety-return"

    @pytest.mark.parametrize("note", ["", "   "])
    def test_a_note_is_required(self, client, officer, world, note):
        response = changes(client, officer, note=note)
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            NOTE_REQUIRED[SafetyOutcome.CHANGES_REQUESTED]
        )
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_the_note_has_a_limit(self, client, officer, world):
        response = changes(client, officer, note="x" * (SAFETY_NOTE_MAX + 1))
        assert response.status_code == 400

    def test_the_affected_arrangements_are_flagged(
        self, client, officer, world, safety_decision_repository
    ):
        changes(client, officer, bookings=(BOOKING_ID,), equipment=(LINE_ID,))
        [decision] = safety_decision_repository.list_for_event(EVENT_ID)
        assert [(flag.booking_id, flag.equipment_request_id) for flag in decision.flags] == [
            (BOOKING_ID, None),
            (None, LINE_ID),
        ]
        assert all(flag.is_open for flag in decision.flags)

    def test_nothing_need_be_flagged(self, client, officer, world, safety_decision_repository):
        assert changes(client, officer, bookings=()).status_code == 200
        [decision] = safety_decision_repository.list_for_event(EVENT_ID)
        assert decision.flags == ()

    def test_a_booking_not_in_the_review_cannot_be_flagged(self, client, officer, world):
        world.bookings.bookings.append(booking(12, BookingStatus.CANCELLED))
        world.bookings.bookings.append(booking(13, event_id=OTHER_EVENT_ID))
        for stranger in (12, 13, 999):
            response = changes(client, officer, bookings=(stranger,))
            assert response.status_code == 400
            assert response.json()["detail"]["message"] == UNKNOWN_BOOKING
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_equipment_not_in_the_review_cannot_be_flagged(self, client, officer, world):
        world.equipment.requests.append(line(22, "Requested"))
        response = changes(client, officer, bookings=(), equipment=(22,))
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == UNKNOWN_EQUIPMENT

    def test_the_assigned_coordinator_is_told(
        self, client, officer, world, notification_repository
    ):
        changes(client, officer, bookings=(BOOKING_ID,), equipment=(LINE_ID,))
        [notice] = coordinator_notices(notification_repository)
        assert notice.kind == CoordinatorNotice.SAFETY_CHANGES
