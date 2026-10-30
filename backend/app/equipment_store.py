"""Equipment catalogue and Requested lines, with Supabase and test repositories."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from threading import RLock
from typing import Protocol

from app import supabase_client
from app.event_store import _now

#: The line status US19.3 sets when Technical Support reserve stock for an event.
RESERVED = "Reserved"


@dataclass(frozen=True)
class Equipment:
    id: int
    name: str
    equipment_type: str
    description: str
    location: str
    total_quantity: int
    out_of_service_quantity: int
    out_of_service_reason: str


@dataclass(frozen=True)
class EquipmentRequest:
    id: int
    event_id: int
    equipment_type: str
    quantity: int
    technical_requirements: str
    support_notes: str
    starts_at: str
    ends_at: str
    status: str
    requested_by_id: int | None
    created_at: str
    version: int
    event_title: str = ""
    updated_by_id: int | None = None
    equipment_id: int | None = None
    unavailable_reason: str = ""
    requested_equipment_id: int | None = None
    equipment_name: str = ""
    event_conflict_reason: str = ""
    event_conflict_at: str = ""


@dataclass(frozen=True)
class RequestHistory:
    id: int
    request_id: int
    event_id: int
    actor_id: int | None
    action: str
    at: str
    before: dict | None
    after: dict | None


def _snapshot(request: EquipmentRequest) -> dict:
    return {
        "equipment_type": request.equipment_type,
        "quantity": request.quantity,
        "technical_requirements": request.technical_requirements,
        "support_notes": request.support_notes,
        "start_at": request.starts_at,
        "end_at": request.ends_at,
        "status": request.status,
        "equipment_id": request.equipment_id,
        "unavailable_reason": request.unavailable_reason,
        "requested_equipment_id": request.requested_equipment_id,
        "equipment_name": request.equipment_name,
    }


def _item(row: dict) -> Equipment:
    return Equipment(
        id=row["id"],
        name=row["name"],
        equipment_type=row["equipment_type"],
        description=row.get("description") or "",
        location=row.get("location") or "",
        total_quantity=row["total_quantity"],
        out_of_service_quantity=row["out_of_service_quantity"],
        out_of_service_reason=row.get("out_of_service_reason") or "",
    )


def _request(row: dict) -> EquipmentRequest:
    event = row.get("events") or {}
    return EquipmentRequest(
        id=row["id"],
        event_id=row["event_id"],
        equipment_type=row["equipment_type"],
        quantity=row["quantity"],
        technical_requirements=row.get("technical_requirements") or "",
        support_notes=row.get("support_notes") or "",
        starts_at=str(row["start_at"]),
        ends_at=str(row["end_at"]),
        status=row["status"],
        requested_by_id=row.get("requested_by_id"),
        created_at=str(row["created_at"]),
        version=row["version"],
        event_title=event.get("name", "") if isinstance(event, dict) else "",
        updated_by_id=row.get("updated_by_id"),
        equipment_id=row.get("equipment_id"),
        unavailable_reason=row.get("unavailable_reason") or "",
        requested_equipment_id=row.get("requested_equipment_id"),
        equipment_name=(row.get("requested_equipment") or {}).get("name", ""),
        event_conflict_reason=row.get("event_conflict_reason") or "",
        event_conflict_at=str(row["event_conflict_at"]) if row.get("event_conflict_at") else "",
    )


class Repository(Protocol):
    def set_event_conflict(self, request_id: int, reason: str) -> None: ...

    def list_items(self) -> list[Equipment]: ...
    def get_item(self, item_id: int) -> Equipment | None: ...
    def save_item(self, item: Equipment) -> Equipment: ...
    def delete_item(self, item_id: int) -> None: ...
    def list_for_event(
        self, event_id: int, *, include_removed: bool = False
    ) -> list[EquipmentRequest]: ...
    def list_reserved_for_event(self, event_id: int) -> list[EquipmentRequest]: ...
    def list_requested(self) -> list[EquipmentRequest]: ...
    def get_request(self, request_id: int) -> EquipmentRequest | None: ...
    def create_request(self, request: EquipmentRequest) -> EquipmentRequest: ...
    def update_request(
        self, request: EquipmentRequest, expected_version: int
    ) -> EquipmentRequest | None: ...
    def delete_request(self, request_id: int, expected_version: int, actor_id: int) -> bool: ...
    def list_history(self, event_id: int) -> list[RequestHistory]: ...
    def availability(self, request_id: int) -> list[dict]: ...
    def decide(
        self, request_id: int, version: int, actor_id: int, item_id: int | None, reason: str
    ) -> dict: ...


class SupabaseEquipment:
    item_columns = (
        "id, name, equipment_type, description, location, total_quantity, "
        "out_of_service_quantity, out_of_service_reason"
    )
    request_columns = (
        "id, event_id, equipment_type, quantity, technical_requirements, "
        "support_notes, start_at, end_at, status, requested_by_id, "
        "created_at, version, updated_by_id, equipment_id, unavailable_reason, "
        "event_conflict_reason, event_conflict_at, "
        "requested_equipment_id, requested_equipment:equipment!requested_equipment_id(name), "
        "events(name)"
    )

    def set_event_conflict(self, request_id: int, reason: str) -> None:
        supabase_client.admin().table("equipment_requests").update(
            {
                "event_conflict_reason": reason,
                "event_conflict_at": _now() if reason else None,
            }
        ).eq("id", request_id).execute()

    def list_items(self) -> list[Equipment]:
        rows = (
            supabase_client.admin()
            .table("equipment")
            .select(self.item_columns)
            .order("name")
            .execute()
            .data
            or []
        )
        return [_item(row) for row in rows]

    def get_item(self, item_id: int) -> Equipment | None:
        rows = (
            supabase_client.admin()
            .table("equipment")
            .select(self.item_columns)
            .eq("id", item_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _item(rows[0]) if rows else None

    def save_item(self, item: Equipment) -> Equipment:
        data = {
            "name": item.name,
            "equipment_type": item.equipment_type,
            "description": item.description,
            "location": item.location,
            "total_quantity": item.total_quantity,
            "out_of_service_quantity": item.out_of_service_quantity,
            "out_of_service_reason": item.out_of_service_reason,
            "updated_at": _now(),
        }
        query = supabase_client.admin().table("equipment")
        if item.id:
            rows = query.update(data).eq("id", item.id).execute().data or []
        else:
            rows = query.insert(data).execute().data or []
        if not rows:
            raise RuntimeError("Equipment save returned no row")
        saved = self.get_item(rows[0]["id"])
        assert saved is not None
        return saved

    def delete_item(self, item_id: int) -> None:
        supabase_client.admin().table("equipment").delete().eq("id", item_id).execute()

    def list_for_event(
        self, event_id: int, *, include_removed: bool = False
    ) -> list[EquipmentRequest]:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .select(self.request_columns)
            .eq("event_id", event_id)
            .in_(
                "status",
                ["Requested", "Reserved", "Unavailable"] + (["Removed"] if include_removed else []),
            )
            .order("created_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [_request(row) for row in rows]

    def list_reserved_for_event(self, event_id: int) -> list[EquipmentRequest]:
        """US17.1: what the Safety Officer reviews. US19.3 sets `Reserved`."""
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .select(self.request_columns)
            .eq("event_id", event_id)
            .eq("status", RESERVED)
            .order("created_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [_request(row) for row in rows]

    def list_requested(self) -> list[EquipmentRequest]:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .select(self.request_columns)
            .eq("status", "Requested")
            .order("created_at")
            .order("id")
            .execute()
            .data
            or []
        )
        return [_request(row) for row in rows]

    def get_request(self, request_id: int) -> EquipmentRequest | None:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .select(self.request_columns)
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _request(rows[0]) if rows else None

    def create_request(self, request: EquipmentRequest) -> EquipmentRequest:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .insert(
                {
                    "event_id": request.event_id,
                    "equipment_type": request.equipment_type,
                    "quantity": request.quantity,
                    "technical_requirements": request.technical_requirements,
                    "support_notes": request.support_notes,
                    "start_at": request.starts_at,
                    "end_at": request.ends_at,
                    "requested_by_id": request.requested_by_id,
                    "updated_by_id": request.requested_by_id,
                    "requested_equipment_id": request.requested_equipment_id,
                }
            )
            .execute()
            .data
            or []
        )
        if not rows:
            raise RuntimeError("Equipment request insert returned no row")
        created = self.get_request(rows[0]["id"])
        assert created is not None
        return created

    def update_request(
        self, request: EquipmentRequest, expected_version: int
    ) -> EquipmentRequest | None:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .update(
                {
                    "equipment_type": request.equipment_type,
                    "quantity": request.quantity,
                    "technical_requirements": request.technical_requirements,
                    "support_notes": request.support_notes,
                    "start_at": request.starts_at,
                    "end_at": request.ends_at,
                    "version": expected_version + 1,
                    "updated_at": _now(),
                    "updated_by_id": request.updated_by_id,
                    "status": "Requested",
                    "equipment_id": None,
                    "unavailable_reason": "",
                    "requested_equipment_id": request.requested_equipment_id,
                }
            )
            .eq("id", request.id)
            .eq("version", expected_version)
            .in_("status", ["Requested", "Unavailable"])
            .execute()
            .data
            or []
        )
        return self.get_request(request.id) if rows else None

    def delete_request(self, request_id: int, expected_version: int, actor_id: int) -> bool:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .update(
                {
                    "status": "Removed",
                    "version": expected_version + 1,
                    "updated_at": _now(),
                    "updated_by_id": actor_id,
                }
            )
            .eq("id", request_id)
            .eq("version", expected_version)
            .in_("status", ["Requested", "Unavailable"])
            .execute()
            .data
            or []
        )
        return bool(rows)

    def list_history(self, event_id: int) -> list[RequestHistory]:
        rows = (
            supabase_client.admin()
            .table("equipment_request_history")
            .select(
                "id, request_id, event_id, actor_id, action, changed_at, before_data, after_data"
            )
            .eq("event_id", event_id)
            .order("changed_at", desc=True)
            .order("id", desc=True)
            .execute()
            .data
            or []
        )
        return [
            RequestHistory(
                row["id"],
                row["request_id"],
                row["event_id"],
                row.get("actor_id"),
                row["action"],
                str(row["changed_at"]),
                row.get("before_data"),
                row.get("after_data"),
            )
            for row in rows
        ]

    def availability(self, request_id: int) -> list[dict]:
        return (
            supabase_client.admin()
            .rpc("equipment_availability", {"p_request_id": request_id})
            .execute()
            .data
            or []
        )

    def decide(
        self, request_id: int, version: int, actor_id: int, item_id: int | None, reason: str
    ) -> dict:
        return (
            supabase_client.admin()
            .rpc(
                "decide_equipment_request",
                {
                    "p_request_id": request_id,
                    "p_version": version,
                    "p_actor_id": actor_id,
                    "p_equipment_id": item_id,
                    "p_reason": reason,
                },
            )
            .execute()
            .data
        )


@dataclass
class InMemoryEquipment:
    items: list[Equipment] = field(default_factory=list)
    requests: list[EquipmentRequest] = field(default_factory=list)
    history: list[RequestHistory] = field(default_factory=list)
    next_item_id: int = 1
    next_request_id: int = 1
    lock: RLock = field(default_factory=RLock, repr=False)

    def set_event_conflict(self, request_id: int, reason: str) -> None:
        self.requests = [
            replace(row, event_conflict_reason=reason, event_conflict_at=_now() if reason else "")
            if row.id == request_id
            else row
            for row in self.requests
        ]

    def _record(
        self, request: EquipmentRequest, action: str, before: EquipmentRequest | None = None
    ) -> None:
        self.history.append(
            RequestHistory(
                len(self.history) + 1,
                request.id,
                request.event_id,
                request.updated_by_id,
                action,
                _now(),
                _snapshot(before) if before else None,
                _snapshot(request) if action != "Removed" else None,
            )
        )

    def list_items(self) -> list[Equipment]:
        return sorted(self.items, key=lambda item: (item.name.lower(), item.id))

    def get_item(self, item_id: int) -> Equipment | None:
        return next((item for item in self.items if item.id == item_id), None)

    def save_item(self, item: Equipment) -> Equipment:
        self._guard_stock(item.id, item)
        if not item.id:
            item = replace(item, id=self.next_item_id)
            self.next_item_id += 1
        self.items = [old for old in self.items if old.id != item.id] + [item]
        return item

    def delete_item(self, item_id: int) -> None:
        self._guard_stock(item_id)
        if any(
            r.equipment_id == item_id or r.requested_equipment_id == item_id for r in self.requests
        ):
            from postgrest.exceptions import APIError

            raise APIError({"code": "23503", "message": "Item is linked to reservation history"})
        self.items = [item for item in self.items if item.id != item_id]

    def _guard_stock(self, item_id: int, changed: Equipment | None = None) -> None:
        from postgrest.exceptions import APIError

        reserved = [r for r in self.requests if r.equipment_id == item_id and r.status == RESERVED]
        current = self.get_item(item_id)
        if (
            changed
            and current
            and changed.equipment_type != current.equipment_type
            and any(
                r.requested_equipment_id == item_id and r.status in ("Requested", "Unavailable")
                for r in self.requests
            )
        ):
            raise APIError({"code": "P0001", "message": "Equipment has active reservations"})
        if not reserved or current is None:
            return
        points: dict[datetime, int] = {}
        for r in reserved:
            for at, delta in ((r.starts_at, r.quantity), (r.ends_at, -r.quantity)):
                key = datetime.fromisoformat(at)
                points[key] = points.get(key, 0) + delta
        demand = peak = 0
        for at in sorted(points):
            demand += points[at]
            peak = max(peak, demand)
        if (
            changed is None
            or changed.equipment_type != current.equipment_type
            or (changed.total_quantity - changed.out_of_service_quantity < peak)
        ):
            raise APIError({"code": "P0001", "message": "Equipment has active reservations"})

    def list_for_event(
        self, event_id: int, *, include_removed: bool = False
    ) -> list[EquipmentRequest]:
        return sorted(
            (
                r
                for r in self.requests
                if r.event_id == event_id and (include_removed or r.status != "Removed")
            ),
            key=lambda r: (r.created_at, r.id),
        )

    def list_reserved_for_event(self, event_id: int) -> list[EquipmentRequest]:
        return sorted(
            (r for r in self.requests if r.event_id == event_id and r.status == RESERVED),
            key=lambda r: (r.created_at, r.id),
        )

    def list_requested(self) -> list[EquipmentRequest]:
        return sorted(
            (r for r in self.requests if r.status == "Requested"),
            key=lambda r: (r.created_at, r.id),
        )

    def get_request(self, request_id: int) -> EquipmentRequest | None:
        return next((r for r in self.requests if r.id == request_id), None)

    def create_request(self, request: EquipmentRequest) -> EquipmentRequest:
        request = replace(request, id=self.next_request_id, updated_by_id=request.requested_by_id)
        self.next_request_id += 1
        self.requests.append(request)
        self._record(request, "Created")
        return request

    def update_request(
        self, request: EquipmentRequest, expected_version: int
    ) -> EquipmentRequest | None:
        current = self.get_request(request.id)
        if (
            current is None
            or current.version != expected_version
            or current.status not in ("Requested", "Unavailable")
        ):
            return None
        updated = replace(
            request,
            version=expected_version + 1,
            status="Requested",
            equipment_id=None,
            unavailable_reason="",
        )
        self.requests = [updated if r.id == request.id else r for r in self.requests]
        self._record(updated, "Updated", current)
        return updated

    def delete_request(self, request_id: int, expected_version: int, actor_id: int) -> bool:
        current = self.get_request(request_id)
        if (
            current is None
            or current.version != expected_version
            or current.status not in ("Requested", "Unavailable")
        ):
            return False
        removed = replace(
            current, status="Removed", version=expected_version + 1, updated_by_id=actor_id
        )
        self.requests = [removed if r.id == request_id else r for r in self.requests]
        self._record(removed, "Removed", current)
        return True

    def release_for_event(self, event_id: int, *, actor_id: int) -> tuple[int, ...]:
        """US4.6: the `cancel_event` RPC's equipment update, for `InMemoryEvents`.

        Every line of the event not already Removed is Removed, whatever its
        status, so the quantities it asked for are free again.
        """
        released: list[int] = []
        for current in sorted(self.requests, key=lambda r: r.id):
            if current.event_id != event_id or current.status == "Removed":
                continue
            removed = replace(
                current, status="Removed", version=current.version + 1, updated_by_id=actor_id
            )
            self.requests = [removed if r.id == current.id else r for r in self.requests]
            self._record(removed, "Removed", current)
            released.append(current.id)
        return tuple(released)

    def list_history(self, event_id: int) -> list[RequestHistory]:
        return sorted(
            (h for h in self.history if h.event_id == event_id),
            key=lambda h: (h.at, h.id),
            reverse=True,
        )

    def availability(self, request_id: int) -> list[dict]:
        request = self.get_request(request_id)
        if request is None:
            return []
        result = []
        for item in self.list_items():
            if item.id != request.requested_equipment_id:
                continue
            reserved = sum(
                r.quantity
                for r in self.requests
                if r.status == RESERVED
                and r.id != request.id
                and r.equipment_id == item.id
                and datetime.fromisoformat(r.starts_at) < datetime.fromisoformat(request.ends_at)
                and datetime.fromisoformat(r.ends_at) > datetime.fromisoformat(request.starts_at)
            )
            available = item.total_quantity - item.out_of_service_quantity - reserved
            result.append(
                {
                    "equipmentId": str(item.id),
                    "name": item.name,
                    "location": item.location,
                    "totalQuantity": item.total_quantity,
                    "outOfServiceQuantity": item.out_of_service_quantity,
                    "reservedQuantity": reserved,
                    "availableQuantity": available,
                    "shortfall": max(0, request.quantity - available),
                }
            )
        return result

    def decide(
        self, request_id: int, version: int, actor_id: int, item_id: int | None, reason: str
    ) -> dict:
        from app import event_store, notification_store, users
        from app.event_status import EventStatus
        from app.permissions import Role

        with self.lock:
            current = self.get_request(request_id)
            actor = users.get_by_id(actor_id)
            if actor is None or actor.role is not Role.TECH_SUPPORT:
                return {"code": "forbidden"}
            if current is None:
                return {"code": "request_not_found"}
            if current.version != version or current.status != "Requested":
                return {"code": "stale_request"}
            event = event_store.repository().get_event(current.event_id)
            if event is None or event.status is not EventStatus.PLANNING:
                return {"code": "rule_refused"}
            if item_id is not None:
                stock = next(
                    (
                        row
                        for row in self.availability(request_id)
                        if row["equipmentId"] == str(item_id)
                    ),
                    None,
                )
                if stock is None:
                    return {"code": "invalid_equipment"}
                if stock["shortfall"]:
                    return {"code": "insufficient_stock", **stock}
            elif not reason.strip():
                return {"code": "invalid_reason"}
            state = RESERVED if item_id is not None else "Unavailable"
            updated = replace(
                current,
                status=state,
                equipment_id=item_id,
                unavailable_reason=reason.strip() if item_id is None else "",
                version=version + 1,
                updated_by_id=actor_id,
            )
            if event.coordinator_id is not None:
                notification_store.repository().create_notice(
                    user_id=event.coordinator_id,
                    event_id=event.id,
                    kind=f"equipment-{state.lower()}",
                    message=f"{current.quantity} × {current.equipment_type} for "
                    f'"{event.title}": {state}.'
                    + (f" Reason: {reason.strip()}" if item_id is None else ""),
                )
            self.requests = [updated if r.id == request_id else r for r in self.requests]
            self._record(updated, "Updated", current)
            return {"code": "ok"}


_repository: Repository = SupabaseEquipment()


def repository() -> Repository:
    return _repository


def use_repository(value: Repository) -> Repository:
    global _repository
    previous = _repository
    _repository = value
    return previous
