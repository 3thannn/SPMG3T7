"""US11.2 checks saved arrangements against the revised event; never moves them.

Event-change flags are separate from US15.2 clash and US12.2 replacement flags,
so the older venue sweep cannot clear a suitability or event-coverage failure.
The pending marker is committed with the edit, making interrupted checks retryable.
"""

import logging
from datetime import datetime

from app import (
    availability,
    booking_store,
    equipment_store,
    event_store,
    suitability,
    venue_store,
    venue_unavailability_store,
)
from app.event_store import Event
from app.notifications import notify_arrangement_conflicts
from app.suitability import BookingNeeds

logger = logging.getLogger(__name__)


def coverage(event: Event, start: str, end: str) -> list[str]:
    if datetime.fromisoformat(start) > datetime.fromisoformat(
        event.starts_at
    ) or datetime.fromisoformat(end) < datetime.fromisoformat(event.ends_at):
        return [
            "The saved window does not cover the revised event. Review the required times (SGT)."
        ]
    return []


def recheck(event: Event) -> Event:
    """Complete each check independently and retain a visible retry on any failure."""
    report: list[dict] = []
    changed: list[str] = []
    pending = False
    booking_flags: list[dict] = []
    equipment_flags: list[dict] = []
    previous = {(r.get("kind"), r.get("id")): r.get("reason") for r in event.arrangement_review}
    now = booking_store.local_now()

    def record(kind: str, row_id: int, label: str, reason: str, error: bool = False) -> None:
        report.append(
            {"kind": kind, "id": str(row_id), "label": label, "reason": reason, "error": error}
        )
        if reason and not error and previous.get((kind, str(row_id))) != reason:
            changed.append(f"{label}: {reason}")

    try:
        bookings = booking_store.repository().list_for_event(event.id)
        reservations = equipment_store.repository().list_for_event(event.id)
    except Exception:
        logger.exception("Could not load arrangements for event %s", event.id)
        return event_store.repository().set_arrangement_review(
            event.id,
            [
                {
                    "kind": "check",
                    "id": "",
                    "label": "Arrangement checks",
                    "error": True,
                    "reason": "Could not load arrangements. Retry the checks.",
                }
            ],
            True,
            expected_updated_at=event.updated_at,
        )

    for booking in bookings:
        label = f"Venue booking #{booking.id} ({booking.venue_name})"
        try:
            reasons: list[str] = []
            if booking.holds_venue_at(now):
                venue = venue_store.repository().get_venue(booking.venue_id)
                reasons += coverage(event, booking.starts_at, booking.ends_at)
                if venue is None:
                    reasons.append("The venue is no longer available in the catalogue.")
                else:
                    slot = availability.check_booking(
                        booking,
                        venue,
                        booking_store.repository().list_for_venue(venue.id),
                        venue_unavailability_store.repository().list_for_venue(venue.id),
                        now=now,
                    )
                    if not slot.available:
                        reasons.append(
                            "The saved venue window clashes with a booking "
                            "or unavailability period."
                        )
                    needs = BookingNeeds(
                        headcount=event.expected_attendance or booking.headcount or 0,
                        starts_at=datetime.fromisoformat(booking.starts_at),
                        ends_at=datetime.fromisoformat(booking.ends_at),
                        layout=booking.required_layout,
                        facilities=booking.required_facilities,
                        accessibility=booking.accessibility_needs,
                    )
                    reasons.extend(suitability.assess(venue, needs).reasons)
            reason = " ".join(reasons)
            booking_flags.append(
                {
                    "id": booking.id,
                    "reason": reason,
                    "status": str(booking.status),
                    "startsAt": booking.starts_at,
                    "endsAt": booking.ends_at,
                    "headcount": booking.headcount,
                }
            )
            if booking.holds_venue_at(now):
                record("venue", booking.id, label, reason)
        except Exception:
            pending = True
            logger.exception("Could not recheck booking %s", booking.id)
            record("venue", booking.id, label, "Check failed. Retry the checks.", True)

    for reservation in reservations:
        label = f"Equipment reservation #{reservation.id} ({reservation.equipment_type})"
        try:
            reasons = []
            if reservation.status == equipment_store.RESERVED:
                reasons += coverage(event, reservation.starts_at, reservation.ends_at)
                choices = equipment_store.repository().reservation_availability(reservation.id)
                stock = next(
                    (c for c in choices if str(c["equipmentId"]) == str(reservation.equipment_id)),
                    None,
                )
                if stock is None:
                    reasons.append("The reserved catalogue item is no longer available.")
                elif stock["shortfall"] > 0:
                    reasons.append(f"Insufficient equipment stock: shortfall {stock['shortfall']}.")
            reason = " ".join(reasons)
            equipment_flags.append(
                {
                    "id": reservation.id,
                    "reason": reason,
                    "status": reservation.status,
                    "version": reservation.version,
                }
            )
            if reservation.status == equipment_store.RESERVED:
                record("equipment", reservation.id, label, reason)
        except Exception:
            pending = True
            logger.exception("Could not recheck equipment reservation %s", reservation.id)
            record("equipment", reservation.id, label, "Check failed. Retry the checks.", True)
    result = event_store.repository().set_arrangement_review(
        event.id,
        report,
        pending,
        expected_updated_at=event.updated_at,
        booking_flags=booking_flags,
        equipment_flags=equipment_flags,
    )
    if result.updated_at == event.updated_at and result.arrangement_review == tuple(report):
        notify_arrangement_conflicts(result, changed)
    return result


def refresh_if_reviewed(event_id: int) -> None:
    """Refresh existing event-change checks after an arrangement is resolved."""
    event = event_store.repository().get_event(event_id)
    if event is not None and (event.arrangement_review or event.arrangement_review_pending):
        recheck(event)
