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
from app.equipment_store import InMemoryEquipment
from app.event_store import InMemoryEvents
from app.main import app
from app.notification_store import InMemoryNotifications
from app.registration_store import InMemoryRegistrations
from app.safety_decision_store import InMemorySafetyDecisions
from app.venue_store import InMemoryVenues, Venue
from app.venue_unavailability_store import InMemoryUnavailability
from tests.conftest import ACCOUNTS, PASSWORD, fixture_users, fixture_venues

#: Venue ids the specs refer to. 1-3 are the pytest suite's own catalogue.
FUTURE_BOOKING = 1  # Great Hall: two bookings still to come
PAST_BOOKINGS_ONLY = 2  # Bertha Room: one that has ended, one cancelled
NEVER_BOOKED = 3  # Seminar Room 4
AWAITING_REPLACEMENT = 4  # Flagged Room: flagged by US12.2, still to come


def _at(delta: timedelta) -> str:
    """A naive Singapore time relative to now, so the seed never goes stale."""
    return (booking_store.local_now() + delta).replace(microsecond=0).isoformat()


def _booking(booking_id: int, venue: Venue, start: timedelta, **fields) -> Booking:
    return Booking(
        id=booking_id,
        event_id=1,
        venue_id=venue.id,
        venue_name=venue.name,
        starts_at=_at(start),
        ends_at=_at(start + timedelta(hours=8)),
        status=fields.pop("status", BookingStatus.REQUESTED),
        requested_by_id=2,
        requested_at=_at(timedelta(days=-60)),
        **fields,
    )


def seed() -> None:
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
    ]

    users.use_repository(
        users.InMemoryUsers(
            users=fixture_users(),
            passwords={email: PASSWORD for email in ACCOUNTS.values()},
        )
    )
    events = InMemoryEvents(names={user.id: user.name for user in fixture_users()})
    event_store.use_repository(events)
    safety_decision_store.use_repository(InMemorySafetyDecisions(names=events.names))
    venue_store.use_repository(InMemoryVenues(venues=venues))
    venue_unavailability_store.use_repository(InMemoryUnavailability())
    notification_store.use_repository(InMemoryNotifications())
    booking_store.use_repository(InMemoryBookings(bookings=bookings))
    registration_store.use_repository(InMemoryRegistrations())
    equipment_store.use_repository(InMemoryEquipment())
    auth.store.clear()


@app.post("/__test__/reset", include_in_schema=False)
def reset() -> dict[str, str]:
    seed()
    return {"status": "reset"}


seed()
