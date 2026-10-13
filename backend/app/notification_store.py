"""Organiser notifications, backed by the Supabase `notifications` table — US10.1.

A notification is written when a Coordinator moves an event to Under Review,
Approved or Rejected, and read by the Organiser who owns that event. This
module is only the access; when to write one and who may read it are decided
in `app.notifications`.

Two choices worth knowing:

* The status and message are copied onto the row rather than read back from
  the event. A notice says what happened at the time; an event approved after
  a clarification request must not turn its earlier "asked for more
  information" notice into "approved".
* Ordering is unread first, then newest first, and it is done by the store so
  the database index carries it. The list is meant to be read from the top.
"""

from dataclasses import dataclass, field, replace
from typing import Protocol

from app import event_store, supabase_client
from app.event_status import EventStatus
from app.event_store import _now

TABLE = "notifications"
COLUMNS = "id, user_id, event_id, status, message, is_read, created_at, read_at, events(name)"


@dataclass(frozen=True)
class Notification:
    id: int
    user_id: int
    event_id: int
    #: The status the event moved to when this was written.
    status: EventStatus
    message: str
    is_read: bool
    created_at: str
    #: The event's current title, for the list. Empty if it could not be read.
    event_title: str = ""
    #: Empty while unread.
    read_at: str = ""


def _embedded_title(row: dict) -> str:
    embedded = row.get("events")
    if isinstance(embedded, dict):
        return embedded.get("name") or ""
    return ""


def to_notification(row: dict) -> Notification:
    return Notification(
        id=row["id"],
        user_id=row["user_id"],
        event_id=row["event_id"],
        status=EventStatus(row["status"]),
        message=row["message"],
        is_read=bool(row["is_read"]),
        created_at=str(row["created_at"]),
        event_title=_embedded_title(row),
        read_at=str(row["read_at"]) if row.get("read_at") else "",
    )


def ordered(notifications: list[Notification]) -> list[Notification]:
    """Unread first, then newest first. Ids break ties between same-second rows.

    Two stable sorts: newest first, then unread before read, which keeps the
    newest-first order inside each group.
    """
    newest = sorted(notifications, key=lambda item: (item.created_at, item.id), reverse=True)
    return sorted(newest, key=lambda item: item.is_read)


class Repository(Protocol):
    def list_for_user(self, user_id: int) -> list[Notification]: ...

    def get(self, notification_id: int) -> Notification | None: ...

    def create(
        self, *, user_id: int, event_id: int, status: EventStatus, message: str
    ) -> Notification: ...

    def set_read(self, notification_id: int, *, is_read: bool) -> Notification: ...


class SupabaseNotifications:
    """The real store. Goes through the service role client, like the others."""

    def list_for_user(self, user_id: int) -> list[Notification]:
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("user_id", user_id)
            .order("is_read")
            .order("created_at", desc=True)
            .order("id", desc=True)
            .execute()
            .data
            or []
        )
        return [to_notification(row) for row in rows]

    def get(self, notification_id: int) -> Notification | None:
        rows = (
            supabase_client.admin()
            .table(TABLE)
            .select(COLUMNS)
            .eq("id", notification_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return to_notification(rows[0]) if rows else None

    def create(
        self, *, user_id: int, event_id: int, status: EventStatus, message: str
    ) -> Notification:
        inserted = (
            supabase_client.admin()
            .table(TABLE)
            .insert(
                {
                    "user_id": user_id,
                    "event_id": event_id,
                    "status": str(status),
                    "message": message,
                    "created_at": _now(),
                }
            )
            .execute()
        )
        created = self.get(inserted.data[0]["id"])
        assert created is not None  # noqa: S101 — the row was just inserted
        return created

    def set_read(self, notification_id: int, *, is_read: bool) -> Notification:
        supabase_client.admin().table(TABLE).update(
            {"is_read": is_read, "read_at": _now() if is_read else None}
        ).eq("id", notification_id).execute()
        updated = self.get(notification_id)
        assert updated is not None  # noqa: S101 — the caller checked it exists
        return updated


@dataclass
class InMemoryNotifications:
    """A stand-in for tests, with the same ordering and read-state behaviour."""

    notifications: list[Notification] = field(default_factory=list)
    next_id: int = 1

    def _title(self, event_id: int) -> str:
        """Stands in for the joined `events(name)`, read from the event store."""
        event = event_store.repository().get_event(event_id)
        return event.title if event is not None else ""

    def list_for_user(self, user_id: int) -> list[Notification]:
        return ordered([item for item in self.notifications if item.user_id == user_id])

    def get(self, notification_id: int) -> Notification | None:
        return next((item for item in self.notifications if item.id == notification_id), None)

    def create(
        self, *, user_id: int, event_id: int, status: EventStatus, message: str
    ) -> Notification:
        created = Notification(
            id=self.next_id,
            user_id=user_id,
            event_id=event_id,
            status=status,
            message=message,
            is_read=False,
            created_at=_now(),
            event_title=self._title(event_id),
        )
        self.next_id += 1
        self.notifications.append(created)
        return created

    def set_read(self, notification_id: int, *, is_read: bool) -> Notification:
        existing = self.get(notification_id)
        assert existing is not None  # noqa: S101 — the caller checked it exists
        updated = replace(existing, is_read=is_read, read_at=_now() if is_read else "")
        self.notifications = [
            updated if item.id == notification_id else item for item in self.notifications
        ]
        return updated


_repository: Repository = SupabaseNotifications()


def use_repository(repository_to_use: Repository) -> Repository:
    """Swap the store. Returns the previous one so a test can put it back."""
    global _repository
    previous = _repository
    _repository = repository_to_use
    return previous


def repository() -> Repository:
    return _repository
