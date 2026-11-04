"""US17.2: the Safety Officer records a decision.

Acceptance criteria, and the tests that hold each one:

* Approve -> the decision is recorded as approved on the current Pending Safety
  Check stay, and the event stays Pending Safety Check ("Safety approved,
  awaiting Coordinator confirmation" in the app) until the assigned
  Coordinator confirms it (US4.7) -> `TestApprove`. The story's test is
  `test_approving_leaves_it_pending_with_an_approved_decision_recorded`. The
  Sprint 4 criterion "Approve -> Confirmed" was replaced in Sprint 5.
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

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app import supabase_client
from app.booking_store import Booking, BookingStatus
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_status import EventStatus
from app.event_store import Event, StaleEventStatus, StatusChange
from app.notifications import CoordinatorNotice
from app.safety_decision_store import (
    COLUMNS,
    FLAG_COLUMNS,
    ReviewFlag,
    StaleFlag,
    SupabaseSafetyDecisions,
    to_flag,
)
from app.safety_decisions import (
    CHECK_MOVED_ON,
    NOTE_REQUIRED,
    SafetyOutcome,
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




# -- AC1: Approve -> stays Pending Safety Check, approved (Sprint 5) ------------


class TestApprove:
    def test_approving_leaves_it_pending_with_an_approved_decision_recorded(
        self, client, officer, world, safety_decision_repository
    ):
        """The story's test: approved, on this stay, and still waiting for the Coordinator."""
        response = decide(client, officer, "approve", {"checkStartedAt": ENTERED})

        assert response.json()["status"] == "Pending Safety Check"
        assert world.events.get_event(EVENT_ID).status is PSC
        (decision,) = safety_decision_repository.list_for_event(EVENT_ID)
        assert decision.outcome is SafetyOutcome.APPROVED
        assert decision.check_started_at == ENTERED






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


    def test_the_coordinator_is_told_why(self, client, officer, world, notification_repository):
        decide(client, officer, "reject", {"note": "Venue unsafe."})
        [notice] = coordinator_notices(notification_repository)
        assert notice.kind == CoordinatorNotice.SAFETY_REJECTED
        assert notice.message == (
            'The Safety Officer rejected the safety check for "Open House": Venue unsafe.'
        )



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




# -- The stores -------------------------------------------------------------------




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



