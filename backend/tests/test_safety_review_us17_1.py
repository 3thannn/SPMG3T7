"""US17.1: the Safety Officer's review queue and detail view.

Acceptance criteria, and the tests that hold each one:

* List shows events in Pending Safety Check, oldest first -> `TestQueue`.
* Detail view shows expected attendance, each booked venue's capacity, layout,
  accessibility and known restrictions, reserved equipment, and the event's
  accessibility requirements -> `TestDetailView`, `TestBuildReview`.
* Read-only -> `TestReadOnly`.
* Safety Officer role only -> `TestSafetyOfficerOnly`.
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import pytest

from app import supabase_client
from app.booking_store import BookingStatus, local_now
from app.equipment_store import RESERVED, SupabaseEquipment
from app.event_status import EventStatus
from app.event_store import StatusChange
from app.safety_review import (
    Closure,
    VenueReview,
    build_review,
    entered_safety_check,
)
from app.venue_store import Venue
from app.venue_unavailability_store import Unavailability
from tests.conftest import COORDINATOR_ID, SAFETY_OFFICER_ID
from tests.test_safety_check_us4_4 import EVENT_ID, booking, equipment_line, seed_event

PSC = EventStatus.PENDING_SAFETY_CHECK
#: The route reads "today" in Singapore; a few days either side keeps the
#: fixtures clear of any timezone edge.
TODAY = local_now().date()


def venue(venue_id=50, **overrides):
    fields = {
        "id": venue_id,
        "name": "Riverside Hall",
        "location": "Block C, Level 2",
        "capacity": 100,
        "facilities": "Stage, PA system",
        "accessibility_features": "Step-free access, hearing loop",
        "operating_hours": "08:00-22:00",
        "created_at": "2099-01-01T09:00",
        "updated_at": "2099-01-01T09:00",
        "supported_layouts": "Theatre, Banquet",
        "setup_minutes": 30,
        "turnaround_minutes": 45,
        **overrides,
    }
    return Venue(**fields)


def closure(closure_id, start, end, *, venue_id=50, reason_type="maintenance", other_reason=""):
    return Unavailability(
        id=closure_id, venue_id=venue_id, start_date=start, end_date=end,
        reason_type=reason_type, other_reason=other_reason, created_by_id=4, created_at="2099-01-01T09:00",
    )


def reviewed_booking(
    booking_id=1, status=BookingStatus.CONFIRMED, *, venue_id=50, hold_expires_at="", **extra
):
    """US4.4's booking fixture, in this story's venue, with any US18.1 needs set."""
    base = booking(booking_id, status, venue_id=venue_id, hold_expires_at=hold_expires_at)
    return replace(base, **extra)


def entered(at):
    return (StatusChange(EventStatus.PLANNING, PSC, at, COORDINATOR_ID, "Priya"),)


@pytest.fixture
def pending(event_repository, booking_repository, venue_repository):
    """An event waiting for its check, in a venue with everything worth showing."""
    venue_repository.venues.append(venue())
    booking_repository.bookings.append(
        reviewed_booking(1, required_layout="Theatre", accessibility_needs=("Hearing loop",))
    )
    return seed_event(event_repository, PSC, history=entered("2099-01-05T09:00"))


class TestQueue:
    """AC1: List shows events in Pending Safety Check, oldest first."""

    def test_only_pending_events_oldest_first(self, client, auth_headers, event_repository):
        seed_event(event_repository, PSC, event_id=1, history=entered("2099-01-03T09:00"))
        seed_event(event_repository, PSC, event_id=2, history=entered("2099-01-01T09:00"))
        seed_event(event_repository, PSC, event_id=3, history=entered("2099-01-02T09:00"))
        for event_id, status in enumerate(
            [EventStatus.PLANNING, EventStatus.CONFIRMED, EventStatus.UNDER_REVIEW], start=4
        ):
            seed_event(event_repository, status, event_id=event_id)

        response = client.get("/events/safety-check", headers=auth_headers("Safety Officer"))

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["2", "3", "1"]
        assert {item["status"] for item in response.json()} == {"Pending Safety Check"}

    def test_ties_keep_a_stable_order(self, client, auth_headers, event_repository):
        seed_event(event_repository, PSC, event_id=9, history=entered("2099-01-01T09:00"))
        seed_event(event_repository, PSC, event_id=8, history=entered("2099-01-01T09:00"))
        response = client.get("/events/safety-check", headers=auth_headers("Safety Officer"))
        assert [item["id"] for item in response.json()] == ["8", "9"]

    def test_an_empty_queue(self, client, auth_headers):
        response = client.get("/events/safety-check", headers=auth_headers("Safety Officer"))
        assert response.status_code == 200
        assert response.json() == []

    def test_waiting_time_counts_from_the_latest_send(self, event_repository):
        history = (
            StatusChange(EventStatus.PLANNING, PSC, "2099-01-01T09:00", COORDINATOR_ID, "Priya"),
            StatusChange(PSC, EventStatus.PLANNING, "2099-01-01T10:00", SAFETY_OFFICER_ID, "Alex"),
            StatusChange(EventStatus.PLANNING, PSC, "2099-01-04T09:00", COORDINATOR_ID, "Priya"),
        )
        event = seed_event(event_repository, PSC, history=history)
        assert entered_safety_check(event) == "2099-01-04T09:00"

    def test_without_a_recorded_move_it_falls_back_to_the_last_change(self, event_repository):
        event = seed_event(event_repository, PSC, updated_at="2099-02-02T09:00")
        assert entered_safety_check(event) == "2099-02-02T09:00"


class TestDetailView:
    """AC2: everything the Safety Officer needs, in one answer."""

    def test_the_event_and_its_accessibility_requirements(self, client, auth_headers, pending):
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        assert body["eventId"] == str(EVENT_ID)
        assert body["title"] == "Open House"
        assert body["status"] == "Pending Safety Check"
        assert body["expectedAttendance"] == 30
        assert body["accessibilityNeeds"] == "Wheelchair access"
        assert body["preferredLayout"] == "Theatre"
        assert body["venueRequirements"] == "Stage, Projector"
        assert (body["startsAt"], body["endsAt"]) == ("2099-11-02T09:00", "2099-11-02T17:00")
        assert body["waitingSince"] == "2099-01-05T09:00"

    def test_each_booked_venue_with_capacity_layout_and_accessibility(
        self, client, auth_headers, pending
    ):
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        [hall] = body["venues"]
        assert hall == {
            "bookingId": "1",
            "venueId": "50",
            "venueName": "Riverside Hall",
            "location": "Block C, Level 2",
            "status": "Confirmed",
            "startsAt": "2099-11-02T09:00",
            "endsAt": "2099-11-02T17:00",
            "capacity": 100,
            "headcount": 30,
            "overCapacity": False,
            "requiredLayout": "Theatre",
            "supportedLayouts": "Theatre, Banquet",
            "facilities": "Stage, PA system",
            "accessibilityFeatures": "Step-free access, hearing loop",
            "accessibilityNeeds": ["Hearing loop"],
            "operatingHours": "08:00-22:00",
            "setupMinutes": 30,
            "turnaroundMinutes": 45,
            "closures": [],
        }

    def test_known_restrictions_include_closures_not_yet_over(
        self, client, auth_headers, pending, unavailability_repository
    ):
        unavailability_repository.entries.extend([
            closure(3, TODAY + timedelta(days=30), TODAY + timedelta(days=32), reason_type="other", other_reason="Renovation"),
            closure(1, TODAY - timedelta(days=20), TODAY - timedelta(days=10)),
            closure(2, TODAY + timedelta(days=5), TODAY + timedelta(days=6),
                    reason_type="other", other_reason="Fire alarm testing"),
            closure(4, TODAY + timedelta(days=5), TODAY + timedelta(days=5), venue_id=1),
        ])
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        assert body["venues"][0]["closures"] == [
            {
                "startDate": (TODAY + timedelta(days=5)).isoformat(),
                "endDate": (TODAY + timedelta(days=6)).isoformat(),
                "reason": "Fire alarm testing",
            },
            {
                "startDate": (TODAY + timedelta(days=30)).isoformat(),
                "endDate": (TODAY + timedelta(days=32)).isoformat(),
                "reason": "Renovation",
            },
        ]

    def test_only_reserved_equipment_is_listed(
        self, client, auth_headers, pending, equipment_repository
    ):
        equipment_repository.requests.extend([
            equipment_line(1, RESERVED),
            equipment_line(2, "Removed"),
            equipment_line(3, RESERVED, event_id=999),
        ])
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        assert body["equipment"] == [
            {
                "id": "1",
                "type": "Projector",
                "quantity": 1,
                "technicalRequirements": "",
                "supportNotes": "",
                "startsAt": "2099-11-02T09:00",
                "endsAt": "2099-11-02T17:00",
            }
        ]

    def test_several_venues_and_only_the_ones_actually_booked(
        self, client, auth_headers, pending, booking_repository, venue_repository
    ):
        venue_repository.venues.append(venue(51, name="Breakout Room", capacity=20))
        booking_repository.bookings.extend([
            reviewed_booking(2, venue_id=51, headcount=25),
            reviewed_booking(3, BookingStatus.CANCELLED),
            reviewed_booking(4, BookingStatus.REJECTED),
            reviewed_booking(5, BookingStatus.HELD, hold_expires_at="2000-01-01T09:00"),
        ])
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        assert [(v["bookingId"], v["venueName"]) for v in body["venues"]] == [
            ("1", "Riverside Hall"),
            ("2", "Breakout Room"),
        ]
        assert body["venues"][1]["overCapacity"] is True

    def test_no_equipment_and_no_venues_are_answered_as_empty(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, PSC)
        body = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        ).json()
        assert (body["venues"], body["equipment"]) == ([], [])


class TestBuildReview:
    """AC2 as a unit, with the clock and the stores supplied."""

    def build(self, event_repository, bookings, venues=(), closures=(), equipment=()):
        event = seed_event(event_repository, PSC)
        catalogue = {item.id: item for item in venues}
        return build_review(
            event,
            bookings=bookings,
            venue_for=catalogue.get,
            closures_for=lambda venue_id: [c for c in closures if c.venue_id == venue_id],
            equipment=equipment,
            today=date(2099, 6, 10),
        )

    @pytest.mark.parametrize(
        ("headcount", "capacity", "over"),
        [(100, 100, False), (101, 100, True), (None, 100, False), (101, None, False)],
    )
    def test_over_capacity_boundary(self, headcount, capacity, over):
        reviewed = VenueReview(
            booking_id=1, venue_id=1, venue_name="Hall", location="", status="Confirmed",
            starts_at="", ends_at="", capacity=capacity, headcount=headcount,
            required_layout="", supported_layouts="", facilities="",
            accessibility_features="", accessibility_needs=(), operating_hours="",
            setup_minutes=0, turnaround_minutes=0, closures=(),
        )
        assert reviewed.over_capacity is over

    def test_a_closure_ending_today_still_restricts(self, event_repository):
        review = self.build(
            event_repository,
            [reviewed_booking()],
            venues=[venue()],
            closures=[
                closure(1, date(2099, 6, 1), date(2099, 6, 9)),
                closure(2, date(2099, 6, 8), date(2099, 6, 10), other_reason=""),
            ],
        )
        assert review.venues[0].closures == (
            Closure(start_date=date(2099, 6, 8), end_date=date(2099, 6, 10), reason=""),
        )

    def test_a_venue_record_that_has_gone_still_shows_the_booking(self, event_repository):
        review = self.build(event_repository, [reviewed_booking(venue_id=77)])
        [shown] = review.venues
        assert (shown.venue_name, shown.capacity, shown.location) == ("Great Hall", None, "")
        assert (shown.setup_minutes, shown.turnaround_minutes, shown.closures) == (0, 0, ())
        assert shown.over_capacity is False

    def test_equipment_is_passed_through_in_order(self, event_repository):
        lines = [equipment_line(1, RESERVED), equipment_line(2, RESERVED)]
        review = self.build(event_repository, [], equipment=lines)
        assert review.equipment == tuple(lines)
        assert review.venues == ()


class TestReadOnly:
    """AC3: looking changes nothing, and there is nothing to write to."""

    def test_reading_the_review_changes_nothing(
        self, client, auth_headers, pending, event_repository, booking_repository
    ):
        before = (list(event_repository.events), list(booking_repository.bookings))
        response = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        )
        assert response.status_code == 200
        assert (event_repository.events, booking_repository.bookings) == before

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_the_review_accepts_no_writes(self, client, auth_headers, pending, method):
        response = client.request(
            method.upper(), f"/events/{EVENT_ID}/safety-review",
            headers=auth_headers("Safety Officer"),
        )
        assert response.status_code == 405


class TestSafetyOfficerOnly:
    """AC4: the queue and the detail view are the Safety Officer's alone."""

    @pytest.mark.parametrize(
        "role",
        ["Event Organiser", "Event Coordinator", "Event Coordinator Lead", "Venue Staff",
         "Technical Support"],
    )
    def test_every_other_role_is_refused(self, client, auth_headers, pending, role):
        headers = auth_headers(role)
        detail = client.get(f"/events/{EVENT_ID}/safety-review", headers=headers)
        queue = client.get("/events/safety-check", headers=headers)
        assert (detail.status_code, queue.status_code) == (403, 403)
        assert "review event safety" in detail.json()["detail"]["message"]

    def test_signed_out_is_refused(self, client, pending):
        assert client.get(f"/events/{EVENT_ID}/safety-review").status_code == 401

    @pytest.mark.parametrize(
        "status", [EventStatus.PLANNING, EventStatus.CONFIRMED, EventStatus.DRAFT]
    )
    def test_only_while_the_event_waits_for_them(
        self, client, auth_headers, event_repository, status
    ):
        seed_event(event_repository, status)
        response = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers("Safety Officer")
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("event_id", ["12345", "not-a-number"])
    def test_an_unknown_event(self, client, auth_headers, event_id):
        response = client.get(
            f"/events/{event_id}/safety-review", headers=auth_headers("Safety Officer")
        )
        assert response.status_code == 404


