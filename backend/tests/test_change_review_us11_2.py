"""US11.2 happy, negative, boundary and cross-feature regression coverage."""


import pytest

from app.booking_store import Booking, BookingStatus
from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus
from tests.conftest import COORDINATOR_ID
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


#: Confirmed and Pending Safety Check are not here: an important field change, as
#: here, sends them back to Planning (tests/test_reconfirm_us11_3.py and
#: tests/test_safety_approval_after_change.py, CODE_AUDIT.md D1).








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




def test_what_now_fails_is_flagged_not_cancelled_and_the_coordinator_is_told(
    client, auth_headers, event_repository, booking_repository, notification_repository
):
    """US11.2 AC5: an edit that breaks a booking flags it, keeps it and tells the Coordinator."""
    event = seed(event_repository, expected_attendance=40)
    booking_repository.bookings = [booking(event.id)]

    saved = client.put(
        f"/events/{event.id}", headers=auth_headers(COORD), json={**DRAFT, "expectedAttendance": 41}
    )

    assert saved.status_code == 200, saved.text
    flagged = booking_repository.get_booking(1)
    assert flagged.event_conflict_reason
    assert flagged.status == BookingStatus.CONFIRMED
    told = [
        (notice.user_id, notice.message)
        for notice in notification_repository.notifications
        if notice.kind == "arrangement-conflict"
    ]
    assert told == [
        (
            COORDINATOR_ID,
            'Arrangements for "Faculty Welcome Night" need review: Venue booking #1 '
            "(Bertha Room): It holds 40 people, and this booking is for 41.",
        )
    ]
