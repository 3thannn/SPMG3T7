"""The Supabase notification store, against a fake client.

The notification rules are tested against `InMemoryNotifications`. These check
the real store's side of the promise: each recipient's list ordered unread
first, then newest, by the database; each kind of notice written with the
columns that tell it apart; and read state written with its timestamp.
"""

from app.event_status import EventStatus
from app.notification_store import TABLE, SupabaseNotifications

ROW = {
    "id": 11,
    "user_id": 1,
    "event_id": 7,
    "status": "Approved",
    "kind": "event-status",
    "equipment_request_id": None,
    "message": "Your event was approved.",
    "is_read": False,
    "created_at": "2026-10-01T09:00:00",
    "read_at": None,
    "events": {"name": "Faculty Welcome Night"},
}


def written(fake) -> dict:
    """The one row the store inserted."""
    [insert] = fake.on(TABLE)[0].named("insert")
    return insert[1]


class TestReading:
    def test_a_recipient_sees_only_their_own_unread_first_then_newest(self, fake):
        fake.rows = {TABLE: [dict(ROW)]}

        [notice] = SupabaseNotifications().list_for_user(1)

        calls = fake.on(TABLE)[0].calls
        assert ("eq", "user_id", 1) in calls
        assert [call[1:] for call in calls if call[0] == "order"] == [
            ("is_read", False),
            ("created_at", True),
            ("id", True),
        ]
        assert notice.event_title == "Faculty Welcome Night"
        assert notice.status is EventStatus.APPROVED

    def test_a_missing_notice_is_none(self, fake):
        assert SupabaseNotifications().get(404) is None


class TestWriting:
    def test_a_status_notice_records_the_status_it_reports(self, fake):
        fake.queued = {TABLE: [[{"id": 11}], [dict(ROW)]]}

        created = SupabaseNotifications().create(
            user_id=1, event_id=7, status=EventStatus.APPROVED, message="Approved."
        )

        assert written(fake)["status"] == "Approved"
        assert created.id == 11

    def test_an_equipment_notice_points_at_its_request_and_has_no_status(self, fake):
        fake.queued = {
            TABLE: [[{"id": 12}], [dict(ROW, id=12, kind="equipment-request", status=None)]]
        }

        created = SupabaseNotifications().create_equipment(
            user_id=6, event_id=7, request_id=30, message="New equipment request."
        )

        row = written(fake)
        assert row["kind"] == "equipment-request"
        assert row["equipment_request_id"] == 30
        assert row["status"] is None
        assert created.kind == "equipment-request"


    def test_reading_a_notice_stamps_when(self, fake):
        fake.rows = {TABLE: [dict(ROW, is_read=True, read_at="2026-10-02T09:00:00")]}

        updated = SupabaseNotifications().set_read(11, is_read=True)

        [update] = fake.on(TABLE)[0].named("update")
        assert update[1]["is_read"] is True
        assert update[1]["read_at"]
        assert updated.read_at == "2026-10-02T09:00:00"
