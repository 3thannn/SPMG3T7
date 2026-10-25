"""Venue routes — US9.2 (view the venue catalogue).

A Coordinator lists the ConnectSphere venues and opens any one of them. That is
the whole story, and the endpoints are shaped to say so:

* Two routes, both GET. Read-only is not enforced by a check inside a write
  route — there is no write route to reach. Venue records are maintained in
  Supabase, not through this API.
* Filtering is query parameters on the list route and nothing else (US9.3):
  no new table, no new endpoint, and the unfiltered call is still the same
  request it always was. The criteria AND together — a Coordinator asking for
  200 seats and step-free access wants both.
* There is no per-record ownership rule of the kind `events` needs. Every
  venue is visible to every Coordinator and writable by any Venue Staff member,
  so the guard is the role and `require_permission` is the whole of it.

Ids go out as strings, as they do everywhere else in this API; the client only
ever compares them.
"""

import re
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app import (
    booking_store,
    conflict_flags,
    supabase_client,
    venue_store,
    venue_turnaround,
    venue_unavailability_store,
)
from app.auth import require_permission
from app.permissions import Permission
from app.users import User
from app.venue_store import DuplicateVenueName, Venue, VenueFilters
from app.venue_turnaround import BookingConflict, InvalidMinutes, OccupiedBooking, Recheck
from app.venue_unavailability_store import Unavailability

router = APIRouter(prefix="/venues", tags=["venues"])


class VenueError:
    NOT_FOUND = "venue_not_found"
    INVALID_FILTER = "invalid_filter"
    INVALID = "invalid_venue"
    NAME_TAKEN = "venue_name_taken"
    INVALID_UNAVAILABILITY = "invalid_unavailability"
    IN_USE = "venue_in_use"


class VenueOut(BaseModel):
    id: str
    name: str
    location: str
    capacity: int
    #: Empty when the column holds nothing; the client shows "Not recorded"
    #: rather than a blank, so an unfilled field reads as unfilled.
    facilities: str
    accessibility_features: str = Field(serialization_alias="accessibilityFeatures")
    operating_hours: str = Field(serialization_alias="operatingHours")
    supported_layouts: str = Field(serialization_alias="supportedLayouts")
    #: US9.4: whole minutes before and after each booking that the venue is
    #: still occupied. 0 when Venue Staff have not set one.
    setup_minutes: int = Field(serialization_alias="setupMinutes")
    turnaround_minutes: int = Field(serialization_alias="turnaroundMinutes")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


def _to_out(venue: Venue) -> VenueOut:
    return VenueOut(
        id=str(venue.id),
        name=venue.name,
        location=venue.location,
        capacity=venue.capacity,
        facilities=venue.facilities,
        accessibility_features=venue.accessibility_features,
        operating_hours=venue.operating_hours,
        supported_layouts=venue.supported_layouts,
        setup_minutes=venue.setup_minutes,
        turnaround_minutes=venue.turnaround_minutes,
        created_at=venue.created_at,
        updated_at=venue.updated_at,
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": VenueError.NOT_FOUND,
            "message": "That venue is not in the catalogue.",
        },
    )


