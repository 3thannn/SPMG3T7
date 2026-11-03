"""US14.5: filtered availability, replacement history, and unrelated bookings."""

from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app import supabase_client
from app.booking_store import (
    Booking,
    BookingStatus,
    Decision,
    SlotTaken,
    StaleBookingStatus,
    SupabaseBookings,
)
from app.event_status import EventStatus
from app.venue_unavailability_store import UnavailabilityReasonType
from tests.conftest import COORDINATOR_ID
from tests.test_venue_bookings import seed_event


@pytest.fixture
def scenario(event_repository, booking_repository):
    event = seed_event(event_repository, status=EventStatus.PLANNING)
    day = datetime.now().date() + timedelta(days=30)
    original = Booking(
        id=10, event_id=event.id, venue_id=1, venue_name="Great Hall",
        starts_at=f"{day}T09:00", ends_at=f"{day}T17:00",
        status=BookingStatus.NEEDS_REPLACEMENT, requested_by_id=COORDINATOR_ID,
        requested_at="2026-10-01T10:00:00", headcount=30,
        required_layout="Theatre", required_facilities=("projector",),
        accessibility_needs=("Step-free access",), replacement_reason="Flooding",
        decision=Decision(at="2026-10-01T11:00:00", by_id=4, by_name="Sam"),
    )
    other = replace(
        original, id=11, venue_id=3, status=BookingStatus.REQUESTED, decision=None,
        starts_at=f"{day}T18:00", ends_at=f"{day}T19:00",
    )
    booking_repository.bookings.extend([original, other])
    return original, other


def search(client, headers, **params):
    return client.get("/bookings/10/replacement-venues", headers=headers, params=params)


def request_replacement(client, headers, venue_id="2"):
    return client.post("/bookings/10/request-replacement", headers=headers,
                       json={"venueId": venue_id})


@pytest.mark.parametrize(("filters", "expected"), [
    ({}, ["2", "3"]),
    ({"minCapacity": "50"}, ["3"]),
    ({"location": " level 3 "}, ["2"]),
    ({"accessibility": " STEP-FREE "}, ["3"]),
    ({"minCapacity": "50", "location": "LIBRARY", "accessibility": "step-free"}, ["3"]),
    ({"minCapacity": "50", "location": "Level 3"}, []),
    ({"minCapacity": "", "location": "  ", "accessibility": ""}, ["2", "3"]),
])
def test_filters_combine_with_same_time_availability(
    client, auth_headers, scenario, filters, expected
):
    response = search(client, auth_headers("Event Coordinator"), **filters)
    assert response.status_code == 200
    assert [venue["id"] for venue in response.json()] == expected


@pytest.mark.parametrize("filters", [
    {"minCapacity": "-1"}, {"minCapacity": "abc"},
    {"location": "x" * 201}, {"accessibility": "x" * 201},
])
def test_bad_filters_are_rejected(client, auth_headers, scenario, filters):
    assert search(client, auth_headers("Event Coordinator"), **filters).status_code == 400


def test_conflicts_and_blackouts_excluded(
    client, auth_headers, scenario, booking_repository, unavailability_repository
):
    original, _ = scenario
    booking_repository.bookings.append(replace(
        original, id=12, event_id=901, venue_id=2, status=BookingStatus.REQUESTED,
    ))
    day = datetime.fromisoformat(original.starts_at).date()
    unavailability_repository.create(
        venue_id=3, start_date=day, end_date=day,
        reason_type=UnavailabilityReasonType.MAINTENANCE, other_reason="", created_by_id=4,
    )
    headers = auth_headers("Event Coordinator")
    assert search(client, headers).json() == []
    assert request_replacement(client, headers).status_code == 400
    assert request_replacement(client, headers, "3").status_code == 400
    assert booking_repository.get_booking(10) == original
    assert len(booking_repository.bookings) == 3


