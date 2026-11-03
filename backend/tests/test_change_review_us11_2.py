"""US11.2 happy, negative, boundary and cross-feature regression coverage."""

from dataclasses import replace

import pytest

from app import arrangement_review, supabase_client
from app.booking_store import Booking, BookingStatus
from app.equipment_store import Equipment, EquipmentRequest
from app.event_status import EventStatus
from app.event_store import SupabaseEvents
from tests.conftest import COORDINATOR_ID, ORGANISER_ID
from tests.test_change_requests import DRAFT, seed

COORD = "Event Coordinator"
OWNER = "Event Organiser"


def submit(client, auth_headers, event, revision=None, **changes):
    return client.post(
        f"/events/{event.id}/change-request",
        headers=auth_headers(OWNER),
        json={**DRAFT, **changes, "reviewRevision": revision},
    )


def question(client, auth_headers, event, revision=None):
    return client.post(
        f"/events/{event.id}/clarification",
        headers=auth_headers(COORD),
        json={"message": "Please amend attendance.", "reviewRevision": revision},
    )


#: Confirmed is not here: US11.3 sends it back to Planning when, as here, an
#: important field changes (tests/test_reconfirm_us11_3.py).
@pytest.mark.parametrize(
    "status",
    [
        EventStatus.SUBMITTED,
        EventStatus.APPROVED,
        EventStatus.PLANNING,
        EventStatus.PENDING_SAFETY_CHECK,
    ],
)
def test_request_question_revision_and_accept_preserve_status(
    client,
    auth_headers,
    event_repository,
    notification_repository,
    status,
):
    event = seed(event_repository, status=status)
    first = submit(client, auth_headers, event, 0, expectedAttendance=100)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == status
    assert first.json()["expectedAttendance"] == 50
    # Each new question enables exactly one amendment, even with a pending proposal.
    for revision, attendance in [(1, 120), (3, 150), (5, 180)]:
        asked = question(client, auth_headers, event, revision)
        assert asked.status_code == 200, asked.text
        assert asked.json()["awaitingReply"]
        replied = submit(client, auth_headers, event, revision + 1, expectedAttendance=attendance)
        assert replied.status_code == 200, replied.text
        assert not replied.json()["awaitingReply"]
        assert replied.json()["status"] == status
    stale = client.post(
        f"/events/{event.id}/change-request/approve?review_revision=1", headers=auth_headers(COORD)
    )
    assert stale.status_code == 409
    accepted = client.post(
        f"/events/{event.id}/change-request/approve?review_revision=7", headers=auth_headers(COORD)
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["expectedAttendance"] == 180
    assert not accepted.json()["changeRequested"]
    assert accepted.json()["status"] == status
    history = accepted.json()["reviewHistory"]
    assert [entry["kind"] for entry in history].count("proposal") == 4
    assert [entry["kind"] for entry in history].count("clarification") == 3
    assert history[-2]["clarificationId"] == history[-3]["clarificationId"]
    assert any(row_status == "superseded" for _, _, row_status in event_repository.change_requests)
    notices = notification_repository.list_for_user(ORGANISER_ID)
    assert len([n for n in notices if "more information" in n.message]) == 3
    assert "accepted" in notices[0].message
    assert len(notification_repository.list_for_user(COORDINATOR_ID)) == 4


def test_under_review_requires_question_and_field_amendment(client, auth_headers, event_repository):
    event = seed(event_repository, status=EventStatus.UNDER_REVIEW)
    assert submit(client, auth_headers, event).status_code == 409
    assert question(client, auth_headers, event).status_code == 200
    reply = submit(client, auth_headers, event, 1, expectedAttendance=75)
    assert reply.status_code == 200
    assert reply.json()["status"] == "Under Review"
    assert submit(client, auth_headers, event, 2, expectedAttendance=80).status_code == 409






def booking(event_id, **overrides):
    values = dict(
        id=1,
        event_id=event_id,
        venue_id=2,
        venue_name="Bertha Room",
        starts_at="2027-11-02T18:00",
        ends_at="2027-11-02T21:00",
        status=BookingStatus.CONFIRMED,
        requested_by_id=COORDINATOR_ID,
        requested_at="2026-10-01T00:00",
        headcount=30,
    )
    return Booking(**{**values, **overrides})


def reservation(event_id, **overrides):
    values = dict(
        id=1,
        event_id=event_id,
        equipment_type="Projector",
        quantity=2,
        technical_requirements="",
        support_notes="",
        starts_at="2027-11-02T18:00",
        ends_at="2027-11-02T21:00",
        status="Reserved",
        requested_by_id=COORDINATOR_ID,
        created_at="2026-10-01T00:00",
        version=1,
        equipment_id=1,
        requested_equipment_id=1,
    )
    return EquipmentRequest(**{**values, **overrides})




@pytest.mark.parametrize("competing,shortfall", [(0, False), (1, True)])
def test_stock_boundary_excludes_own_reservation(
    event_repository,
    equipment_repository,
    competing,
    shortfall,
):
    event = seed(event_repository)
    equipment_repository.items = [Equipment(1, "Projector", "Projector", "", "Store", 2, 0, "")]
    equipment_repository.requests = [reservation(event.id)]
    if competing:
        equipment_repository.requests.append(reservation(999, id=2, quantity=1))
    result = arrangement_review.recheck(event)
    assert bool(equipment_repository.get_request(1).event_conflict_reason) == shortfall
    assert not result.arrangement_review_pending
    assert equipment_repository.get_request(1).status == "Reserved"




def test_partial_failure_is_visible_and_retryable(
    client,
    auth_headers,
    event_repository,
    booking_repository,
    equipment_repository,
    monkeypatch,
):
    event = seed(event_repository, expected_attendance=41)
    booking_repository.bookings = [booking(event.id)]
    equipment_repository.requests = [reservation(event.id)]
    original = equipment_repository.reservation_availability
    monkeypatch.setattr(
        equipment_repository,
        "reservation_availability",
        lambda _: (_ for _ in ()).throw(RuntimeError()),
    )
    failed = arrangement_review.recheck(event)
    assert failed.arrangement_review_pending
    assert any(r["error"] for r in failed.arrangement_review)
    assert booking_repository.get_booking(1).event_conflict_reason
    monkeypatch.setattr(equipment_repository, "reservation_availability", original)
    response = client.post(f"/events/{event.id}/arrangements/recheck", headers=auth_headers(COORD))
    assert response.status_code == 200
    assert not response.json()["arrangementReviewPending"]
    assert (
        client.post(
            f"/events/{event.id}/arrangements/recheck", headers=auth_headers(OWNER)
        ).status_code
        == 403
    )


def test_direct_edit_and_accept_use_same_checks(
    client, auth_headers, event_repository, booking_repository
):
    event = seed(event_repository, expected_attendance=40)
    booking_repository.bookings = [booking(event.id)]
    saved = client.put(
        f"/events/{event.id}", headers=auth_headers(COORD), json={**DRAFT, "expectedAttendance": 41}
    )
    assert saved.status_code == 200, saved.text
    assert booking_repository.get_booking(1).event_conflict_reason
    proposed = submit(client, auth_headers, event, expectedAttendance=40)
    assert proposed.status_code == 200
    # Direct edit cannot invalidate a proposal.
    assert (
        client.put(f"/events/{event.id}", headers=auth_headers(COORD), json=DRAFT).status_code
        == 409
    )
    accepted = client.post(
        f"/events/{event.id}/change-request/approve", headers=auth_headers(COORD)
    )
    assert accepted.status_code == 200
    assert not booking_repository.get_booking(1).event_conflict_reason
    assert any(
        c.field == "expected_attendance" and c.important for _, c in event_repository.change_log
    )






def test_cancelled_booking_clears_event_conflict_and_report(
    client,
    auth_headers,
    event_repository,
    booking_repository,
):
    event = seed(event_repository, status=EventStatus.PLANNING, expected_attendance=41)
    booking_repository.bookings = [booking(event.id, status=BookingStatus.REQUESTED)]
    arrangement_review.recheck(event)
    assert booking_repository.get_booking(1).event_conflict_reason
    response = client.post(
        f"/events/{event.id}/bookings/1/cancel",
        headers=auth_headers(COORD),
        json={"reason": "Rearranging the venue"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["conflict"] is None
    assert not event_repository.get_event(event.id).arrangement_review




@pytest.mark.parametrize("old_end,new_end", [("22:00", "21:00"), ("21:00", "22:00")])
def test_older_recheck_cannot_overwrite_newer_flags_or_report(
    event_repository,
    booking_repository,
    equipment_repository,
    monkeypatch,
    old_end,
    new_end,
):
    event = seed(event_repository, expected_attendance=40, ends_at=f"2027-11-02T{old_end}")
    booking_repository.bookings = [booking(event.id)]
    equipment_repository.items = [Equipment(1, "Projector", "Projector", "", "Store", 2, 0, "")]
    equipment_repository.requests = [reservation(event.id)]
    original = equipment_repository.reservation_availability
    interleave = True

    def finish_newer_check(request_id):
        nonlocal interleave
        if interleave:
            interleave = False
            newer = replace(
                event,
                ends_at=f"2027-11-02T{new_end}",
                updated_at="2026-10-31T12:00:00",
                arrangement_review_pending=True,
            )
            event_repository._replace(newer)
            arrangement_review.recheck(newer)
        return original(request_id)

    monkeypatch.setattr(equipment_repository, "reservation_availability", finish_newer_check)
    result = arrangement_review.recheck(event)
    assert result.ends_at == f"2027-11-02T{new_end}"
    assert not result.arrangement_review_pending
    expected_failure = new_end == "22:00"
    assert bool(booking_repository.get_booking(1).event_conflict_reason) == expected_failure
    assert bool(equipment_repository.get_request(1).event_conflict_reason) == expected_failure
    assert all(bool(item["reason"]) == expected_failure for item in result.arrangement_review)




@pytest.mark.parametrize(
    "failure,reason",
    [
        ("venue", "venue-conflict"),
        ("equipment", "equipment-conflict"),
        ("pending", "arrangement-review-pending"),
    ],
)
def test_event_change_conflicts_and_incomplete_checks_block_safety(
    client,
    auth_headers,
    event_repository,
    booking_repository,
    equipment_repository,
    failure,
    reason,
):
    event = seed(
        event_repository,
        status=EventStatus.PLANNING,
        arrangement_review_pending=failure == "pending",
    )
    booking_repository.bookings = [
        booking(event.id, event_conflict_reason="Over capacity" if failure == "venue" else "")
    ]
    equipment_repository.requests = [
        reservation(
            event.id, event_conflict_reason="Stock shortfall" if failure == "equipment" else ""
        )
    ]
    headers = auth_headers(COORD)
    readiness = client.get(f"/events/{event.id}/safety-check", headers=headers)
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is False
    assert readiness.json()["reason"] == reason
    assert client.post(f"/events/{event.id}/safety-check", headers=headers).status_code == 409
    assert event_repository.get_event(event.id).status == EventStatus.PLANNING


def test_supabase_publishes_flags_and_report_through_one_guarded_rpc(
    event_repository,
    monkeypatch,
):
    from tests.test_change_requests import FakeAdmin

    event = seed(event_repository)
    admin = FakeAdmin(True)
    store = SupabaseEvents()
    monkeypatch.setattr(supabase_client, "admin", lambda: admin)
    monkeypatch.setattr(store, "get_event", lambda _: event)
    flags = [{"id": 1, "reason": "Over capacity"}]
    report = [{"id": "1", "reason": "Over capacity"}]
    store.set_arrangement_review(
        event.id, report, False, expected_updated_at=event.updated_at, booking_flags=flags
    )
    assert admin.calls == [
        (
            "us11_commit_arrangement_review",
            {
                "p_event_id": event.id,
                "p_updated_at": event.updated_at,
                "p_report": report,
                "p_pending": False,
                "p_booking_flags": flags,
                "p_equipment_flags": [],
            },
        )
    ]
    assert admin.queries == []