def _invalid_filter(message: str) -> HTTPException:
    """A filter that cannot be read is the caller's mistake, said in a sentence.

    400 with a code rather than FastAPI's 422, so a bad filter reads like every
    other refusal this API sends and the client has one shape to handle.
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": VenueError.INVALID_FILTER, "message": message},
    )


#: `venues.location` is VARCHAR(500) and the text columns are unbounded, so the
#: cap here is about not sending an absurd pattern to Postgres rather than about
#: matching a column width.
FILTER_TEXT_MAX = 200


def _min_capacity(raw: str) -> int | None:
    """Read the capacity floor, or None when it was not asked for.

    Taken as text rather than an int so that "abc" and "-5" come back as the
    same 400 this module sends for every other bad filter, instead of the 422
    FastAPI would raise for one and not the other.
    """
    trimmed = raw.strip()
    if not trimmed:
        return None
    # isdigit rejects a negative, a decimal and a word in one go. A venue that
    # holds minus five people is not a query, it is a typo.
    if not trimmed.isdigit():
        raise _invalid_filter("Give a whole number of people for the minimum capacity.")
    return int(trimmed)


def _filter_text(raw: str, *, field: str) -> str:
    trimmed = raw.strip()
    if len(trimmed) > FILTER_TEXT_MAX:
        raise _invalid_filter(f"Keep the {field} filter to {FILTER_TEXT_MAX} characters or fewer.")
    return trimmed


def _as_id(raw: str) -> int:
    """Ids are strings on the wire and integers in the table."""
    try:
        return int(raw)
    except ValueError:
        raise _not_found() from None


@router.get("", response_model=list[VenueOut])
def list_venues(
    _: Annotated[User, Depends(require_permission(Permission.VENUES_READ))],
    min_capacity: Annotated[
        str,
        Query(
            alias="minCapacity",
            description="Only venues holding at least this many people.",
        ),
    ] = "",
    location: Annotated[
        str,
        Query(description="Case-insensitive substring of the venue's location."),
    ] = "",
    accessibility: Annotated[
        str,
        Query(description=("Case-insensitive substring of the venue's accessibility features.")),
    ] = "",
    available_from: Annotated[
        str,
        Query(
            alias="availableFrom",
            description="YYYY-MM-DD. Leave out venues with a blackout on any day from here.",
        ),
    ] = "",
    available_to: Annotated[
        str,
        Query(
            alias="availableTo",
            description="YYYY-MM-DD, inclusive. Either date alone means that one day.",
        ),
    ] = "",
) -> list[VenueOut]:
    """US9.2 the catalogue, US9.3 narrowed: capacity, location, accessibility.

    No parameters returns the whole catalogue, which is what US9.2 asked for and
    still the behaviour of a bare `GET /venues`. Every parameter supplied has to
    match — see `VenueFilters` for why AND is the only sensible reading.
    
    US12.1 adds the dates being planned for: a venue marked unavailable on any
    of them is left out, so a Coordinator is not offered it in the first place.
    """
    window = _availability_window(available_from, available_to)
    excluded = (
        venue_unavailability_store.repository().venues_unavailable_between(*window)
        if window
        else frozenset()
    )
    filters = VenueFilters(
        min_capacity=_min_capacity(min_capacity),
        location=_filter_text(location, field="location"),
        accessibility=_filter_text(accessibility, field="accessibility"),
        excluded_ids=excluded,
    )
    return [_to_out(venue) for venue in venue_store.repository().list_venues(filters)]


@router.get("/{venue_id}", response_model=VenueOut)
def get_venue(
    venue_id: str,
    _: Annotated[User, Depends(require_permission(Permission.VENUES_READ))],
) -> VenueOut:
    """US9.2: open any venue record. Details only — nothing here books it."""
    venue = venue_store.repository().get_venue(_as_id(venue_id))
    if venue is None:
        raise _not_found()
    return _to_out(venue)


class VenueInput(BaseModel):
    """What Venue Staff send to create or update a venue (US9.1a, US9.1b).

    The required and optional split is US9.1a's, and it is the same shape for an
    update: US9.1b says any field is editable except the system-generated ones,
    and those are simply not in this model. `id` and `createdAt` cannot be sent
    here, so a request that includes them changes nothing rather than being
    refused — there is no field for them to land in.

    Text is kept as supplied, trimmed only at the ends. Validation must not
    rewrite what Venue Staff typed about their own venue.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    location: str = ""
    #: Required and positive (US9.1a). Optional here so a missing field is a
    #: sentence from `_validated` rather than Pydantic's own 422.
    capacity: int | None = None
    facilities: str = ""
    accessibility_features: str = Field(default="", alias="accessibilityFeatures")
    operating_hours: str = Field(default="", alias="operatingHours")
    supported_layouts: str = Field(default="", alias="supportedLayouts")
    #: US9.4: whole minutes, 0 or more, 0 when left out. Typed loosely so a
    #: decimal, a word or `true` is a sentence from `_validated` rather than a
    #: 422; `venue_turnaround.parse_minutes` is the one reading of them.
    setup_minutes: bool | int | float | str | None = Field(default=None, alias="setupMinutes")
    turnaround_minutes: bool | int | float | str | None = Field(
        default=None, alias="turnaroundMinutes"
    )


#: `venues.name` is VARCHAR(255) and `venues.location` VARCHAR(500). Checking
#: here turns a database error into a sentence the form can show.
NAME_MAX = 255
LOCATION_MAX = 500
#: Postgres `integer`. A capacity beyond this is a typo, and letting it through
#: would be a 500 from the driver rather than a message about the field.
CAPACITY_MAX = 2_147_483_647


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": VenueError.INVALID, "message": message},
    )


