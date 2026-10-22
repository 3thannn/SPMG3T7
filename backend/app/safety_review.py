"""US17.1: what the Safety Officer reviews for an event Pending Safety Check.

The story asks for "everything I need to review them, so that I can assess them
without chasing people for info", and names it: the expected attendance, each
booked venue's capacity, layout, accessibility and known restrictions, the
reserved equipment, and the event's accessibility requirements.

This module puts that together from the stores the rest of the system already
keeps; it reads and never writes, which is the story's "read-only". The route
in `app.events` decides who may see it (the Safety Officer, and only while the
event waits for them).

A venue's *known restrictions* are the limits Venue Staff have recorded on it:
its operating hours, the setup and turnaround time it needs around each event
(US9.4), and its unavailability periods (US12.1) that have not ended yet. A
period already over restricts nothing, so it is left out.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from app.booking_store import Booking
from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus
from app.event_store import Event
from app.venue_store import Venue
from app.venue_unavailability_store import Unavailability


@dataclass(frozen=True)
class Closure:
    """One unavailability period on a venue, inclusive at both ends (US12.1)."""

    start_date: date
    end_date: date
    reason: str


@dataclass(frozen=True)
class VenueReview:
    """One booked venue, with what the booking asks of it beside what it offers."""

    booking_id: int
    venue_id: int
    venue_name: str
    location: str
    status: str
    starts_at: str
    ends_at: str
    #: None only if the venue record has gone; the booking is still shown.
    capacity: int | None
    headcount: int | None
    required_layout: str
    supported_layouts: str
    facilities: str
    accessibility_features: str
    #: What this booking asked the venue for (US18.1).
    accessibility_needs: tuple[str, ...]
    operating_hours: str
    setup_minutes: int
    turnaround_minutes: int
    closures: tuple[Closure, ...]

    @property
    def over_capacity(self) -> bool:
        """More people booked into the room than it holds — the first safety question."""
        return (
            self.capacity is not None
            and self.headcount is not None
            and self.headcount > self.capacity
        )


@dataclass(frozen=True)
class SafetyReview:
    event: Event
    #: When the event last entered Pending Safety Check.
    waiting_since: str
    venues: tuple[VenueReview, ...]
    equipment: tuple[EquipmentRequest, ...]


def entered_safety_check(event: Event) -> str:
    """When the event last moved to Pending Safety Check.

    The last such entry, so an event sent back and sent again counts from the
    second time. An event with no entry for the move — one set up by hand —
    falls back to when it last changed.
    """
    entered = [
        change.at
        for change in event.history
        if change.to_status is EventStatus.PENDING_SAFETY_CHECK
    ]
    return entered[-1] if entered else event.updated_at


def _venue_review(
    booking: Booking, venue: Venue | None, closures: Iterable[Unavailability], today: date
) -> VenueReview:
    return VenueReview(
        booking_id=booking.id,
        venue_id=booking.venue_id,
        venue_name=venue.name if venue else booking.venue_name,
        location=venue.location if venue else "",
        status=str(booking.status),
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        capacity=venue.capacity if venue else None,
        headcount=booking.headcount,
        required_layout=booking.required_layout,
        supported_layouts=venue.supported_layouts if venue else "",
        facilities=venue.facilities if venue else "",
        accessibility_features=venue.accessibility_features if venue else "",
        accessibility_needs=booking.accessibility_needs,
        operating_hours=venue.operating_hours if venue else "",
        setup_minutes=venue.setup_minutes if venue else 0,
        turnaround_minutes=venue.turnaround_minutes if venue else 0,
        closures=tuple(
            Closure(start_date=item.start_date, end_date=item.end_date, reason=item.reason)
            for item in sorted(closures, key=lambda item: (item.start_date, item.id))
            if item.end_date >= today
        ),
    )


def build_review(
    event: Event,
    *,
    bookings: Iterable[Booking],
    venue_for: Callable[[int], Venue | None],
    closures_for: Callable[[int], Iterable[Unavailability]],
    equipment: Iterable[EquipmentRequest],
    today: date,
) -> SafetyReview:
    """Everything US17.1 shows for one event.

    Only bookings that hold their venue count as "booked" — Cancelled, Rejected
    and expired ones are history, not part of the plan being checked. They are
    in booking order, soonest first, as the stores return them.
    """
    venues = tuple(
        _venue_review(booking, venue_for(booking.venue_id), closures_for(booking.venue_id), today)
        for booking in bookings
        if booking.holds_venue
    )
    return SafetyReview(
        event=event,
        waiting_since=entered_safety_check(event),
        venues=venues,
        equipment=tuple(equipment),
    )
