"""The event request route — Event Request Creation.

One endpoint, `POST /event-requests`: an Event Organiser fills in a complete
proposal and it is submitted in a single step. It sits beside the US4.2 draft
flow rather than replacing it, because the two answer different needs — a draft
is for a proposal still being worked out, a request is for one that is finished.
Nothing in `events.py` changes behaviour as a result.

Every field arrives as plain text. There are no Venue or Equipment catalogue
lookups: those arrive in Sprint 2 and 3, and inventing a shape for them now
would be guessing at an interface nobody has agreed.

`EventOut` and `_to_out` are borrowed from `events` rather than copied: a
request is written to the same table and must come back in the same shape, so
a second mapper here would be a second thing to keep in step with the first.

The rules live in `event_request_rules`, not here. This module's whole job is
the two things a route should do: check that the caller may create an event at
all, and turn a rule's refusal into an HTTP answer the form can render.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app import event_request_rules, event_store
from app.auth import require_permission
from app.events import EventOut, _to_out
from app.permissions import Permission
from app.users import User

router = APIRouter(prefix="/event-requests", tags=["event requests"])


class EventRequestError:
    INVALID = "invalid_event_request"


class EventRequestIn(BaseModel):
    """The submitted form, before any rule has looked at it.

    Every field has a default and the text ones are typed `str`, so a field the
    client left out arrives as empty rather than as a Pydantic 422. That is
    deliberate: a missing name and a blank name are the same mistake to the
    person filling the form in, and they should get the same sentence back.

    `expected_attendance` is `Any` for the same reason — `"twenty"`, `12.5` and
    `true` are all things a hand-written client can send, and each should come
    back as "must be a whole number" rather than as a validation dump.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    purpose: str = ""
    description: str = ""
    proposed_date: str = Field(default="", alias="proposedDate")
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")
    expected_attendance: Any = Field(default=None, alias="expectedAttendance")


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event_request(
    submitted: EventRequestIn,
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_CREATE))],
) -> EventOut:
    """A complete request, written to `events` and already Submitted.

    The organiser is taken from the session and never from the body, for the
    reason `events.create_event` gives: a client that could name the organiser
    could file an event under someone else's name.
    """
    try:
        request = event_request_rules.validated(
            name=submitted.name,
            purpose=submitted.purpose,
            description=submitted.description,
            proposed_date=submitted.proposed_date,
            start_time=submitted.start_time,
            end_time=submitted.end_time,
            expected_attendance=submitted.expected_attendance,
        )
    except event_request_rules.InvalidField as refusal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": EventRequestError.INVALID,
                "message": refusal.message,
                "field": refusal.field,
            },
        ) from None

    created = event_store.repository().create_event_request(
        name=request.name,
        purpose=request.purpose,
        description=request.description,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        expected_attendance=request.expected_attendance,
        organiser_id=user.id,
    )
    return _to_out(created)