def _validated(payload: VenueInput) -> VenueInput:
    """US9.1a: name, capacity and location are required; capacity is positive.

    Everything else is optional and may be left empty. The order matters only
    in that the message names one problem at a time, starting with the field a
    form shows first.
    """
    name = payload.name.strip()
    location = payload.location.strip()

    if not name:
        raise _invalid("Give the venue a name.")
    if len(name) > NAME_MAX:
        raise _invalid(f"Keep the name to {NAME_MAX} characters or fewer.")
    if not location:
        raise _invalid("Give the venue a location.")
    if len(location) > LOCATION_MAX:
        raise _invalid(f"Keep the location to {LOCATION_MAX} characters or fewer.")
    if payload.capacity is None:
        raise _invalid("Give the venue a capacity.")
    # US9.1a says a positive integer, so zero is refused as well as a negative.
    # A venue that holds nobody is not a venue anyone can plan around.
    if payload.capacity < 1:
        raise _invalid("Capacity must be a positive whole number of people.")
    if payload.capacity > CAPACITY_MAX:
        raise _invalid("That capacity is larger than any venue this system can hold.")
    try:
        setup = venue_turnaround.parse_minutes(payload.setup_minutes, which="setup")
        turnaround = venue_turnaround.parse_minutes(
            payload.turnaround_minutes, which="turnaround"
        )
    except InvalidMinutes as error:
        raise _invalid(str(error)) from None

    return VenueInput(
        name=name,
        location=location,
        capacity=payload.capacity,
        facilities=payload.facilities.strip(),
        accessibility_features=payload.accessibility_features.strip(),
        operating_hours=payload.operating_hours.strip(),
        supported_layouts=payload.supported_layouts.strip(),
        setup_minutes=setup,
        turnaround_minutes=turnaround,
    )


def _minutes(clean: VenueInput) -> dict[str, int]:
    """The two US9.4 values of a validated input, as the store takes them."""
    return {
        "setup_minutes": int(clean.setup_minutes or 0),
        "turnaround_minutes": int(clean.turnaround_minutes or 0),
    }


def _taken(error: DuplicateVenueName) -> HTTPException:
    """US9.1a/b: `venues.name` is UNIQUE, so a clash is a rule, not a crash."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": VenueError.NAME_TAKEN, "message": str(error)},
    )


@router.post("", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
def create_venue(
    payload: VenueInput,
    _: Annotated[User, Depends(require_permission(Permission.VENUES_CREATE))],
) -> VenueOut:
    """US9.1a: Venue Staff add a venue, so Coordinators have it to plan around."""
    clean = _validated(payload)
    try:
        created = venue_store.repository().create_venue(
            name=clean.name,
            location=clean.location,
            capacity=clean.capacity or 0,
            facilities=clean.facilities,
            accessibility_features=clean.accessibility_features,
            operating_hours=clean.operating_hours,
            supported_layouts=clean.supported_layouts,
            **_minutes(clean),
        )
    except DuplicateVenueName as error:
        raise _taken(error) from error
    return _to_out(created)


class BookingWindowOut(BaseModel):
    """One booking in a US9.4 conflict: its own times and what it really occupies."""

    booking_id: str = Field(serialization_alias="bookingId")
    event_id: str = Field(serialization_alias="eventId")
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    occupied_from: str = Field(serialization_alias="occupiedFrom")
    occupied_to: str = Field(serialization_alias="occupiedTo")


class ConflictOut(BaseModel):
    first: BookingWindowOut
    second: BookingWindowOut
    #: True when the new setup or turnaround time is what made the pair clash.
    caused_by_change: bool = Field(serialization_alias="causedByChange")


class RecheckOut(BaseModel):
    """US9.4 kicks off US15.2's re-check; this is what it found."""

    setup_minutes: int = Field(serialization_alias="setupMinutes")
    turnaround_minutes: int = Field(serialization_alias="turnaroundMinutes")
    checked_bookings: int = Field(serialization_alias="checkedBookings")
    conflicts: list[ConflictOut]
    #: US15.2: bookings this change marked "Conflict – review needed". Their
    #: Coordinators have been notified. Already-flagged bookings are not repeated.
    flagged_booking_ids: list[str] = Field(
        default_factory=list, serialization_alias="flaggedBookingIds"
    )
    #: US15.2: flagged bookings whose clash this change resolved.
    cleared_booking_ids: list[str] = Field(
        default_factory=list, serialization_alias="clearedBookingIds"
    )


