"""Flag bookings that clash after a setup/turnaround change — US15.2.

When Venue Staff change a venue's setup or turnaround time (US9.4), bookings
that fitted under the old values may not fit under the new ones. They are
identified, never silently removed:

* Every future active booking at the venue is re-checked with US15.1's rule
  (`availability.check_booking`): Held (unexpired), Requested and Confirmed
  bookings, and the venue's unavailability periods. "Future" means its occupied
  window, turnaround included, has not ended yet.
* A booking that now clashes and was not flagged already is marked
  "Conflict - review needed", with why, and its event's Coordinator is told
  (US10.2). The booking keeps its status. Nothing is deleted or cancelled.
* A flag clears once the clash is resolved: the booking is cancelled, rejected
  or its hold expired, the booking it clashed with went the same way, or the
  times changed so the windows no longer meet. That is checked again after a
  booking at the venue is cancelled or rejected, after any further
  setup/turnaround change, and whenever Venue Staff open the flagged list (a
  hold expires without anything being written, so a read is when it shows).

The reason stored on a flagged booking names the other booking by number,
status and occupied window but never by its event's title: the flagged
booking's Coordinator reads it, and they may not be assigned to the other event.

Writes here follow a change that has already been stored, so the `*_quietly`
wrappers log a failure rather than turning a saved change into an error.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app import availability, booking_store, event_store, venue_store, venue_unavailability_store
from app.availability import SlotCheck
from app.booking_store import Booking
from app.notifications import notify_booking_conflict
from app.venue_store import Venue
from app.venue_unavailability_store import Unavailability

logger = logging.getLogger(__name__)

#: What a flagged booking is shown as, in the words of the acceptance criteria.
LABEL = "Conflict – review needed"


def _minutes(value: int) -> str:
    return "1 minute" if value == 1 else f"{value} minutes"


def reason_for(found: SlotCheck, venue: Venue | None) -> str:
    """Why a booking is flagged, in words its own Coordinator may read."""
    setup, turnaround = availability.buffers(venue)
    return (
        f"With {_minutes(setup)} setup and {_minutes(turnaround)} turnaround it occupies "
        f"{availability.stamp(found.occupied_from)} to {availability.stamp(found.occupied_to)}, "
        "which overlaps " + "; and ".join(availability.describe(found)) + "."
    )


def clash_now(
    booking: Booking,
    venue: Venue | None,
    bookings_at_venue: Sequence[Booking],
    unavailability: Sequence[Unavailability],
    now: datetime,
) -> SlotCheck | None:
    """What a future active booking clashes with under the US15.1 rule, or None.

    None for a booking that no longer holds its venue (cancelled, rejected, an
    expired hold), one that has finished, one whose times cannot be read, and
    one that clashes with nothing.
    """
    if not booking.holds_venue_at(now):
        return None
    try:
        found = availability.check_booking(
            booking, venue, bookings_at_venue, unavailability, now=now
        )
    except ValueError:
        return None
    if found.occupied_to <= now or found.available:
        return None
    return found


@dataclass(frozen=True)
class Review:
    """What one pass over a venue's bookings changed."""

    #: Newly marked "Conflict - review needed" by this pass.
    flagged: tuple[Booking, ...] = ()
    #: Flags this pass cleared because the clash is resolved.
    cleared: tuple[Booking, ...] = ()


def _notify(booking: Booking, reason: str) -> None:
    event = event_store.repository().get_event(booking.event_id)
    if event is not None:
        notify_booking_conflict(event, booking.venue_name or "a venue", reason)


def _review(venue: Venue, *, flag_new: bool, now: datetime | None) -> Review:
    current = now or booking_store.local_now()
    store = booking_store.repository()
    bookings = store.list_for_venue(venue.id)
    if not flag_new and not any(booking.conflict for booking in bookings):
        return Review()
    blackouts = venue_unavailability_store.repository().list_for_venue(venue.id)

    flagged: list[Booking] = []
    cleared: list[Booking] = []
    for booking in bookings:
        found = clash_now(booking, venue, bookings, blackouts, current)
        if found is None:
            if booking.conflict is not None:
                cleared.append(store.clear_conflict(booking.id))
            continue
        if flag_new and booking.conflict is None:
            reason = reason_for(found, venue)
            flagged.append(store.flag_conflict(booking.id, reason=reason))
            _notify(booking, reason)
    return Review(flagged=tuple(flagged), cleared=tuple(cleared))


def recheck_venue(venue: Venue, *, now: datetime | None = None) -> Review:
    """US15.2: after a setup or turnaround change, flag what now clashes, clear what doesn't."""
    return _review(venue, flag_new=True, now=now)


def resolve_venue(venue_id: int, *, now: datetime | None = None) -> Review:
    """Clear the flags at one venue whose clash is resolved. Flags nothing new."""
    venue = venue_store.repository().get_venue(venue_id)
    if venue is None:
        return Review()
    return _review(venue, flag_new=False, now=now)


def resolve_flagged(*, now: datetime | None = None) -> None:
    """Clear every resolved flag, venue by venue. Run before listing the flags."""
    from app import arrangement_review

    flagged = booking_store.repository().list_flagged()
    for venue_id in sorted({b.venue_id for b in flagged}):
        resolve_venue(venue_id, now=now)
    for event_id in sorted({b.event_id for b in flagged if b.event_conflict_reason}):
        arrangement_review.refresh_if_reviewed(event_id)


def recheck_quietly(venue: Venue) -> Review | None:
    """`recheck_venue`, after a venue save that has already been stored. None if it failed."""
    try:
        return recheck_venue(venue)
    except Exception:
        logger.exception("Could not flag the US15.2 booking conflicts at venue %s", venue.id)
        return None


def resolve_quietly(venue_id: int) -> None:
    """`resolve_venue`, after a cancellation or rejection that has already been stored."""
    try:
        resolve_venue(venue_id)
    except Exception:
        logger.exception("Could not clear the US15.2 booking conflicts at venue %s", venue_id)
