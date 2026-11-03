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

from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import pytest

from app import notifications, supabase_client
from app.booking_store import Booking, BookingStatus
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_status import EventStatus
from app.event_store import Event, StaleEventStatus, StatusChange
from app.notifications import CoordinatorNotice
from app.safety_check import SAFETY_NOTE_MAX, SafetyCheckRefusal, check_ready_for_safety_check
from app.safety_decision_store import (
    COLUMNS,
    FLAG_COLUMNS,
    InMemorySafetyDecisions,
    ReviewFlag,
    SafetyDecision,
    StaleFlag,
    SupabaseSafetyDecisions,
    to_decision,
    to_flag,
)
from app.safety_decisions import (
    CHECK_MOVED_ON,
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
    SAFETY_OFFICER_ID,
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
        assert notice.event_id == EVENT_ID
        assert notice.message == (
            'The Safety Officer requested changes to "Open House": Add a second fire exit. '
            "2 arrangements flagged for re-review."
        )

    def test_one_flag_reads_in_the_singular(self, client, officer, world, notification_repository):
        changes(client, officer)
        [notice] = coordinator_notices(notification_repository)
        assert notice.message.endswith(" 1 arrangement flagged for re-review.")

    def test_us4_4s_return_route_is_the_same_move(
        self, client, officer, world, safety_decision_repository
    ):
        response = decide(client, officer, "return", {"note": "Fix exits"})
        assert response.json()["status"] == "Planning"
        [decision] = safety_decision_repository.list_for_event(EVENT_ID)
        assert decision.outcome is SafetyOutcome.CHANGES_REQUESTED


# -- AC3: Reject ----------------------------------------------------------------


class TestReject:
    def test_back_to_planning_with_the_reason(self, client, officer, world):
        response = decide(
            client, officer, "reject",
            {"note": "  Venue unsafe for this crowd.  ", "checkStartedAt": ENTERED},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Planning"
        assert response.json()["history"][-1]["notes"] == "Venue unsafe for this crowd."

    @pytest.mark.parametrize("body", [None, {"note": ""}, {"note": " \n "}])
    def test_a_reason_is_required(self, client, officer, world, body):
        response = decide(client, officer, "reject", body)
        expected = 422 if body is None else 400
        assert response.status_code == expected
        if body is not None:
            assert response.json()["detail"]["message"] == NOTE_REQUIRED[SafetyOutcome.REJECTED]
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_a_rejection_flags_nothing(self, client, officer, world):
        response = decide(
            client, officer, "reject",
            {"note": "No", "flaggedEquipmentIds": [str(LINE_ID)]},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["message"] == FLAGS_ONLY_ON_CHANGES

    def test_the_coordinator_is_told_why(self, client, officer, world, notification_repository):
        decide(client, officer, "reject", {"note": "Venue unsafe."})
        [notice] = coordinator_notices(notification_repository)
        assert notice.kind == CoordinatorNotice.SAFETY_REJECTED
        assert notice.message == (
            'The Safety Officer rejected the safety check for "Open House": Venue unsafe.'
        )

    def test_it_is_recorded_as_a_rejection(
        self, client, officer, world, safety_decision_repository
    ):
        decide(client, officer, "reject", {"note": "Venue unsafe."})
        [decision] = safety_decision_repository.list_for_event(EVENT_ID)
        assert decision.outcome is SafetyOutcome.REJECTED


# -- Who may decide, and when ----------------------------------------------------


class TestWhoDecides:
    @pytest.mark.parametrize("action", ["approve", "request-changes", "reject"])
    @pytest.mark.parametrize(
        "role", ["Event Coordinator", "Event Organiser", "Event Coordinator Lead", "Venue Staff"]
    )
    def test_only_the_safety_officer(self, client, auth_headers, world, action, role):
        response = decide(client, auth_headers(role), action, {"note": "x"})
        assert response.status_code == 403
        assert world.events.get_event(EVENT_ID).status is PSC

    @pytest.mark.parametrize("action", ["approve", "request-changes", "reject"])
    def test_only_while_pending(self, client, officer, event_repository, action):
        seed_event(event_repository, EventStatus.PLANNING)
        response = decide(client, officer, action, {"note": "x"})
        assert response.status_code == 404

    def test_an_unknown_event(self, client, officer):
        assert decide(client, officer, "approve", event_id="nope").status_code == 404

    def test_a_check_decided_twice_is_refused(self, client, officer, world):
        assert decide(client, officer, "approve").status_code == 200
        # US4.7: still Pending Safety Check, but this stay has its decision.
        second = decide(client, officer, "reject", {"note": "Too late"})
        assert second.status_code == 409
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_a_race_lost_in_the_store_is_reported(
        self, client, officer, world, safety_decision_repository, monkeypatch
    ):
        def lost(*_args, **_kwargs):
            raise StaleEventStatus

        monkeypatch.setattr(safety_decision_repository, "record", lost)
        response = decide(client, officer, "approve")
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "This safety check was already decided. Refresh it and try again."
        )


# -- AC4: timestamped and attributable -------------------------------------------


class TestDecisionRecord:
    def test_every_decision_says_who_what_and_when(
        self, client, officer, coordinator, world
    ):
        changes(client, officer)
        [record] = client.get(
            f"/events/{EVENT_ID}/safety-decisions", headers=coordinator
        ).json()
        assert record["outcome"] == "changes-requested"
        assert record["note"] == "Add a second fire exit."
        assert record["decidedByName"] == "Alex"
        assert record["decidedAt"]
        assert record["checkStartedAt"] == ENTERED

    def test_the_audit_trail_records_it_too(self, client, officer, world):
        history = decide(client, officer, "reject", {"note": "No fire plan."}).json()["history"]
        last = history[-1]
        assert (last["from"], last["to"]) == ("Pending Safety Check", "Planning")
        assert last["byId"] == str(SAFETY_OFFICER_ID)
        assert last["byName"] == "Alex"
        assert last["at"]

    def test_an_approval_is_recorded_on_the_decision_not_as_a_move(
        self, client, officer, world, safety_decision_repository
    ):
        """US4.7: the status does not change, so the trail has nothing new; the
        decision itself is timestamped and attributable."""
        history = decide(client, officer, "approve").json()["history"]
        assert history[-1]["to"] == "Pending Safety Check"
        (decision,) = safety_decision_repository.list_for_event(EVENT_ID)
        assert decision.outcome is SafetyOutcome.APPROVED
        assert (decision.decided_by_id, decision.decided_by_name) == (SAFETY_OFFICER_ID, "Alex")
        assert decision.decided_at

    def test_decisions_come_newest_first_with_their_flags(
        self, client, officer, coordinator, world, safety_decision_repository
    ):
        changes(client, officer, bookings=(BOOKING_ID,), equipment=(LINE_ID,))
        records = client.get(f"/events/{EVENT_ID}/safety-decisions", headers=coordinator).json()
        flags = records[0]["flags"]
        assert flags[0] == {
            "id": flags[0]["id"],
            "target": "booking",
            "targetId": str(BOOKING_ID),
            "label": "Great Hall",
            "status": "Confirmed",
            "startsAt": "2099-11-02T09:00",
            "endsAt": "2099-11-02T17:00",
            "resolvedAt": "",
            "resolvedByName": "",
        }
        assert flags[1]["target"] == "equipment"
        assert flags[1]["label"] == "Projector × 2"
        assert flags[1]["status"] == RESERVED

    def test_a_flagged_arrangement_that_has_gone_is_still_described(
        self, client, officer, coordinator, world
    ):
        changes(client, officer, bookings=(BOOKING_ID,), equipment=(LINE_ID,))
        world.bookings.bookings.clear()
        world.equipment.requests.clear()
        flags = client.get(
            f"/events/{EVENT_ID}/safety-decisions", headers=coordinator
        ).json()[0]["flags"]
        assert [flag["label"] for flag in flags] == [
            "A venue booking that no longer exists",
            "An equipment request that no longer exists",
        ]
        assert [flag["status"] for flag in flags] == ["", ""]

    def test_an_event_never_checked_has_no_decisions(self, client, coordinator, event_repository):
        seed_event(event_repository, EventStatus.PLANNING)
        assert client.get(
            f"/events/{EVENT_ID}/safety-decisions", headers=coordinator
        ).json() == []

    def test_another_coordinator_cannot_read_them(self, client, coordinator, event_repository):
        seed_event(event_repository, EventStatus.PLANNING, coordinator_id=99)
        response = client.get(f"/events/{EVENT_ID}/safety-decisions", headers=coordinator)
        assert response.status_code == 404

    def test_the_safety_officer_reads_them_while_the_event_waits(
        self, client, officer, event_repository
    ):
        seed_event(event_repository)
        assert client.get(f"/events/{EVENT_ID}/safety-decisions", headers=officer).json() == []
        event_repository.events.clear()
        seed_event(event_repository, EventStatus.PLANNING)
        response = client.get(f"/events/{EVENT_ID}/safety-decisions", headers=officer)
        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["Event Organiser", "Venue Staff", "Technical Support"])
    def test_nobody_else_reads_them(self, client, auth_headers, world, role):
        response = client.get(f"/events/{EVENT_ID}/safety-decisions", headers=auth_headers(role))
        assert response.status_code == 403


# -- Re-review: the flags in the Coordinator's hands ------------------------------


def flag_ids(client, coordinator):
    records = client.get(f"/events/{EVENT_ID}/safety-decisions", headers=coordinator).json()
    return [flag["id"] for flag in records[0]["flags"]]


def resolve(client, headers, flag_id, event_id=EVENT_ID):
    return client.post(f"/events/{event_id}/safety-flags/{flag_id}/resolve", headers=headers)


class TestReReview:
    def test_open_flags_keep_the_event_from_being_sent_again(
        self, client, officer, coordinator, world
    ):
        changes(client, officer)
        readiness = client.get(f"/events/{EVENT_ID}/safety-check", headers=coordinator).json()
        assert readiness["ready"] is False
        assert readiness["reason"] == "safety-flags-open"
        sent = client.post(f"/events/{EVENT_ID}/safety-check", headers=coordinator)
        assert sent.status_code == 409
        assert sent.json()["detail"]["reason"] == "safety-flags-open"

    def test_the_coordinator_marks_each_one_re_reviewed(
        self, client, officer, coordinator, world
    ):
        changes(client, officer)
        [flag_id] = flag_ids(client, coordinator)
        response = resolve(client, coordinator, flag_id)
        assert response.status_code == 200, response.text
        assert response.json()["resolvedByName"] == "Priya"
        assert response.json()["resolvedAt"]
        readiness = client.get(f"/events/{EVENT_ID}/safety-check", headers=coordinator).json()
        assert readiness["ready"] is True

    def test_a_flag_is_resolved_once(self, client, officer, coordinator, world):
        changes(client, officer)
        [flag_id] = flag_ids(client, coordinator)
        resolve(client, coordinator, flag_id)
        again = resolve(client, coordinator, flag_id)
        assert again.status_code == 409
        assert again.json()["detail"]["reason"] == "flag-resolved"

    @pytest.mark.parametrize("flag_id", ["999", "abc"])
    def test_an_unknown_flag(self, client, officer, coordinator, world, flag_id):
        changes(client, officer)
        response = resolve(client, coordinator, flag_id)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "safety_flag_not_found"

    def test_another_events_flag_is_not_this_ones(
        self, client, officer, coordinator, world, event_repository
    ):
        changes(client, officer)
        [flag_id] = flag_ids(client, coordinator)
        seed_event(event_repository, EventStatus.PLANNING, event_id=OTHER_EVENT_ID)
        response = resolve(client, coordinator, flag_id, event_id=OTHER_EVENT_ID)
        assert response.status_code == 404

    def test_only_while_planning(
        self, client, officer, coordinator, world, event_repository, safety_decision_repository
    ):
        changes(client, officer)
        [flag_id] = flag_ids(client, coordinator)
        event = event_repository.get_event(EVENT_ID)
        event_repository._replace(replace(event, status=EventStatus.CANCELLED))
        response = resolve(client, coordinator, flag_id)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-planning"
        assert safety_decision_repository.get_flag(int(flag_id)).is_open

    def test_only_the_assigned_coordinator(self, client, officer, auth_headers, world):
        changes(client, officer)
        response = resolve(client, auth_headers("Safety Officer"), "1")
        assert response.status_code == 403

    def test_a_race_lost_in_the_store_is_reported(
        self, client, officer, coordinator, world, safety_decision_repository, monkeypatch
    ):
        changes(client, officer)
        [flag_id] = flag_ids(client, coordinator)

        def lost(*_args, **_kwargs):
            raise StaleFlag

        monkeypatch.setattr(safety_decision_repository, "resolve_flag", lost)
        assert resolve(client, coordinator, flag_id).status_code == 409


# -- AC5: a fresh decision each time ----------------------------------------------


class TestFreshDecision:
    def resend(self, client, officer, coordinator):
        """Request changes, re-review every flag, and send the event again."""
        changes(client, officer)
        for flag_id in flag_ids(client, coordinator):
            resolve(client, coordinator, flag_id)
        sent = client.post(f"/events/{EVENT_ID}/safety-check", headers=coordinator)
        assert sent.status_code == 200, sent.text
        return sent.json()

    def test_a_returned_event_comes_back_undecided(self, client, officer, coordinator, world):
        resent = self.resend(client, officer, coordinator)
        assert resent["status"] == "Pending Safety Check"
        queue = client.get("/events/safety-check", headers=officer).json()
        assert [event["id"] for event in queue] == [str(EVENT_ID)]

    def test_a_decision_on_the_earlier_submission_is_refused(
        self, client, officer, coordinator, world
    ):
        self.resend(client, officer, coordinator)
        stale = decide(client, officer, "approve", {"checkStartedAt": ENTERED})
        assert stale.status_code == 409
        assert stale.json()["detail"] == {
            "code": "rule_refused",
            "message": CHECK_MOVED_ON,
            "reason": "check-moved-on",
        }
        assert world.events.get_event(EVENT_ID).status is PSC

    def test_a_decision_on_the_current_submission_lands(
        self, client, officer, coordinator, world, safety_decision_repository
    ):
        self.resend(client, officer, coordinator)
        review = client.get(f"/events/{EVENT_ID}/safety-review", headers=officer).json()
        approved = decide(client, officer, "approve", {"checkStartedAt": review["waitingSince"]})
        assert approved.json()["safetyApproved"] is True
        newest, earlier = safety_decision_repository.list_for_event(EVENT_ID)
        assert newest.outcome is SafetyOutcome.APPROVED
        assert newest.check_started_at == review["waitingSince"]
        assert earlier.check_started_at == ENTERED

    def test_a_check_time_that_is_not_a_time_is_a_bad_request(self, client, officer, world):
        response = decide(client, officer, "approve", {"checkStartedAt": "last Tuesday"})
        assert response.status_code == 400
        assert world.events.get_event(EVENT_ID).status is PSC


# -- The stores -------------------------------------------------------------------


class TestInMemoryStore:
    def record(self, store, **overrides):
        arguments = {
            "officer_id": SAFETY_OFFICER_ID,
            "outcome": SafetyOutcome.CHANGES_REQUESTED,
            "note": "Fix exits",
            "check_started_at": ENTERED,
            "booking_ids": (BOOKING_ID, BOOKING_ID),
            "equipment_ids": (LINE_ID,),
            **overrides,
        }
        return store.record(EVENT_ID, **arguments)

    def test_records_moves_and_flags_once_each(self, event_repository):
        seed_event(event_repository)
        store = InMemorySafetyDecisions(names={SAFETY_OFFICER_ID: "Alex"})
        decision = self.record(store)
        assert decision.decided_by_name == "Alex"
        assert decision.decided_at == event_repository.get_event(EVENT_ID).updated_at
        assert [flag.id for flag in decision.flags] == [1, 2]
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

    def test_an_empty_check_time_skips_the_comparison(self, event_repository):
        seed_event(event_repository)
        store = InMemorySafetyDecisions()
        decision = self.record(store, check_started_at="", booking_ids=(), equipment_ids=())
        assert decision.check_started_at == ENTERED
        assert decision.decided_by_name == ""

    def test_refuses_a_missing_or_undecidable_event(self, event_repository):
        store = InMemorySafetyDecisions()
        with pytest.raises(StaleEventStatus):
            self.record(store)
        seed_event(event_repository, EventStatus.PLANNING)
        with pytest.raises(StaleEventStatus):
            self.record(store)

    def test_refuses_a_later_stay(self, event_repository):
        seed_event(event_repository)
        with pytest.raises(StaleEventStatus):
            self.record(InMemorySafetyDecisions(), check_started_at="2099-01-01T00:00:00")

    def test_lists_one_events_decisions_newest_first(self, event_repository):
        store = InMemorySafetyDecisions(
            decisions=[
                SafetyDecision(1, EVENT_ID, SafetyOutcome.REJECTED, "a", 5, "", "2099-01-01", ""),
                SafetyDecision(2, OTHER_EVENT_ID, SafetyOutcome.APPROVED, "", 5, "", "2099-01-03",
                               ""),
                SafetyDecision(3, EVENT_ID, SafetyOutcome.APPROVED, "", 5, "", "2099-01-02", ""),
            ]
        )
        assert [item.id for item in store.list_for_event(EVENT_ID)] == [3, 1]

    def test_resolves_an_open_flag_once_and_only_on_its_event(self, event_repository):
        seed_event(event_repository)
        store = InMemorySafetyDecisions(names={COORDINATOR_ID: "Priya"})
        self.record(store)
        assert store.get_flag(99) is None
        with pytest.raises(StaleFlag):
            store.resolve_flag(1, event_id=OTHER_EVENT_ID, actor_id=COORDINATOR_ID)
        with pytest.raises(StaleFlag):
            store.resolve_flag(99, event_id=EVENT_ID, actor_id=COORDINATOR_ID)
        resolved = store.resolve_flag(1, event_id=EVENT_ID, actor_id=COORDINATOR_ID)
        assert (resolved.resolved_by_id, resolved.resolved_by_name) == (COORDINATOR_ID, "Priya")
        assert not store.get_flag(1).is_open
        assert store.get_flag(2).is_open
        with pytest.raises(StaleFlag):
            store.resolve_flag(1, event_id=EVENT_ID, actor_id=COORDINATOR_ID)


FLAG_ROW = {
    "id": 4,
    "decision_id": 3,
    "event_id": EVENT_ID,
    "booking_id": BOOKING_ID,
    "equipment_request_id": None,
    "resolved_at": None,
    "resolved_by_id": None,
    "resolved_by": None,
}
DECISION_ROW = {
    "id": 3,
    "event_id": EVENT_ID,
    "outcome": "changes-requested",
    "note": "Fix exits",
    "decided_by_id": SAFETY_OFFICER_ID,
    "decided_at": "2099-01-02T11:00:00",
    "check_started_at": ENTERED,
    "decided_by": {"name": "Alex"},
    "safety_review_flags": [
        {**FLAG_ROW, "id": 5, "booking_id": None, "equipment_request_id": LINE_ID},
        FLAG_ROW,
    ],
}


@dataclass
class FakeAdmin:
    """A PostgREST client that records each call and answers with what it is given."""

    rows: list[dict] | None = field(default_factory=list)
    rpc_result: object = None
    calls: list[tuple] = field(default_factory=list)

    def rpc(self, name, arguments):
        self.calls.append(("rpc", name, arguments))
        self._answer = self.rpc_result
        return self

    def table(self, name):
        self.calls.append(("table", name))
        self._answer = self.rows
        return self

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, *args, *kwargs.values()))
            return self

        return call

    def execute(self):
        return SimpleNamespace(data=self._answer)