@dataclass
class FakeQuery:
    calls: list[tuple] = field(default_factory=list)
    rows: list[dict] | None = None

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def select(self, columns):
        self.calls.append(("select",))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def order(self, column):
        self.calls.append(("order", column))
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class TestReservedEquipmentStore:
    def test_supabase_reads_reserved_lines_for_one_event(self, monkeypatch):
        query = FakeQuery(rows=[{
            "id": 7, "event_id": EVENT_ID, "equipment_type": "Projector", "quantity": 2,
            "technical_requirements": "HDMI", "support_notes": "", "start_at": "2099-11-02T09:00",
            "end_at": "2099-11-02T17:00", "status": RESERVED, "requested_by_id": COORDINATOR_ID,
            "created_at": "2099-01-01T09:00", "version": 3, "updated_by_id": 6,
            "events": {"name": "Open House"},
        }])
        monkeypatch.setattr(supabase_client, "admin", lambda: query)
        [line] = SupabaseEquipment().list_reserved_for_event(EVENT_ID)
        assert (line.id, line.status, line.quantity, line.event_title) == (
            7, RESERVED, 2, "Open House"
        )
        assert query.calls == [
            ("table", "equipment_requests"),
            ("select",),
            ("eq", "event_id", EVENT_ID),
            ("eq", "status", RESERVED),
            ("order", "created_at"),
            ("order", "id"),
        ]

    def test_supabase_answers_nothing_as_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "admin", lambda: FakeQuery(rows=None))
        assert SupabaseEquipment().list_reserved_for_event(EVENT_ID) == []

    def test_in_memory_keeps_reserved_lines_for_the_event_oldest_first(
        self, equipment_repository
    ):
        later = equipment_line(1, RESERVED)
        earlier = equipment_line(2, RESERVED)
        earlier = replace(earlier, created_at="2098-01-01T09:00")
        equipment_repository.requests.extend([
            later, earlier, equipment_line(3, "Requested"), equipment_line(4, RESERVED, event_id=1)
        ])
        assert [line.id for line in equipment_repository.list_reserved_for_event(EVENT_ID)] == [
            2, 1
        ]
