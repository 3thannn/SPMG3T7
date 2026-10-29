"""US19 equipment catalogue and event request routes."""

from datetime import datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app import equipment_store, event_store, users
from app.auth import require_any_permission, require_permission
from app.equipment_store import Equipment, EquipmentRequest, RequestHistory
from app.event_status import EventStatus
from app.event_store import _now
from app.notifications import notify_equipment_change, notify_equipment_request
from app.permissions import Permission, Role
from app.users import User

router = APIRouter(tags=["equipment"])
MAX_QUANTITY = 2_147_483_647  # PostgreSQL INTEGER


def _error(code: str, message: str, http_status: int = 400) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _id(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise _error("not_found", "That item does not exist.", 404) from None
    if value < 1:
        raise _error("not_found", "That item does not exist.", 404)
    return value


class EquipmentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    equipment_type: str = Field(alias="type")
    description: str = ""
    location: str
    total_quantity: StrictInt = Field(alias="totalQuantity")
    out_of_service_quantity: StrictInt = Field(default=0, alias="outOfServiceQuantity")
    out_of_service_reason: str = Field(default="", alias="outOfServiceReason")


class EquipmentOut(EquipmentInput):
    id: str
    usable_quantity: int = Field(serialization_alias="usableQuantity")


def _equipment_out(item: Equipment) -> EquipmentOut:
    return EquipmentOut(
        id=str(item.id),
        name=item.name,
        type=item.equipment_type,
        description=item.description,
        location=item.location,
        totalQuantity=item.total_quantity,
        outOfServiceQuantity=item.out_of_service_quantity,
        outOfServiceReason=item.out_of_service_reason,
        usable_quantity=item.total_quantity - item.out_of_service_quantity,
    )


def _validated_item(data: EquipmentInput, item_id: int = 0) -> Equipment:
    name, kind, location = data.name.strip(), data.equipment_type.strip(), data.location.strip()
    if not name or not kind or not location:
        raise _error("invalid_equipment", "Name, type, and location are required.")
    if len(name) > 255 or len(kind) > 100:
        raise _error("invalid_equipment", "Name or type is too long.")
    total, out = data.total_quantity, data.out_of_service_quantity
    if total < 0 or total > MAX_QUANTITY:
        raise _error("invalid_equipment", "Total quantity must be between zero and 2,147,483,647.")
    if out < 0 or out > total:
        raise _error(
            "invalid_equipment", "Out-of-service units must be between zero and total quantity."
        )
    reason = data.out_of_service_reason.strip()
    if out and not reason:
        raise _error("invalid_equipment", "Give a reason for out-of-service units.")
    return Equipment(
        item_id, name, kind, data.description.strip(), location, total, out, reason if out else ""
    )


CatalogueReader = Annotated[User, Depends(require_any_permission(Permission.EQUIPMENT_READ))]
CatalogueWriter = Annotated[User, Depends(require_permission(Permission.EQUIPMENT_WRITE))]


@router.get("/equipment", response_model=list[EquipmentOut])
def list_equipment(_user: CatalogueReader) -> list[EquipmentOut]:
    return [_equipment_out(item) for item in equipment_store.repository().list_items()]


@router.get("/equipment/{item_id}", response_model=EquipmentOut)
def get_equipment(item_id: str, _user: CatalogueReader) -> EquipmentOut:
    item = equipment_store.repository().get_item(_id(item_id))
    if item is None:
        raise _error("equipment_not_found", "That equipment item does not exist.", 404)
    return _equipment_out(item)


@router.post("/equipment", response_model=EquipmentOut, status_code=201)
def create_equipment(payload: EquipmentInput, _user: CatalogueWriter) -> EquipmentOut:
    return _equipment_out(equipment_store.repository().save_item(_validated_item(payload)))


def _guard_last_type(item: Equipment) -> None:
    repo = equipment_store.repository()
    has_another = any(
        other.id != item.id and other.equipment_type.casefold() == item.equipment_type.casefold()
        for other in repo.list_items()
    )
    if not has_another and any(
        request.requested_equipment_id is None
        and request.equipment_type.casefold() == item.equipment_type.casefold()
        for request in repo.list_requested()
    ):
        raise _error(
            "equipment_in_use",
            "Active equipment requests still need this type. "
            "Remove or change those requests first.",
            409,
        )


@router.put("/equipment/{item_id}", response_model=EquipmentOut)
def update_equipment(item_id: str, payload: EquipmentInput, _user: CatalogueWriter) -> EquipmentOut:
    numeric_id = _id(item_id)
    current = equipment_store.repository().get_item(numeric_id)
    if current is None:
        raise _error("equipment_not_found", "That equipment item does not exist.", 404)
    changed = _validated_item(payload, numeric_id)
    if current.equipment_type.casefold() != changed.equipment_type.casefold():
        _guard_last_type(current)
    try:
        return _equipment_out(equipment_store.repository().save_item(changed))
    except APIError as error:
        if error.code == "P0001" and "Equipment has active reservations" in error.message:
            raise _error(
                "equipment_in_use", "This change would affect active reservations.", 409
            ) from error
        raise


@router.delete("/equipment/{item_id}", status_code=204)
def delete_equipment(item_id: str, _user: CatalogueWriter) -> Response:
    numeric_id = _id(item_id)
    current = equipment_store.repository().get_item(numeric_id)
    if current is None:
        raise _error("equipment_not_found", "That equipment item does not exist.", 404)
    _guard_last_type(current)
    try:
        equipment_store.repository().delete_item(numeric_id)
    except APIError as error:
        if error.code == "23503":
            raise _error(
                "equipment_in_use", "This item is linked to equipment reservation history.", 409
            ) from error
        if error.code == "P0001" and "Equipment has active reservations" in error.message:
            raise _error("equipment_in_use", "This item has active reservations.", 409) from error
        raise
    return Response(status_code=204)


class RequestInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    equipment_id: StrictInt = Field(alias="equipmentId", ge=1)
    equipment_type: str | None = Field(default=None, alias="equipmentType")
    quantity: StrictInt
    technical_requirements: str = Field(default="", alias="technicalRequirements")
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")


class RequestUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: StrictInt
    equipment_id: StrictInt | None = Field(default=None, alias="equipmentId", ge=1)
    equipment_type: str | None = Field(default=None, alias="equipmentType")
    quantity: StrictInt | None = None
    technical_requirements: str | None = Field(default=None, alias="technicalRequirements")
    support_notes: str | None = Field(default=None, alias="supportNotes")
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")


class RequestOut(BaseModel):
    id: str
    event_id: str = Field(serialization_alias="eventId")
    event_title: str = Field(serialization_alias="eventTitle")
    equipment_type: str = Field(serialization_alias="equipmentType")
    quantity: int
    technical_requirements: str = Field(serialization_alias="technicalRequirements")
    support_notes: str = Field(serialization_alias="supportNotes")
    starts_at: str = Field(serialization_alias="startsAt")
    ends_at: str = Field(serialization_alias="endsAt")
    status: str
    created_at: str = Field(serialization_alias="createdAt")
    version: int
    equipment_id: str | None = Field(default=None, serialization_alias="equipmentId")
    unavailable_reason: str = Field(default="", serialization_alias="unavailableReason")
    requested_equipment_id: str | None = Field(
        default=None, serialization_alias="requestedEquipmentId"
    )
    equipment_name: str = Field(default="", serialization_alias="equipmentName")


class RequestDetailOut(RequestOut):
    removed_by_name: str = Field(default="", serialization_alias="removedByName")


class RequestHistoryOut(BaseModel):
    id: str
    request_id: str = Field(serialization_alias="requestId")
    action: str
    at: str
    by_name: str = Field(serialization_alias="byName")
    before: dict | None
    after: dict | None


def _history_out(entry: RequestHistory, names: dict[int, str]) -> RequestHistoryOut:
    return RequestHistoryOut(
        id=str(entry.id),
        request_id=str(entry.request_id),
        action=entry.action,
        at=entry.at,
        by_name=names.get(entry.actor_id, "Former user"),
        before=entry.before,
        after=entry.after,
    )


def _request_out(request: EquipmentRequest) -> RequestOut:
    return RequestOut(
        id=str(request.id),
        event_id=str(request.event_id),
        event_title=request.event_title,
        equipment_type=request.equipment_type,
        quantity=request.quantity,
        technical_requirements=request.technical_requirements,
        support_notes=request.support_notes,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        status=request.status,
        created_at=request.created_at,
        version=request.version,
        equipment_id=str(request.equipment_id) if request.equipment_id is not None else None,
        unavailable_reason=request.unavailable_reason,
        requested_equipment_id=str(request.requested_equipment_id)
        if request.requested_equipment_id is not None
        else None,
        equipment_name=request.equipment_name,
    )


def _assigned_event(event_id: int, user: User):
    event = event_store.repository().get_event(event_id)
    if event is None or event.coordinator_id != user.id:
        raise _error("event_not_found", "That event does not exist.", 404)
    return event


def _planning(event) -> None:
    if event.status is not EventStatus.PLANNING:
        raise _error(
            "rule_refused", "Equipment requests can only change while the event is Planning.", 409
        )


def _request_write_error(error: APIError) -> NoReturn:
    if error.code == "P0001" and "Equipment requests can only change while" in error.message:
        raise _error(
            "rule_refused", "Equipment requests can only change while the event is Planning.", 409
        ) from error
    raise error


def _type(raw: str) -> str:
    requested = raw.strip()
    for item in equipment_store.repository().list_items():
        if item.equipment_type.casefold() == requested.casefold():
            return item.equipment_type
    raise _error("invalid_equipment_type", "Choose a type from the equipment catalogue.")


def _requested_item(item_id: int, supplied_type: str | None = None) -> Equipment:
    item = equipment_store.repository().get_item(item_id)
    if item is None:
        raise _error("invalid_equipment", "Choose an item from the equipment catalogue.")
    if (
        supplied_type is not None
        and supplied_type.strip().casefold() != item.equipment_type.casefold()
    ):
        raise _error(
            "invalid_equipment_type", "The selected item does not match that equipment type."
        )
    return item


def _times(start_raw: str, end_raw: str) -> tuple[str, str]:
    try:
        start, end = datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw)
    except ValueError:
        raise _error("invalid_time", "Enter valid start and end times.") from None
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        raise _error("invalid_time", "The needed end time must be after the start time.")
    return start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")


