"""What an event request needs of its venue and setup — US2.1, reopened in Sprint 3.

The customer clarified which fields an event request must have before it is
submitted. On top of the original details (name, purpose, date and times,
attendance) a request now has to say what it needs:

* venue requirements — the facilities the venue must have;
* a preferred layout;
* accessibility needs;
* equipment needs;
* registration needs.

Layout, facilities and accessibility are picked from fixed lists that use the
venue catalogue's own words (US9.1a), so a request can be checked against a
venue the way US18.1's suitability check reads one. Equipment and registration
needs are described in words. Every one of the five can instead be answered
"None / Not required": a field that does not apply is answered, not skipped.

Drafts (US2.2) still save without any of this being filled in. Only a value
that is not one of the fixed options is refused on a draft, because it can
never become valid by being completed later.

Values are stored as text, the way the venue catalogue stores its lists: a
multi-choice answer is its options joined with ", ". No option contains a
comma, so the join reads back unambiguously. An empty value means "not answered
yet", which is what a draft may leave.

This module is pure, so each rule is tested as a plain function.
"""

from dataclasses import dataclass, fields

#: The answer for a field that does not apply to this event.
NOT_REQUIRED = "None / Not required"

#: In the order the form lists them. The words are the venue catalogue's.
LAYOUT_OPTIONS: tuple[str, ...] = (
    "Theatre",
    "Classroom",
    "Boardroom",
    "Banquet",
    "Cabaret",
    "Standing",
    "Reception",
    "Breakout tables",
    "Workshop",
    "Exhibition",
    "Concert",
    "Fixed tiered seating",
)

FACILITY_OPTIONS: tuple[str, ...] = (
    "Stage",
    "AV system",
    "PA system",
    "Sound system",
    "Projector",
    "Screen",
    "Whiteboard",
    "Video conferencing",
    "Recording equipment",
    "Lectern",
    "Interpretation booth",
    "Catering area",
    "Kitchenette",
    "Green room",
    "Power outlets",
    "Outdoor seating",
)

ACCESSIBILITY_OPTIONS: tuple[str, ...] = (
    "Wheelchair access",
    "Step-free access",
    "Accessible toilets",
    "Lift",
    "Hearing loop",
    "Reserved seating",
)

#: A cap for readability, not the column: the free-text answers are TEXT.
FREE_TEXT_MAX = 1000


@dataclass(frozen=True)
class EventNeeds:
    """The five answers, named as `event_store.Event` names them."""

    venue_requirements: str = ""
    preferred_layout: str = ""
    accessibility_needs: str = ""
    equipment_needs: str = ""
    registration_needs: str = ""

    def as_attrs(self) -> dict[str, str]:
        """The answers keyed by `Event` attribute, for `dataclasses.replace`."""
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def as_columns(self) -> dict[str, str | None]:
        """The answers as `events` columns; an unanswered field is written NULL."""
        return {name: value or None for name, value in self.as_attrs().items()}


#: An event that has answered none of them yet.
NO_NEEDS = EventNeeds()

#: The attribute names, which are also the `events` column names.
NEED_FIELDS: tuple[str, ...] = tuple(item.name for item in fields(EventNeeds))


def listed(value: str) -> tuple[str, ...]:
    """The options a multi-choice answer holds, as written."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _choice_error(value: str, options: tuple[str, ...], *, what: str) -> str | None:
    """Why a multi-choice answer is not made of the fixed options, or None."""
    chosen = listed(value)
    if NOT_REQUIRED in chosen and len(chosen) > 1:
        return f"Choose {what}, or {NOT_REQUIRED} — not both."
    unknown = [item for item in chosen if item != NOT_REQUIRED and item not in options]
    if unknown:
        return f"Choose {what} from the list. {unknown[0]} is not one of the options."
    return None


def format_error(needs: EventNeeds) -> str | None:
    """Why these answers could never be submitted as they stand, or None.

    Applies to drafts as well as submissions: blanks are allowed, values from
    outside the fixed lists are not.
    """
    problem = _choice_error(
        needs.venue_requirements, FACILITY_OPTIONS, what="the venue requirements"
    ) or _choice_error(
        needs.accessibility_needs, ACCESSIBILITY_OPTIONS, what="the accessibility needs"
    )
    if problem:
        return problem
    layout = needs.preferred_layout.strip()
    if layout and layout != NOT_REQUIRED and layout not in LAYOUT_OPTIONS:
        return f"Choose a preferred layout from the list. {layout} is not one of the options."
    if len(needs.equipment_needs) > FREE_TEXT_MAX:
        return f"Keep the equipment needs to {FREE_TEXT_MAX} characters or fewer."
    if len(needs.registration_needs) > FREE_TEXT_MAX:
        return f"Keep the registration needs to {FREE_TEXT_MAX} characters or fewer."
    return None


#: What each field says when it is left unanswered at submission, in form order.
MISSING_MESSAGES: dict[str, str] = {
    "venue_requirements": f"Choose the venue requirements, or {NOT_REQUIRED}.",
    "preferred_layout": f"Choose a preferred layout, or {NOT_REQUIRED}.",
    "accessibility_needs": f"Choose the accessibility needs, or {NOT_REQUIRED}.",
    "equipment_needs": f"Describe the equipment needs, or choose {NOT_REQUIRED}.",
    "registration_needs": f"Describe the registration needs, or choose {NOT_REQUIRED}.",
}


def missing_error(needs: EventNeeds) -> str | None:
    """The first field a submission has left unanswered, or None."""
    for name, message in MISSING_MESSAGES.items():
        if not getattr(needs, name).strip():
            return message
    return None
