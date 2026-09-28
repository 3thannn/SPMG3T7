"""Venue data access, backed by the Supabase `venues` table — US9.2.

The table has been in the schema since the first setup script and until now
nothing read it. US9.2 reads it, US9.3 narrows it, and US9.1a-c write it. Reading and writing
are held by different roles — a Coordinator reads, Venue Staff maintain — and
the routes above enforce that; this module is only the access.

Two choices worth knowing:

* `facilities`, `accessibility_features` and `operating_hours` are all nullable
  columns, and each comes back as an empty string rather than None. A venue with
  no accessibility notes recorded is not a venue with a null — it is one nobody
  has filled in, and the page says "Not recorded" either way. `capacity` is NOT
  NULL, so it stays an int and needs no such treatment.
* The catalogue is ordered by name in the database rather than in Python. It is
  the order a catalogue is read in, and `ix_venues_name` already exists for it.

US9.3 added filtering, and it happens in the database rather than in Python —
the same reason `list_events` gives: a catalogue narrowed before it leaves
Postgres is one this process cannot forget to narrow. `VenueFilters` carries the
criteria, and the two stores below are held to the same reading of them.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from app import supabase_client

TABLE = "venues"
#: Exactly the columns the schema has, in the order the detail page reads them.
COLUMNS = (
    "id, name, location, capacity, facilities, accessibility_features, "
    "operating_hours, supported_layouts, created_at, updated_at"
)


class DuplicateVenueName(Exception):
    """`venues.name` is UNIQUE and the name asked for is taken.

    Raised by the store rather than left as a Postgres error, so the route can
    answer 409 with the name in it instead of leaking a constraint violation.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"A venue called {name!r} is already in the catalogue.")
        self.name = name


#: Postgres unique-violation SQLSTATE, as PostgREST reports it.
_UNIQUE_VIOLATION = "23505"


def _as_duplicate(error: Exception, name: str) -> Exception:
    """Turn a unique-violation into `DuplicateVenueName`; leave everything else.

    PostgREST reports the SQLSTATE in the error body, so this reads the code
    rather than matching message text, which is localised and version
    dependent. Any other error is returned untouched to be re-raised: a write
    that failed because the database was unreachable is not a name clash.
    """
    code = getattr(error, "code", None)
    if code is None:
        args = getattr(error, "args", None)
        if args and isinstance(args[0], dict):
            code = args[0].get("code")
    if str(code) == _UNIQUE_VIOLATION:
        return DuplicateVenueName(name)
    return error