def _quantity(value: int) -> int:
    if value < 1 or value > MAX_QUANTITY:
        raise _error("invalid_quantity", "Quantity must be between one and 2,147,483,647.")
    return value


Coordinator = Annotated[User, Depends(require_permission(Permission.EQUIPMENT_REQUEST))]
Support = Annotated[User, Depends(require_permission(Permission.EQUIPMENT_QUEUE))]
Editor = Annotated[
    User, Depends(require_any_permission(Permission.EQUIPMENT_REQUEST, Permission.EQUIPMENT_QUEUE))
]


@router.get("/events/{event_id}/equipment-requests", response_model=list[RequestOut])
def list_event_requests(
    event_id: str,
    user: Annotated[
        User,
        Depends(
            require_any_permission(
                Permission.EVENTS_READ_OWN,
                Permission.EVENTS_READ_SUBMITTED,
                Permission.EVENTS_READ_ALL,
            )
        ),
    ],
    include_removed: bool = Query(default=False, alias="includeRemoved"),
) -> list[RequestOut]:
    event = event_store.repository().get_event(_id(event_id))
    if event is None or not (
        (user.role is Role.ORGANISER and event.organiser_id == user.id)
        or (
            event.status is not EventStatus.DRAFT
            and (
                (user.role is Role.COORDINATOR and event.coordinator_id == user.id)
                or user.role is Role.COORDINATOR_LEAD
            )
        )
    ):
        raise _error("event_not_found", "That event does not exist.", 404)
    return [
        _request_out(r)
        for r in equipment_store.repository().list_for_event(
            event.id, include_removed=include_removed
        )
    ]