class VenueSavedOut(VenueOut):
    #: Set only when setup or turnaround changed, which is what triggers it.
    recheck: RecheckOut | None = None


def _window_out(item: OccupiedBooking) -> BookingWindowOut:
    return BookingWindowOut(
        booking_id=str(item.booking.id),
        event_id=str(item.booking.event_id),
        starts_at=item.booking.starts_at,
        ends_at=item.booking.ends_at,
        occupied_from=item.occupied_from.isoformat(timespec="minutes"),
        occupied_to=item.occupied_to.isoformat(timespec="minutes"),
    )


def _conflict_out(conflict: BookingConflict) -> ConflictOut:
    return ConflictOut(
        first=_window_out(conflict.first),
        second=_window_out(conflict.second),
        caused_by_change=conflict.caused_by_change,
    )


def _recheck_out(result: Recheck, review: conflict_flags.Review | None) -> RecheckOut:
    return RecheckOut(
        setup_minutes=result.setup_minutes,
        turnaround_minutes=result.turnaround_minutes,
        checked_bookings=result.checked,
        conflicts=[_conflict_out(conflict) for conflict in result.conflicts],
        flagged_booking_ids=[str(b.id) for b in review.flagged] if review else [],
        cleared_booking_ids=[str(b.id) for b in review.cleared] if review else [],
    )


@router.put("/{venue_id}", response_model=VenueSavedOut)
def save_venue(
    venue_id: str,
    payload: VenueInput,
    _: Annotated[User, Depends(require_permission(Permission.VENUES_EDIT))],
) -> VenueSavedOut:
    """US9.1b: update a venue, so the catalogue keeps up with the building.

    Every field is editable except `id` and `created_at`, which `VenueInput`
    has no room for. A venue keeps its own name, so renaming it to what it
    already is is not a clash.

    US9.4: changing the setup or turnaround time re-checks every booking that
    holds the venue under the new values. Bookings that now clash are reported
    in `recheck` - identified, not removed or cancelled.

    US15.2: each future active booking that now clashes, with another booking
    or an unavailability period, is also marked "Conflict – review needed" and
    its Coordinator notified; flags whose clash the change resolved are cleared.
    The save has already happened, so a failure here is logged, not returned.
    """
    existing = venue_store.repository().get_venue(_as_id(venue_id))
    if existing is None:
        raise _not_found()

    clean = _validated(payload)
    try:
        saved = venue_store.repository().save_venue(
            existing.id,
            name=clean.name,
            location=clean.location,
            capacity=clean.capacity or 0,
            facilities=clean.facilities,
            accessibility_features=clean.accessibility_features,
            operating_hours=clean.operating_hours,
            supported_layouts=clean.supported_layouts,
            **_minutes(clean),
        )
    except DuplicateVenueName as error:
        raise _taken(error) from error

    result = None
    if saved.buffers != existing.buffers:
        result = _recheck_out(
            venue_turnaround.recheck(
                booking_store.repository().list_for_venue(saved.id),
                before=existing.buffers,
                after=saved.buffers,
            ),
            conflict_flags.recheck_quietly(saved),
        )
    return VenueSavedOut(**_to_out(saved).model_dump(), recheck=result)