class TestSupabaseStore:
    @pytest.fixture
    def admin(self, monkeypatch):
        fake = FakeAdmin()
        monkeypatch.setattr(supabase_client, "admin", lambda: fake)
        return fake

    def test_rows_become_decisions_and_flags(self):
        decision = to_decision(DECISION_ROW)
        assert decision.outcome is SafetyOutcome.CHANGES_REQUESTED
        assert decision.decided_by_name == "Alex"
        assert [flag.id for flag in decision.flags] == [4, 5]
        assert to_decision({**DECISION_ROW, "note": None, "safety_review_flags": None}).note == ""

    def test_a_joined_name_may_come_as_a_list_or_not_at_all(self):
        resolved = {**FLAG_ROW, "resolved_at": "2099-01-03T09:00:00", "resolved_by_id": 2}
        assert to_flag({**resolved, "resolved_by": [{"name": "Priya"}]}).resolved_by_name == "Priya"
        assert to_flag({**resolved, "resolved_by": []}).resolved_by_name == ""
        assert to_flag(FLAG_ROW) == ReviewFlag(4, 3, EVENT_ID, booking_id=BOOKING_ID)

    def test_record_is_one_rpc(self, admin):
        admin.rpc_result = 3
        admin.rows = [DECISION_ROW]
        decision = SupabaseSafetyDecisions().record(
            EVENT_ID,
            officer_id=SAFETY_OFFICER_ID,
            outcome=SafetyOutcome.CHANGES_REQUESTED,
            note="Fix exits",
            check_started_at=ENTERED,
            booking_ids=(BOOKING_ID,),
            equipment_ids=(LINE_ID,),
        )
        assert decision.id == 3
        assert admin.calls[0] == (
            "rpc",
            "record_safety_decision",
            {
                "p_event_id": EVENT_ID,
                "p_outcome": "changes-requested",
                "p_officer_id": SAFETY_OFFICER_ID,
                "p_note": "Fix exits",
                "p_check_started_at": ENTERED,
                "p_booking_ids": [BOOKING_ID],
                "p_equipment_ids": [LINE_ID],
            },
        )

    def test_an_empty_note_and_check_time_go_as_null(self, admin):
        admin.rpc_result = 3
        admin.rows = [DECISION_ROW]
        SupabaseSafetyDecisions().record(
            EVENT_ID, officer_id=SAFETY_OFFICER_ID, outcome=SafetyOutcome.APPROVED, note="",
            check_started_at="", booking_ids=(), equipment_ids=(),
        )
        arguments = admin.calls[0][2]
        assert arguments["p_note"] is None
        assert arguments["p_check_started_at"] is None

    @pytest.mark.parametrize("answer", [None, False])
    def test_a_refused_record_is_stale(self, admin, answer):
        admin.rpc_result = answer
        with pytest.raises(StaleEventStatus):
            SupabaseSafetyDecisions().record(
                EVENT_ID, officer_id=SAFETY_OFFICER_ID, outcome=SafetyOutcome.APPROVED,
                note="", check_started_at="", booking_ids=(), equipment_ids=(),
            )

    def test_list_is_newest_first(self, admin):
        admin.rows = [DECISION_ROW]
        assert [item.id for item in SupabaseSafetyDecisions().list_for_event(EVENT_ID)] == [3]
        assert admin.calls == [
            ("table", "safety_reviews"),
            ("select", COLUMNS),
            ("eq", "event_id", EVENT_ID),
            ("order", "decided_at", True),
            ("order", "id", True),
        ]
        admin.rows = None
        assert SupabaseSafetyDecisions().list_for_event(EVENT_ID) == []

    def test_get_flag(self, admin):
        admin.rows = [FLAG_ROW]
        assert SupabaseSafetyDecisions().get_flag(4).id == 4
        assert ("select", FLAG_COLUMNS) in admin.calls
        admin.rows = []
        assert SupabaseSafetyDecisions().get_flag(4) is None

    def test_resolve_only_an_open_flag_on_its_event(self, admin, monkeypatch):
        store = SupabaseSafetyDecisions()
        admin.rows = [FLAG_ROW]
        marker = ReviewFlag(4, 3, EVENT_ID, resolved_at="now", resolved_by_id=COORDINATOR_ID)
        monkeypatch.setattr(store, "get_flag", lambda _id: marker)
        assert store.resolve_flag(4, event_id=EVENT_ID, actor_id=COORDINATOR_ID) is marker
        update = next(call for call in admin.calls if call[0] == "update")
        assert update[1]["resolved_by_id"] == COORDINATOR_ID
        assert ("eq", "event_id", EVENT_ID) in admin.calls
        assert ("is_", "resolved_at", "null") in admin.calls
        admin.rows = []
        with pytest.raises(StaleFlag):
            store.resolve_flag(4, event_id=EVENT_ID, actor_id=COORDINATOR_ID)


class TestNotices:
    def test_no_flags_says_nothing_about_flags(self, notification_repository, event_repository):
        event = seed_event(event_repository)
        notifications.notify_safety_changes(event, "Fix exits")
        [notice] = notification_repository.notifications
        assert notice.message == 'The Safety Officer requested changes to "Open House": Fix exits'