@router.get("/events/{event_id}/equipment-history", response_model=list[RequestHistoryOut])
def list_event_equipment_history(
    event_id: str,
    user: Annotated[
        User,
        Depends(require_any_permission(Permission.EVENTS_READ_OWN, Permission.EQUIPMENT_REQUEST)),
    ],
) -> list[RequestHistoryOut]:
    event = event_store.repository().get_event(_id(event_id))
    if event is None or not (
        (user.role is Role.ORGANISER and event.organiser_id == user.id)
        or (
            user.role is Role.COORDINATOR
            and event.coordinator_id == user.id
            and event.status is not EventStatus.DRAFT
        )
    ):
        raise _error("event_not_found", "That event does not exist.", 404)
    entries = equipment_store.repository().list_history(event.id)
    names = {person.id: person.name for person in users.list_users()}
    return [_history_out(entry, names) for entry in entries]


@router.post("/events/{event_id}/equipment-requests", response_model=RequestOut, status_code=201)
def create_request(event_id: str, payload: RequestInput, user: Coordinator) -> RequestOut:
    event = _assigned_event(_id(event_id), user)
    _planning(event)
    item = _requested_item(payload.equipment_id, payload.equipment_type)
    end_raw = payload.ends_at or event.ends_at
    if not end_raw or not end_raw.strip():
        raise _error("invalid_time", "Enter a needed end time for this equipment request.")
    starts_at, ends_at = _times(payload.starts_at or event.starts_at, end_raw)
    request = EquipmentRequest(
        0,
        event.id,
        item.equipment_type,
        _quantity(payload.quantity),
        payload.technical_requirements.strip(),
        "",
        starts_at,
        ends_at,
        "Requested",
        user.id,
        _now(),
        1,
        event.title,
        requested_equipment_id=item.id,
        equipment_name=item.name,
    )
    try:
        created = equipment_store.repository().create_request(request)
    except APIError as error:
        _request_write_error(error)
    notify_equipment_request(event, created)
    return _request_out(created)


