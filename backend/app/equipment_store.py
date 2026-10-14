"""Equipment catalogue and Requested lines, with Supabase and test repositories."""

from dataclasses import dataclass, field, replace
from typing import Protocol

from app import supabase_client
from app.event_store import _now


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
    )


class Repository(Protocol):
    def list_items(self) -> list[Equipment]: ...
    def get_item(self, item_id: int) -> Equipment | None: ...
    def save_item(self, item: Equipment) -> Equipment: ...
    def delete_item(self, item_id: int) -> None: ...
    def list_for_event(self, event_id: int) -> list[EquipmentRequest]: ...
    def list_requested(self) -> list[EquipmentRequest]: ...
    def get_request(self, request_id: int) -> EquipmentRequest | None: ...
    def create_request(self, request: EquipmentRequest) -> EquipmentRequest: ...
    def update_request(
        self, request: EquipmentRequest, expected_version: int
    ) -> EquipmentRequest | None: ...
    def delete_request(self, request_id: int, expected_version: int, actor_id: int) -> bool: ...
    def list_history(self, event_id: int) -> list[RequestHistory]: ...


class SupabaseEquipment:
    item_columns = (
        "id, name, equipment_type, description, location, total_quantity, "
        "out_of_service_quantity, out_of_service_reason"
    )
    request_columns = (
        "id, event_id, equipment_type, quantity, technical_requirements, "
        "support_notes, start_at, end_at, status, requested_by_id, "
        "created_at, version, updated_by_id, events(name)"
    )

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

    def list_for_event(self, event_id: int) -> list[EquipmentRequest]:
        rows = (
            supabase_client.admin()
            .table("equipment_requests")
            .select(self.request_columns)
            .eq("event_id", event_id)
            .eq("status", "Requested")
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
                }
            )
            .eq("id", request.id)
            .eq("version", expected_version)
            .eq("status", "Requested")
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
            .eq("status", "Requested")
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


@dataclass
class InMemoryEquipment:
    items: list[Equipment] = field(default_factory=list)
    requests: list[EquipmentRequest] = field(default_factory=list)
    history: list[RequestHistory] = field(default_factory=list)
    next_item_id: int = 1
    next_request_id: int = 1

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
        if not item.id:
            item = replace(item, id=self.next_item_id)
            self.next_item_id += 1
        self.items = [old for old in self.items if old.id != item.id] + [item]
        return item

    def delete_item(self, item_id: int) -> None:
        self.items = [item for item in self.items if item.id != item_id]

    def list_for_event(self, event_id: int) -> list[EquipmentRequest]:
        return sorted(
            (r for r in self.requests if r.event_id == event_id and r.status == "Requested"),
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
        if current is None or current.version != expected_version or current.status != "Requested":
            return None
        updated = replace(request, version=expected_version + 1)
        self.requests = [updated if r.id == request.id else r for r in self.requests]
        self._record(updated, "Updated", current)
        return updated

    def delete_request(self, request_id: int, expected_version: int, actor_id: int) -> bool:
        current = self.get_request(request_id)
        if current is None or current.version != expected_version or current.status != "Requested":
            return False
        removed = replace(
            current, status="Removed", version=expected_version + 1, updated_by_id=actor_id
        )
        self.requests = [removed if r.id == request_id else r for r in self.requests]
        self._record(removed, "Removed", current)
        return True

    def list_history(self, event_id: int) -> list[RequestHistory]:
        return sorted(
            (h for h in self.history if h.event_id == event_id),
            key=lambda h: (h.at, h.id),
            reverse=True,
        )


_repository: Repository = SupabaseEquipment()


def repository() -> Repository:
    return _repository


def use_repository(value: Repository) -> Repository:
    global _repository
    previous = _repository
    _repository = value
    return previous
