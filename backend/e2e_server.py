"""The API over in-memory stores, for browser tests that write.

The Playwright specs in `frontend/e2e-isolated/` delete venues. Against the
shared Supabase project that would delete the team's real records, so they run
against this instead: the same app and the same rules, with the stores the
pytest suite uses (see tests/conftest.py) and nothing reaching Supabase.

    uvicorn e2e_server:app --port 8001

`POST /__test__/reset` puts every store back to the seed below, so each spec
starts from the same catalogue. It exists only on this app, never on
`app.main:app`.

What it cannot show is the database's own part of US9.5, the cascade and the
trigger in SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql: the in-memory venue store
deletes the venue only.
"""

from datetime import timedelta

from app import (
    auth,
    booking_store,
    equipment_store,
    event_store,
    notification_store,
    registration_store,
    safety_decision_store,
    users,
    venue_store,
    venue_unavailability_store,
)
from app.booking_store import Booking, BookingStatus, Cancellation, InMemoryBookings
from app.equipment_store import RESERVED, EquipmentRequest, InMemoryEquipment
from app.event_status import EventStatus
from app.event_store import Event, InMemoryEvents, StatusChange
from app.main import app
from app.notification_store import InMemoryNotifications
from app.registration_store import InMemoryRegistrations
from app.safety_decision_store import InMemorySafetyDecisions
from app.venue_store import InMemoryVenues, Venue
from app.venue_unavailability_store import (
    InMemoryUnavailability,
    Unavailability,
    UnavailabilityReasonType,
)
from tests.conftest import (
    ACCOUNTS,
    COORDINATOR_ID,
    ORGANISER_ID,
    PASSWORD,
    SUBMITTABLE_NEED_ATTRS,
    fixture_users,
    fixture_venues,
)

#: Venue ids the specs refer to. 1-3 are the pytest suite's own catalogue.
FUTURE_BOOKING = 1  # Great Hall: two bookings still to come
PAST_BOOKINGS_ONLY = 2  # Bertha Room: one that has ended, one cancelled
NEVER_BOOKED = 3  # Seminar Room 4
AWAITING_REPLACEMENT = 4  # Flagged Room: flagged by US12.2, still to come

#: US17.1/US17.2 (safety-check-us17.spec.ts): two events Pending Safety Check,
#: each ready to be decided. They book venues of their own, so nothing above
#: changes for the venue specs, and use ids clear of the event_id=1 bookings.
SAFETY_HALL = 5  # Main Hall: capacity 100, booked for the 120-person gala
SAFETY_STUDIO = 6  # Studio B
SAFETY_GALA = 50  # entered the check first, so it heads the queue
SAFETY_WORKSHOP = 51
SAFETY_GALA_BOOKING = 50
SAFETY_WORKSHOP_BOOKING = 51
SAFETY_GALA_EQUIPMENT = 50


def _at(delta: timedelta) -> str:
    """A naive Singapore time relative to now, so the seed never goes stale."""
    return (booking_store.local_now() + delta).replace(microsecond=0).isoformat()


def _booking(booking_id: int, venue: Venue, start: timedelta, **fields) -> Booking:
    return Booking(
        id=booking_id,
        event_id=fields.pop("event_id", 1),
        venue_id=venue.id,
        venue_name=venue.name,
        starts_at=_at(start),
        ends_at=_at(start + timedelta(hours=8)),
        status=fields.pop("status", BookingStatus.REQUESTED),
        requested_by_id=2,
        requested_at=_at(timedelta(days=-60)),
        **fields,
    )


def _safety_venue(venue_id: int, name: str, capacity: int, **fields) -> Venue:
    return Venue(
        id=venue_id,
        name=name,
        location=fields.pop("location", "Main Campus, Building C"),
        capacity=capacity,
        facilities=fields.pop("facilities", ""),
        accessibility_features=fields.pop("accessibility_features", ""),
        operating_hours=fields.pop("operating_hours", ""),
        created_at="2026-01-08T09:00:00",
        updated_at="2026-01-08T09:00:00",
        **fields,
    )


def _safety_event(event_id: int, title: str, attendance: int, entered: timedelta) -> Event:
    """An event the Coordinator sent for its safety check `entered` ago."""
    coordinator = next(user for user in fixture_users() if user.id == COORDINATOR_ID)
    organiser = next(user for user in fixture_users() if user.id == ORGANISER_ID)
    entered_at = _at(entered)
    return Event(
        id=event_id,
        title=title,
        purpose="Community outreach",
        description="Seeded for the safety check browser tests.",
        starts_at=_at(timedelta(days=30))[:16],
        ends_at=_at(timedelta(days=30, hours=4))[:16],
        expected_attendance=attendance,
        status=EventStatus.PENDING_SAFETY_CHECK,
        organiser_id=organiser.id,
        organiser_name=organiser.name,
        created_at=_at(timedelta(days=-20)),
        updated_at=entered_at,
        coordinator_id=coordinator.id,
        coordinator_name=coordinator.name,
        history=(
            StatusChange(
                EventStatus.PLANNING,
                EventStatus.PENDING_SAFETY_CHECK,
                entered_at,
                coordinator.id,
                coordinator.name,
            ),
        ),
        **{**SUBMITTABLE_NEED_ATTRS, "accessibility_needs": "Wheelchair access, Hearing loop"},
    )


