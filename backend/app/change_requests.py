"""US11.1 — an Organiser asks for changes to a submitted event instead of making them.

Once an event is submitted it is the Coordinator's to review, so the Organiser
no longer edits it directly. They fill in the same edit form, and what they
send becomes a *proposal*: one `event_change_requests` row per field that
differs, marked pending, while the event itself keeps its current values until
a Coordinator approves. Only then is each field applied and logged to
`event_changes`, which stays a record of changes that actually happened.

This module is the rules half, kept free of storage and HTTP so each rule can be
tested as a plain function — which fields exist, which of them are important,
what counts as a change, and when a request may be made or reviewed.

"Important" follows US5.2's logging rule: changes to date/time, attendance,
venue or equipment are flagged so a Coordinator does not miss them among
routine wording edits.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.event_status import EventStatus


@dataclass(frozen=True)
class FieldChange:
    """One proposed edit: a column, what it holds now, and what is asked for.

    Values are text, as `event_change_requests` and `event_changes` store them. An
    empty string means "not set" — a cleared end date, or no attendance estimate.
    """

    field: str
    old_value: str
    new_value: str
    important: bool


@dataclass(frozen=True)
class EditableField:
    """A column the edit form can change, and how to read and compare it."""

    #: The `events` column, which is also what `event_changes.changed_field` holds.
    column: str
    #: The matching attribute on `event_store.Event`.
    attr: str
    #: The form's label for it, so a Coordinator reads the same word the
    #: Organiser typed against.
    label: str
    kind: str = "text"


#: In the order the form shows them, which is the order a proposal is listed in.
EDITABLE_FIELDS: tuple[EditableField, ...] = (
    EditableField("name", "title", "Title"),
    EditableField("proposed_date", "starts_at", "Starts", kind="datetime"),
    EditableField("end_date", "ends_at", "Ends", kind="datetime"),
    EditableField("purpose", "purpose", "Purpose"),
    EditableField("expected_attendance", "expected_attendance", "Expected attendance", kind="int"),
    EditableField("description", "description", "Description"),
    # US2.1 (Sprint 3): what the event needs. Text, as `app.event_needs` stores it.
    EditableField("venue_requirements", "venue_requirements", "Venue requirements"),
    EditableField("preferred_layout", "preferred_layout", "Preferred layout"),
    EditableField("accessibility_needs", "accessibility_needs", "Accessibility needs"),
    EditableField("equipment_needs", "equipment_needs", "Equipment needs"),
    EditableField("registration_needs", "registration_needs", "Registration needs"),
)

_BY_COLUMN: dict[str, EditableField] = {field.column: field for field in EDITABLE_FIELDS}

#: US5.2's rule: date/time, attendance, venue and equipment are important.
#:
#: `venue_id` and `equipment` are not columns on `events` yet — they arrive with
#: the booking epic — so no proposal can contain them today. They are listed so
#: the rule is written once, as the story states it, and a proposal that does
#: carry them is flagged without anyone having to remember to come back here.
#: `equipment_needs` (US2.1, Sprint 3) is the equipment an event asks for.
IMPORTANT_FIELDS: frozenset[str] = frozenset(
    {
        "proposed_date",
        "end_date",
        "expected_attendance",
        "venue_id",
        "equipment",
        "equipment_needs",
    }
)


def is_important(column: str) -> bool:
    return column in IMPORTANT_FIELDS


def change_type(change: FieldChange) -> str:
    """The `event_changes.change_type` value US5.2 already writes."""
    return "important" if change.important else "routine"


def label_for(column: str) -> str:
    """The form label for a column, or the column itself for one the form lacks."""
    field = _BY_COLUMN.get(column)
    return field.label if field else column


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _same_instant(old: str, new: str) -> bool:
    """Whether two datetime strings name the same moment.

    The database hands back `2027-03-01T09:00:00` and a datetime-local input
    sends `2027-03-01T09:00`. Comparing the text would report a change the
    Organiser never made and put it in front of a Coordinator as important.
    """
    if not old or not new:
        return old == new
    try:
        return datetime.fromisoformat(old) == datetime.fromisoformat(new)
    except ValueError:
        return old == new


def diff(current: object, proposed: object) -> tuple[FieldChange, ...]:
    """Every editable field whose proposed value differs from the current one.

    Both arguments are read by attribute, so an `Event` and the same `Event`
    with the proposal applied can be compared directly. Text is compared exactly
    — validation must not rewrite what an Organiser wrote, so neither may this.
    """
    changes: list[FieldChange] = []
    for field in EDITABLE_FIELDS:
        old = _as_text(getattr(current, field.attr))
        new = _as_text(getattr(proposed, field.attr))
        unchanged = _same_instant(old, new) if field.kind == "datetime" else old == new
        if not unchanged:
            changes.append(
                FieldChange(
                    field=field.column,
                    old_value=old,
                    new_value=new,
                    important=is_important(field.column),
                )
            )
    return tuple(changes)


def ordered(changes: Iterable[FieldChange]) -> tuple[FieldChange, ...]:
    """A proposal in form order, whatever order storage returned it in."""
    rank = {field.column: index for index, field in enumerate(EDITABLE_FIELDS)}
    return tuple(sorted(changes, key=lambda change: rank.get(change.field, len(rank))))


def applied_values(changes: Iterable[FieldChange]) -> dict[str, Any]:
    """The `Event` attributes an approved proposal sets, typed as `Event` holds them.

    A column the form does not know is skipped rather than guessed at: there is
    no `Event` attribute to put it in.
    """
    values: dict[str, Any] = {}
    for change in changes:
        field = _BY_COLUMN.get(change.field)
        if field is None:
            continue
        if field.kind == "int":
            values[field.attr] = int(change.new_value) if change.new_value else None
        else:
            values[field.attr] = change.new_value
    return values


#: Drafts are edited directly. Approved and Planning events can carry a pending
#: request without moving back to Under Review; closed events cannot.
REQUESTABLE: tuple[EventStatus, ...] = (
    EventStatus.SUBMITTED,
    EventStatus.UNDER_REVIEW,
    EventStatus.APPROVED,
    EventStatus.PLANNING,
)


class ChangeRequestRefusal(StrEnum):
    """Why a change request was refused, so the client can explain rather than deny."""

    NOT_OWNER = "not-owner"
    NOT_SUBMITTED = "not-submitted"
    ALREADY_DECIDED = "already-decided"
    ALREADY_PENDING = "already-pending"


CHANGE_REQUEST_REFUSAL_MESSAGES: dict[ChangeRequestRefusal, str] = {
    ChangeRequestRefusal.NOT_OWNER: (
        "Only the Organiser who owns this event can request changes to it."
    ),
    ChangeRequestRefusal.NOT_SUBMITTED: (
        "This event is still a Draft. Edit it directly, then submit it."
    ),
    ChangeRequestRefusal.ALREADY_DECIDED: (
        "This event has already been decided, so changes can no longer be requested."
    ),
    ChangeRequestRefusal.ALREADY_PENDING: (
        "A change request for this event is already awaiting the Coordinator's review."
    ),
}


def check_change_request(
    *, status: EventStatus, organiser_id: int, actor_id: int, change_requested: bool
) -> ChangeRequestRefusal | None:
    """US11.1: may this actor propose changes to this event now?

    Returns the reason it was refused, or None when it is allowed. Ownership is
    checked first so that someone else's event reads as "not yours" rather than
    describing its state, as US4.2's submit check does.

    One request at a time: a second would leave the Coordinator reviewing two
    proposals against the same values, and approving both would quietly let the
    later one overwrite the earlier.
    """
    if organiser_id != actor_id:
        return ChangeRequestRefusal.NOT_OWNER
    if status is EventStatus.DRAFT:
        return ChangeRequestRefusal.NOT_SUBMITTED
    if status not in REQUESTABLE:
        return ChangeRequestRefusal.ALREADY_DECIDED
    if change_requested:
        return ChangeRequestRefusal.ALREADY_PENDING
    return None


def change_request_refusal_message(reason: ChangeRequestRefusal) -> str:
    return CHANGE_REQUEST_REFUSAL_MESSAGES[reason]


NOTHING_PENDING_MESSAGE = "There is no change request awaiting review on this event."


def has_pending_request(*, status: EventStatus, change_requested: bool) -> bool:
    """Whether a Coordinator has a change request to approve or reject.

    A request preserves its status except when an assigned Submitted event
    moves to Under Review. An unassigned Submitted event awaits Lead assignment.
    """
    return change_requested and status in REQUESTABLE


#: How the history labels the entry a change request wrote.
KIND_CHANGE_REQUEST = "change-request"


def history_kind(*, by_id: int, organiser_id: int, to_status: EventStatus) -> str:
    """What a status-history entry is, worked out rather than stored.

    The Organiser moves their own event to Under Review in exactly one way:
    by requesting a change. Their only other move is Draft -> Submitted, and a
    Coordinator never owns the event. So the entry needs no column to say so.
    """
    if by_id == organiser_id and to_status is EventStatus.UNDER_REVIEW:
        return KIND_CHANGE_REQUEST
    return ""


@dataclass(frozen=True)
class ChangeReview:
    """A Coordinator's answer to the most recent request: approved or rejected.

    Kept on the `event_change_requests` rows it answered, not as a status
    change, because answering a request does not move the event's status.
    """

    outcome: str
    at: str
    #: The rejection reason the Organiser reads. Empty for an approval.
    note: str = ""
    #: The Organiser's note on the request that received this answer.
    request_note: str = ""