@router.get("/equipment-requests", response_model=list[RequestOut])
def list_queue(_user: Support) -> list[RequestOut]:
    return [_request_out(r) for r in equipment_store.repository().list_requested()]


@router.get("/equipment-requests/{request_id}", response_model=RequestDetailOut)
def get_request_detail(request_id: str, _user: Support) -> RequestDetailOut:
    request = equipment_store.repository().get_request(_id(request_id))
    if request is None:
        raise _error("request_not_found", "That equipment request does not exist.", 404)
    removed_by_name = ""
    if request.status == "Removed":
        actor = users.get_by_id(request.updated_by_id) if request.updated_by_id else None
        removed_by_name = actor.name if actor else "A former Coordinator"
    return RequestDetailOut(
        **_request_out(request).model_dump(),
        removed_by_name=removed_by_name,
    )


class ReserveInput(BaseModel):
    version: StrictInt = Field(ge=1)
    equipment_id: StrictInt = Field(alias="equipmentId", ge=1)


class UnavailableInput(BaseModel):
    version: StrictInt = Field(ge=1)
    reason: str


@router.get("/equipment-requests/{request_id}/availability")
def request_availability(request_id: str, _user: Support) -> list[dict]:
    numeric_id = _id(request_id)
    if equipment_store.repository().get_request(numeric_id) is None:
        raise _error("request_not_found", "That equipment request does not exist.", 404)
    return equipment_store.repository().availability(numeric_id)


def _decide(
    request_id: str, version: int, user: User, item_id: int | None = None, reason: str = ""
) -> RequestOut:
    repo = equipment_store.repository()
    try:
        result = repo.decide(_id(request_id), version, user.id, item_id, reason)
    except APIError as error:
        if error.code == "23514" and "notifications_kind_valid" in error.message:
            raise _error(
                "equipment_configuration_error",
                "Equipment notifications are not configured correctly. "
                "Please contact your administrator and try again.",
                503,
            ) from error
        raise
    code = result["code"]
    if code != "ok":
        messages = {
            "request_not_found": "That equipment request does not exist.",
            "stale_request": "This request changed. Reload it before deciding.",
            "rule_refused": "Equipment decisions are only allowed while the event is Planning.",
            "invalid_equipment": (
                "Reserve the item selected by the Coordinator. "
                "If no item was selected, ask the Coordinator to revise the request."
            ),
            "invalid_reason": "Give a reason for marking this request Unavailable.",
            "forbidden": "Only Technical Support can decide equipment requests.",
        }
        message = messages.get(code, "The equipment decision could not be saved.")
        if code == "insufficient_stock":
            message = (
                f"Only {result['availableQuantity']} available. Shortfall: {result['shortfall']}."
            )
        raise HTTPException(
            status_code=404
            if code == "request_not_found"
            else 403
            if code == "forbidden"
            else 400
            if code in ("invalid_equipment", "invalid_reason")
            else 409,
            detail={**result, "message": message},
        )
    updated = repo.get_request(_id(request_id))
    assert updated is not None
    return _request_out(updated)