SafetySeed = tuple[
    list[Venue], list[Booking], list[Event], list[EquipmentRequest], list[Unavailability]
]


def _safety_seed() -> SafetySeed:
    """US17.1/US17.2: what the safety check specs review and decide on."""
    hall = _safety_venue(
        SAFETY_HALL,
        "Main Hall",
        100,
        location="Main Campus, Building C, Level 1",
        facilities="Stage, PA system",
        accessibility_features="Ramp, accessible toilet",
        operating_hours="08:00-23:00",
        supported_layouts="Theatre, Banquet",
        setup_minutes=60,
        turnaround_minutes=30,
    )
    studio = _safety_venue(SAFETY_STUDIO, "Studio B", 40, supported_layouts="Classroom")
    month = timedelta(days=30)
    bookings = [
        # More people booked than the hall holds: the review's first warning.
        _booking(
            SAFETY_GALA_BOOKING,
            hall,
            month,
            status=BookingStatus.CONFIRMED,
            event_id=SAFETY_GALA,
            headcount=120,
            required_layout="Theatre",
            accessibility_needs=("Wheelchair access", "Hearing loop"),
        ),
        _booking(
            SAFETY_WORKSHOP_BOOKING,
            studio,
            month + timedelta(days=5),
            status=BookingStatus.CONFIRMED,
            event_id=SAFETY_WORKSHOP,
            headcount=30,
            required_layout="Classroom",
        ),
    ]
    events = [
        _safety_event(SAFETY_GALA, "Charity Gala Night", 120, timedelta(days=-10)),
        _safety_event(SAFETY_WORKSHOP, "Youth Workshop", 30, timedelta(days=-5)),
    ]
    equipment = [
        EquipmentRequest(
            id=SAFETY_GALA_EQUIPMENT,
            event_id=SAFETY_GALA,
            equipment_type="Wireless microphone",
            quantity=4,
            technical_requirements="Spare batteries",
            support_notes="Sound check before doors open",
            starts_at=_at(month),
            ends_at=_at(month + timedelta(hours=8)),
            status=RESERVED,
            requested_by_id=COORDINATOR_ID,
            created_at=_at(timedelta(days=-20)),
            version=1,
        )
    ]
    # A known restriction on the hall, after the gala so it blocks nothing.
    today = booking_store.local_now().date()
    closures = [
        Unavailability(
            id=SAFETY_HALL,
            venue_id=SAFETY_HALL,
            start_date=today + timedelta(days=50),
            end_date=today + timedelta(days=52),
            reason_type=UnavailabilityReasonType.OTHER,
            other_reason="Floor resurfacing",
            created_by_id=None,
            created_at=_at(timedelta(days=-20)),
        )
    ]
    return [hall, studio], bookings, events, equipment, closures


def seed() -> None:
    safety_venues, safety_bookings, safety_events, safety_equipment, safety_closures = (
        _safety_seed()
    )
    venues = fixture_venues()
    venues.append(
        Venue(
            id=AWAITING_REPLACEMENT,
            name="Flagged Room",
            location="Main Campus, Building B",
            capacity=80,
            facilities="",
            accessibility_features="",
            operating_hours="",
            created_at="2026-01-08T09:00:00",
            updated_at="2026-01-08T09:00:00",
        )
    )
    by_id = {venue.id: venue for venue in venues}
    week = timedelta(days=7)
    bookings = [
        _booking(1, by_id[FUTURE_BOOKING], week),
        _booking(2, by_id[FUTURE_BOOKING], 2 * week, status=BookingStatus.CONFIRMED),
        _booking(3, by_id[PAST_BOOKINGS_ONLY], -4 * week, status=BookingStatus.CONFIRMED),
        _booking(
            4,
            by_id[PAST_BOOKINGS_ONLY],
            3 * week,
            status=BookingStatus.CANCELLED,
            cancellation=Cancellation(at=_at(-week), by_id=2, by_name="Priya", reason="Moved"),
        ),
        _booking(
            5,
            by_id[AWAITING_REPLACEMENT],
            week,
            status=BookingStatus.NEEDS_REPLACEMENT,
            replacement_reason="Burst pipe",
        ),
        *safety_bookings,
    ]
    venues.extend(safety_venues)

    users.use_repository(
        users.InMemoryUsers(
            users=fixture_users(),
            passwords={email: PASSWORD for email in ACCOUNTS.values()},
        )
    )
    events = InMemoryEvents(
        events=safety_events, names={user.id: user.name for user in fixture_users()}
    )
    event_store.use_repository(events)
    safety_decision_store.use_repository(InMemorySafetyDecisions(names=events.names))
    venue_store.use_repository(InMemoryVenues(venues=venues))
    venue_unavailability_store.use_repository(InMemoryUnavailability(entries=safety_closures))
    notification_store.use_repository(InMemoryNotifications())
    booking_store.use_repository(InMemoryBookings(bookings=bookings))
    registration_store.use_repository(InMemoryRegistrations())
    equipment_store.use_repository(InMemoryEquipment(requests=safety_equipment))
    auth.store.clear()


@app.post("/__test__/reset", include_in_schema=False)
def reset() -> dict[str, str]:
    seed()
    return {"status": "reset"}


seed()