def test_replacement_copies_needs_and_preserves_history_and_other_bookings(
    client, auth_headers, scenario, booking_repository, event_repository
):
    original, other = scenario
    event_before = event_repository.get_event(original.event_id)
    headers = auth_headers("Event Coordinator")
    response = request_replacement(client, headers)
    assert response.status_code == 201, response.text
    new = booking_repository.get_booking(int(response.json()["id"]))
    assert new.status is BookingStatus.REQUESTED
    assert new.venue_id == 2
    for attribute in ("event_id", "starts_at", "ends_at", "headcount", "required_layout",
                      "required_facilities", "accessibility_needs"):
        assert getattr(new, attribute) == getattr(original, attribute)
    assert new.decision is None
    assert new.replacement_reason == ""
    assert booking_repository.get_booking(10) == replace(original, status=BookingStatus.REPLACED)
    assert booking_repository.get_booking(11) == other
    assert event_repository.get_event(original.event_id) == event_before
    assert len(booking_repository.bookings) == 3
    assert request_replacement(client, headers, "3").status_code == 409
    assert search(client, headers).status_code == 409
    assert len(booking_repository.bookings) == 3
    assert not booking_repository.get_booking(10).holds_venue


@pytest.mark.parametrize("venue_id", ["1", "999", "nonsense", ""])
def test_invalid_or_original_venue_cannot_replace(
    client, auth_headers, scenario, booking_repository, venue_id
):
    before = list(booking_repository.bookings)
    response = request_replacement(client, auth_headers("Event Coordinator"), venue_id)
    assert response.status_code == 400
    assert booking_repository.bookings == before


@pytest.mark.parametrize("role", ["Event Organiser", "Venue Staff", "Safety Officer"])
def test_other_roles_cannot_search_or_replace(client, auth_headers, scenario, role):
    headers = auth_headers(role)
    assert search(client, headers).status_code == 403
    assert request_replacement(client, headers).status_code == 403


def test_unassigned_coordinator_is_refused(client, auth_headers, scenario, event_repository):
    event_repository.events[0] = replace(event_repository.events[0], coordinator_id=99)
    headers = auth_headers("Event Coordinator")
    assert search(client, headers).status_code == 404
    assert request_replacement(client, headers).status_code == 404


@pytest.mark.parametrize(
    "status", [EventStatus.CANCELLED, EventStatus.COMPLETED, EventStatus.REJECTED],
)
def test_closed_events_cannot_replace(client, auth_headers, scenario, event_repository, status):
    event_repository.events[0] = replace(event_repository.events[0], status=status)
    headers = auth_headers("Event Coordinator")
    assert search(client, headers).status_code == 409
    assert request_replacement(client, headers).status_code == 409


@pytest.mark.parametrize(("error", "expected"), [(SlotTaken, 400), (StaleBookingStatus, 409)])
def test_commit_race_returns_rule_error_without_partial_booking(
    client, auth_headers, scenario, booking_repository, monkeypatch, error, expected
):
    before = list(booking_repository.bookings)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(booking_repository, "request_replacement", fail)
    assert request_replacement(client, auth_headers("Event Coordinator")).status_code == expected
    assert booking_repository.bookings == before


@pytest.mark.parametrize(("result", "error"), [(-1, SlotTaken), (None, StaleBookingStatus)])
def test_supabase_atomic_rpc_errors(monkeypatch, result, error):
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = result
    monkeypatch.setattr(supabase_client, "admin", lambda: client)
    with pytest.raises(error):
        SupabaseBookings().request_replacement(10, venue_id=2, actor_id=2, reason="Why")
    # US12.4: through the wrapper that also reopens a Confirmed event.
    client.rpc.assert_called_once_with(
        "us12_4_request_replacement",
        {"p_booking_id": 10, "p_venue_id": 2, "p_actor_id": 2, "p_reason": "Why"},
    )
    client.table.assert_not_called()