@router.delete("/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_venue(
    venue_id: str,
    _: Annotated[User, Depends(require_permission(Permission.VENUES_DELETE))],
) -> Response:
    """US9.1c: remove a venue that is no longer in use. A hard delete.

    404 for a venue that is not there, rather than a quiet 204. Deleting
    something that was already gone is usually a sign the caller is working
    from a stale list, and saying so is more use than pretending it worked.

    409 for a venue an event has booked (US14.1). A venue with bookings is in
    use, and deleting it would either take an event's booking with it or, as
    `venue_bookings.venue_id` has no cascade, fail in the database.
    """
    existing = venue_store.repository().get_venue(_as_id(venue_id))
    if existing is None:
        raise _not_found()
    if booking_store.repository().venue_has_bookings(existing.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": VenueError.IN_USE,
                "message": (
                    f"{existing.name} has venue bookings, so it cannot be removed "
                    "from the catalogue."
                ),
            },
        )
    venue_store.repository().delete_venue(existing.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- US12.1: blackout periods --------------------------------------------------
#
# Venue Staff mark the days a venue cannot be used; Coordinators see them when
# they open the venue. Recording a blackout is maintaining the venue record, so
# it takes the same `venues:edit` that US9.1b does rather than a permission of
# its own — the same role holds both, and a second name for the same grant
# would be one more thing for the frontend's copy of the catalogue to drift on.
#
# This only records and displays. Nothing here checks a range against venue
# bookings or against other ranges: comparing a booking with the venue's
# blackouts is US15.1's availability check, made per booking.


class UnavailabilityOut(BaseModel):
    id: str
    venue_id: str = Field(serialization_alias="venueId")
    #: "YYYY-MM-DD", inclusive at both ends.
    start_date: str = Field(serialization_alias="startDate")
    end_date: str = Field(serialization_alias="endDate")
    #: US12.2: Structured reason type (maintenance, equipment_failure, etc.)
    reason_type: str = Field(serialization_alias="reasonType")
    #: US12.2: Custom reason text when reason_type = "other", otherwise empty
    other_reason: str = Field(serialization_alias="otherReason")
    created_at: str = Field(serialization_alias="createdAt")
    #: US12.2: How many bookings were flagged as needing replacement
    flagged_bookings_count: int | None = Field(
        default=None, serialization_alias="flaggedBookingsCount"
    )


def _unavailability_out(
    entry: Unavailability, flagged_count: int | None = None
) -> UnavailabilityOut:
    return UnavailabilityOut(
        id=str(entry.id),
        venue_id=str(entry.venue_id),
        start_date=entry.start_date.isoformat(),
        end_date=entry.end_date.isoformat(),
        reason_type=entry.reason_type.value,
        other_reason=entry.other_reason,
        created_at=entry.created_at,
        flagged_bookings_count=flagged_count,
    )


class UnavailabilityInput(BaseModel):
    """What Venue Staff send to mark a venue unavailable.

    The dates are text rather than `date` so that a missing, malformed or
    impossible date is a sentence from `_validated_range` with this module's
    400, not Pydantic's 422 — the same reason `VenueInput.capacity` is optional.

    US12.2: reason is now structured with reason_type (enum) and other_reason
    (custom text when type = "other").
    """

    model_config = ConfigDict(populate_by_name=True)

    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    #: US12.2: Required structured reason type
    reason_type: str | None = Field(default=None, alias="reasonType")
    #: US12.2: Required when reason_type = "other", otherwise should be empty
    other_reason: str | None = Field(default=None, alias="otherReason")


#: The column is TEXT. The cap is about a note staying a note, not a width.
REASON_MAX = 500

#: Exactly YYYY-MM-DD in ASCII digits. `date.fromisoformat` alone is looser
#: than that — it takes "20261001" — and a date the form did not mean to send
#: should be refused, not reinterpreted. `[0-9]` rather than `\d`, which would
#: pass other scripts' digits on to be misreported as an impossible date.
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _invalid_range(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": VenueError.INVALID_UNAVAILABILITY, "message": message},
    )


def _iso_date(text: str, *, which: str, refuse: Callable[[str], HTTPException]) -> date:
    """One reading of a date for the form and the filter, refused in the caller's terms."""
    if not _ISO_DATE.fullmatch(text):
        raise refuse(f"Give the {which} date as YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except ValueError:
        # Well-formed but not on any calendar: 2026-02-30, month 13, year 0000.
        raise refuse(f"The {which} date {text} is not a real calendar date.") from None


def _parse_date(raw: str | None, *, which: str) -> date:
    text = (raw or "").strip()
    if not text:
        raise _invalid_range(f"Give the {which} date.")
    return _iso_date(text, which=which, refuse=_invalid_range)


def _filter_date(text: str, *, which: str) -> date:
    return _iso_date(text, which=which, refuse=_invalid_filter)


def _availability_window(raw_from: str, raw_to: str) -> tuple[date, date] | None:
    """The catalogue's planning dates, or None when none were asked for.

    Either date alone is that single day. Reading "from the 2nd" as "the 2nd
    onwards" would rule out every venue with any closure in its future, which
    is not a question anyone planning one event is asking.
    """
    from_text, to_text = raw_from.strip(), raw_to.strip()
    if not from_text and not to_text:
        return None
    # Each box is read under its own name, so a bad date is blamed on the box
    # it was typed in even when the other one is empty.
    if from_text and to_text:
        start = _filter_date(from_text, which="available-from")
        end = _filter_date(to_text, which="available-to")
    elif from_text:
        start = end = _filter_date(from_text, which="available-from")
    else:
        start = end = _filter_date(to_text, which="available-to")
    if end < start:
        raise _invalid_filter(
            "The available-to date cannot be earlier than the available-from date."
        )
    return start, end


def _validated_range(
    payload: UnavailabilityInput,
) -> tuple[date, date, venue_unavailability_store.UnavailabilityReasonType, str]:
    """US12.1/US12.2: validate dates and structured reason.

    Equal dates are a one-day closure and are accepted. One problem is named at
    a time, start first, which is the order the form shows the fields in.

    US12.2: reason_type is required and must be a valid enum value. When
    reason_type = "other", other_reason must be provided.
    """
    start = _parse_date(payload.start_date, which="start")
    end = _parse_date(payload.end_date, which="end")
    if end < start:
        raise _invalid_range("The end date cannot be earlier than the start date.")

    # US12.2: Validate structured reason
    reason_type_raw = (payload.reason_type or "").strip()
    if not reason_type_raw:
        raise _invalid_range("Give a reason type for the unavailability.")

    # Validate reason_type is a valid enum value
    try:
        reason_type = venue_unavailability_store.UnavailabilityReasonType(reason_type_raw)
    except ValueError:
        valid_types = ", ".join(t.value for t in venue_unavailability_store.UnavailabilityReasonType)
        raise _invalid_range(
            f'Reason type must be one of: {valid_types}.'
        ) from None

    # Validate other_reason when reason_type = "other"
    other_reason = (payload.other_reason or "").strip()
    if reason_type is venue_unavailability_store.UnavailabilityReasonType.OTHER:
        if not other_reason:
            raise _invalid_range('Give a custom reason when selecting "other".')
        if len(other_reason) > REASON_MAX:
            raise _invalid_range(f"Keep the custom reason to {REASON_MAX} characters or fewer.")
    elif other_reason:
        # If not "other", other_reason should be empty
        raise _invalid_range('Only provide a custom reason when reason type is "other".')

    return start, end, reason_type, other_reason


def _existing_venue(venue_id: str) -> Venue:
    venue = venue_store.repository().get_venue(_as_id(venue_id))
    if venue is None:
        raise _not_found()
    return venue


@router.get("/{venue_id}/unavailability", response_model=list[UnavailabilityOut])
def list_unavailability(
    venue_id: str,
    _: Annotated[User, Depends(require_permission(Permission.VENUES_READ))],
) -> list[UnavailabilityOut]:
    """US12.1: a venue's blackout periods, soonest first.

    Read with the catalogue's own permission, so anyone who can open a venue can
    see when it is closed. Past ranges are included: the story asks for the
    record, and trimming it to the future is a filter nobody has asked for yet.
    """
    venue = _existing_venue(venue_id)
    entries = venue_unavailability_store.repository().list_for_venue(venue.id)
    return [_unavailability_out(entry) for entry in entries]


@router.post(
    "/{venue_id}/unavailability",
    response_model=UnavailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def mark_unavailable(
    venue_id: str,
    payload: UnavailabilityInput,
    user: Annotated[User, Depends(require_permission(Permission.VENUES_EDIT))],
) -> UnavailabilityOut:
    """US12.1/US12.2: Venue Staff record a date range the venue cannot be used.

    404 before 400, as `save_venue` does: a range for a venue that is not there
    is wrong however well-formed its dates are.

    US12.2: A database trigger automatically flags any active bookings (Requested,
    Held, or Confirmed) whose effective window overlaps the unavailability period.
    The response includes the count of bookings flagged, and affected Coordinators
    are notified once per event.
    """
    venue = _existing_venue(venue_id)
    start, end, reason_type, other_reason = _validated_range(payload)
    created = venue_unavailability_store.repository().create(
        venue_id=venue.id,
        start_date=start,
        end_date=end,
        reason_type=reason_type,
        other_reason=other_reason,
        created_by_id=user.id,
    )

    # US12.2: Count how many bookings were flagged by this unavailability period.
    # The database trigger has already flagged them; we just need to count.
    flagged_bookings = (
        supabase_client.admin()
        .table("venue_bookings")
        .select("id", count="exact")
        .eq("flagged_by_unavailability_id", created.id)
        .execute()
    )
    flagged_count = flagged_bookings.count or 0

    return _unavailability_out(created, flagged_count=flagged_count)