@router.post("/equipment-requests/{request_id}/reserve", response_model=RequestOut)
def reserve_request(request_id: str, payload: ReserveInput, user: Support) -> RequestOut:
    return _decide(request_id, payload.version, user, payload.equipment_id)


@router.post("/equipment-requests/{request_id}/unavailable", response_model=RequestOut)
def unavailable_request(request_id: str, payload: UnavailableInput, user: Support) -> RequestOut:
    return _decide(request_id, payload.version, user, reason=payload.reason)


def _editable(request_id: str, user: User) -> EquipmentRequest:
    request = equipment_store.repository().get_request(_id(request_id))
    if request is None:
        raise _error("request_not_found", "That equipment request does not exist.", 404)
    if user.role is Role.COORDINATOR:
        _assigned_event(request.event_id, user)
    event = event_store.repository().get_event(request.event_id)
    if event is None:
        raise _error("request_not_found", "That equipment request does not exist.", 404)
    _planning(event)
    recoverable = user.role is Role.COORDINATOR and request.status == "Unavailable"
    if request.status != "Requested" and not recoverable:
        raise _error("rule_refused", "Only Requested lines can be changed.", 409)
    return request


@router.patch("/equipment-requests/{request_id}", response_model=RequestOut)
def update_request(request_id: str, payload: RequestUpdate, user: Editor) -> RequestOut:
    current = _editable(request_id, user)
    if current.version != payload.version:
        raise _error("stale_request", "This request changed. Reload it before editing.", 409)
    is_support = user.role is Role.TECH_SUPPORT
    if is_support and (
        payload.equipment_type is not None
        or payload.technical_requirements is not None
        or payload.equipment_id is not None
    ):
        raise _error(
            "forbidden_fields",
            "Tech Support cannot change the requested type or Coordinator requirements.",
            403,
        )
    if not is_support and payload.support_notes is not None:
        raise _error("forbidden_fields", "Only Tech Support can change arrangement notes.", 403)
    item = None
    if not is_support:
        selected_id = payload.equipment_id or current.requested_equipment_id
        if selected_id is None:
            raise _error(
                "invalid_equipment", "Choose a catalogue item before resubmitting this request."
            )
        item = _requested_item(selected_id, payload.equipment_type)
    starts_at, ends_at = _times(
        payload.starts_at or current.starts_at, payload.ends_at or current.ends_at
    )
    changed = EquipmentRequest(
        current.id,
        current.event_id,
        item.equipment_type if item else current.equipment_type,
        _quantity(current.quantity if payload.quantity is None else payload.quantity),
        current.technical_requirements
        if is_support or payload.technical_requirements is None
        else payload.technical_requirements.strip(),
        current.support_notes
        if not is_support or payload.support_notes is None
        else payload.support_notes.strip(),
        starts_at,
        ends_at,
        "Requested",
        current.requested_by_id,
        current.created_at,
        current.version,
        current.event_title,
        user.id,
        requested_equipment_id=item.id if item else current.requested_equipment_id,
        equipment_name=item.name if item else current.equipment_name,
    )
    try:
        updated = equipment_store.repository().update_request(changed, payload.version)
    except APIError as error:
        _request_write_error(error)
    if updated is None:
        raise _error("stale_request", "This request changed. Reload it before editing.", 409)
    if user.role is Role.COORDINATOR and any(
        getattr(current, field) != getattr(updated, field)
        for field in (
            "equipment_type",
            "quantity",
            "technical_requirements",
            "starts_at",
            "ends_at",
            "status",
            "requested_equipment_id",
        )
    ):
        notify_equipment_change(
            updated, user.name, "resubmitted" if current.status == "Unavailable" else "updated"
        )
    return _request_out(updated)


@router.delete("/equipment-requests/{request_id}", status_code=204)
def delete_request(request_id: str, version: int, user: Coordinator) -> Response:
    current = _editable(request_id, user)
    try:
        removed = equipment_store.repository().delete_request(current.id, version, user.id)
    except APIError as error:
        _request_write_error(error)
    if not removed:
        raise _error("stale_request", "This request changed. Reload it before removing it.", 409)
    notify_equipment_change(current, user.name, "removed")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