def _now() -> str:
    """A naive UTC timestamp, matching the column type."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


#: Characters Postgres reads as wildcards inside a LIKE pattern. A Coordinator
#: typing "100%" into the location box means a literal per-cent sign, so these
#: are escaped rather than honoured — backslash is Postgres's default LIKE
#: escape character, which is what makes the escaping work without an ESCAPE
#: clause (PostgREST does not expose one).
_LIKE_WILDCARDS = ("\\", "%", "_")


def _contains_pattern(value: str) -> str:
    """A LIKE pattern matching `value` as a literal substring, case aside."""
    escaped = value
    for character in _LIKE_WILDCARDS:
        escaped = escaped.replace(character, "\\" + character)
    return f"%{escaped}%"


@dataclass(frozen=True)
class VenueFilters:
    """US9.3: narrow the catalogue by capacity, location and accessibility.

    Every applied filter must match — AND, not OR. A Coordinator asking for 200
    seats *and* step-free access wants both, and returning the union would hand
    back exactly the rows they ruled out.

    An absent filter is not a filter. `min_capacity` of None and an empty
    location are both "did not ask", which is why the text fields are compared
    after stripping: a box holding only spaces has not been filled in.
    """

    #: Venues holding at least this many people. None means no floor.
    min_capacity: int | None = None
    #: Matched as a case-insensitive substring of `venues.location`.
    location: str = ""
    #: Matched as a case-insensitive substring of `venues.accessibility_features`.
    #: A venue with nothing recorded therefore never matches, which is the
    #: honest answer — an unfilled field is not evidence of a feature.
    accessibility: str = ""
    #: US12.1: venues to leave out — those with a blackout period over the
    #: dates a Coordinator is planning for. Ids rather than dates, so this store
    #: needs to know nothing about blackouts; the route works out which venues
    #: they rule out and hands the answer over.
    excluded_ids: frozenset[int] = frozenset()

    @property
    def applied(self) -> bool:
        """Whether anything was actually asked for."""
        return (
            self.min_capacity is not None
            or bool(self.location.strip())
            or bool(self.accessibility.strip())
            or bool(self.excluded_ids)
        )


#: The unfiltered catalogue, named so a caller reads as asking for all of it.
NO_FILTERS = VenueFilters()


@dataclass(frozen=True)
class Venue:
    id: int
    name: str
    location: str
    capacity: int
    #: Nullable in the database; empty string when nothing is recorded.
    facilities: str
    accessibility_features: str
    operating_hours: str
    created_at: str
    updated_at: str
    #: `venues.supported_layouts`. Last in the field order because it has a
    #: default: US9.1a names it as an optional field and it was added to the
    #: schema for that story, after the columns above.
    supported_layouts: str = ""


def to_venue(row: dict) -> Venue:
    """Build a Venue from a table row, flattening the nullable text columns."""
    return Venue(
        id=row["id"],
        name=row.get("name") or "",
        location=row.get("location") or "",
        # NOT NULL in the schema, so the `or 0` is for a malformed row rather
        # than an empty one — a venue with no capacity would still render.
        capacity=row.get("capacity") or 0,
        facilities=row.get("facilities") or "",
        accessibility_features=row.get("accessibility_features") or "",
        operating_hours=row.get("operating_hours") or "",
        supported_layouts=row.get("supported_layouts") or "",
        created_at=str(row["created_at"]) if row.get("created_at") else "",
        updated_at=str(row["updated_at"]) if row.get("updated_at") else "",
    )


class Repository(Protocol):
    """What the routes need from a venue store."""

    def list_venues(self, filters: VenueFilters = NO_FILTERS) -> list[Venue]: ...

    def get_venue(self, venue_id: int) -> Venue | None: ...

    def create_venue(
        self,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue: ...

    def save_venue(
        self,
        venue_id: int,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue: ...

    def delete_venue(self, venue_id: int) -> None: ...


class SupabaseVenues:
    """The real store. Goes through the service role client, like the others."""

    def list_venues(self, filters: VenueFilters = NO_FILTERS) -> list[Venue]:
        """US9.3: narrow in the database, so unwanted rows never leave it."""
        query = supabase_client.admin().table(TABLE).select(COLUMNS)

        if filters.min_capacity is not None:
            query = query.gte("capacity", filters.min_capacity)

        location = filters.location.strip()
        if location:
            query = query.ilike("location", _contains_pattern(location))

        accessibility = filters.accessibility.strip()
        if accessibility:
            query = query.ilike("accessibility_features", _contains_pattern(accessibility))

        if filters.excluded_ids:
            # Sorted so the same exclusions always make the same request.
            query = query.not_.in_("id", sorted(filters.excluded_ids))

        # Chained filters are ANDed by PostgREST, which is the rule US9.3 asks
        # for: a venue has to satisfy every criterion, not any one of them.
        rows = query.order("name").execute().data or []
        return [to_venue(row) for row in rows]

    def get_venue(self, venue_id: int) -> Venue | None:
        response = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("id", venue_id)
            .limit(1)
            .execute()
        )
        return to_venue(response.data[0]) if response.data else None

    def _writable(
        self,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> dict:
        """The columns a write sends, in one place so create and update cannot drift.

        `id` and `created_at` are absent, and that absence is US9.1b's rule
        about system-generated fields: there is no path through here that could
        move them, so the route does not have to refuse a request that tries.

        The optional text columns are nullable, and an empty field is stored as
        NULL rather than "". Both read back as "" through `to_venue`, so the
        choice is invisible to a caller — but it keeps "nothing recorded" as one
        state in the database instead of two that mean the same thing.
        """
        return {
            "name": name,
            "location": location,
            "capacity": capacity,
            "facilities": facilities or None,
            "accessibility_features": accessibility_features or None,
            "operating_hours": operating_hours or None,
            "supported_layouts": supported_layouts or None,
        }

    def create_venue(
        self,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue:
        """US9.1a: add a venue to the catalogue."""
        at = _now()
        row = {
            **self._writable(
                name=name,
                location=location,
                capacity=capacity,
                facilities=facilities,
                accessibility_features=accessibility_features,
                operating_hours=operating_hours,
                supported_layouts=supported_layouts,
            ),
            "created_at": at,
            "updated_at": at,
        }
        try:
            created = supabase_client.admin().table(TABLE).insert(row).execute()
        except Exception as error:
            raise _as_duplicate(error, name) from error

        # The insert response is read back rather than trusted, so a default or
        # trigger the database applied is what the caller gets.
        venue = self.get_venue(created.data[0]["id"])
        assert venue is not None  # noqa: S101 — the row was just inserted
        return venue

    def save_venue(
        self,
        venue_id: int,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue:
        """US9.1b: every field is writable except the ones the system owns."""
        changes = {
            **self._writable(
                name=name,
                location=location,
                capacity=capacity,
                facilities=facilities,
                accessibility_features=accessibility_features,
                operating_hours=operating_hours,
                supported_layouts=supported_layouts,
            ),
            "updated_at": _now(),
        }
        try:
            supabase_client.admin().table(TABLE).update(changes).eq("id", venue_id).execute()
        except Exception as error:
            raise _as_duplicate(error, name) from error

        saved = self.get_venue(venue_id)
        assert saved is not None  # noqa: S101 — the row was just updated
        return saved

    def delete_venue(self, venue_id: int) -> None:
        """US9.1c: a hard delete.

        No referential check, because nothing books a venue yet and so no row
        can be orphaned by this. That check becomes necessary with Sprint 3's
        booking feature, and this is where it belongs when it does.
        """
        supabase_client.admin().table(TABLE).delete().eq("id", venue_id).execute()


def _matches(venue: Venue, filters: VenueFilters) -> bool:
    """Every applied filter, ANDed — the shared definition of a match."""
    if venue.id in filters.excluded_ids:
        return False

    if filters.min_capacity is not None and venue.capacity < filters.min_capacity:
        return False

    location = filters.location.strip().lower()
    if location and location not in venue.location.lower():
        return False

    accessibility = filters.accessibility.strip().lower()
    if accessibility and accessibility not in venue.accessibility_features.lower():
        return False

    return True


@dataclass
class InMemoryVenues:
    """A stand-in for tests, ordered by name the way the real query is."""

    venues: list[Venue] = field(default_factory=list)
    #: Well clear of the fixture ids, so a created venue is obvious in a test.
    next_id: int = 100

    def list_venues(self, filters: VenueFilters = NO_FILTERS) -> list[Venue]:
        """The same reading of the filters as the SQL above, in Python.

        Substring and case-insensitive, matching `ilike` with an escaped
        pattern: the text a Coordinator types is literal, not a wildcard.
        """
        matched = [venue for venue in self.venues if _matches(venue, filters)]
        return sorted(matched, key=lambda venue: venue.name)

    def get_venue(self, venue_id: int) -> Venue | None:
        return next((venue for venue in self.venues if venue.id == venue_id), None)

    def _taken(self, name: str, *, excluding: int | None = None) -> bool:
        """Whether another row already holds this name, matching the UNIQUE index."""
        return any(venue.name == name and venue.id != excluding for venue in self.venues)

    def create_venue(
        self,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue:
        if self._taken(name):
            raise DuplicateVenueName(name)
        self.next_id += 1
        at = _now()
        venue = Venue(
            id=self.next_id,
            name=name,
            location=location,
            capacity=capacity,
            facilities=facilities,
            accessibility_features=accessibility_features,
            operating_hours=operating_hours,
            supported_layouts=supported_layouts,
            created_at=at,
            updated_at=at,
        )
        self.venues.append(venue)
        return venue

    def save_venue(
        self,
        venue_id: int,
        *,
        name: str,
        location: str,
        capacity: int,
        facilities: str,
        accessibility_features: str,
        operating_hours: str,
        supported_layouts: str,
    ) -> Venue:
        existing = self.get_venue(venue_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        if self._taken(name, excluding=venue_id):
            raise DuplicateVenueName(name)
        # `id` and `created_at` are carried over rather than taken, the same way
        # the real store leaves them out of the update.
        saved = replace(
            existing,
            name=name,
            location=location,
            capacity=capacity,
            facilities=facilities,
            accessibility_features=accessibility_features,
            operating_hours=operating_hours,
            supported_layouts=supported_layouts,
            updated_at=_now(),
        )
        self.venues = [saved if v.id == venue_id else v for v in self.venues]
        return saved

    def delete_venue(self, venue_id: int) -> None:
        self.venues = [venue for venue in self.venues if venue.id != venue_id]


_repository: Repository = SupabaseVenues()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
