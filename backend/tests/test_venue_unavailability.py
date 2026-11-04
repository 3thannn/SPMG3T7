"""The venue blackout endpoints — US12.1.

Venue Staff mark the date ranges a venue cannot be used; Coordinators see them
when they open the venue. The classes below follow the acceptance criteria in
order, then the boundaries of the one real rule (the end is not before the
start), then every way a request can be refused.

Fixture venues are 1 (Great Hall), 2 (Bertha Room) and 3 (Seminar Room 4); see
conftest. No blackout periods exist until a test records one.
"""

import pytest

GREAT_HALL = "1"
SEMINAR_ROOM = "3"

#: A valid range. Tests override one field at a time, so a failure names the
#: field that broke rather than the whole request.
# US12.2: Updated to use structured reason types
RANGE = {
    "startDate": "2026-11-02",
    "endDate": "2026-11-06",
    "reasonType": "maintenance",
    "otherReason": "",
}


def path(venue_id: str = GREAT_HALL) -> str:
    return f"/venues/{venue_id}/unavailability"


def mark(client, headers, venue_id: str = GREAT_HALL, **overrides):
    """POST a range with overrides; `None` drops the field from the body."""
    body = {**RANGE, **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(path(venue_id), json=body, headers=headers)


def refusal(response) -> dict:
    """The 400 body, asserting it is the shape this story promises."""
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_unavailability"
    return detail


@pytest.fixture
def staff(auth_headers):
    return auth_headers("Venue Staff")


@pytest.fixture
def coordinator(auth_headers):
    return auth_headers("Event Coordinator")


class TestRecordingARange:
    """AC1 and AC3: Venue Staff record a start and end; it is stored for the venue."""

    def test_venue_staff_record_a_range(self, client, staff):
        response = mark(client, staff)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["venueId"] == GREAT_HALL
        assert body["startDate"] == "2026-11-02"
        assert body["endDate"] == "2026-11-06"
        assert body["reasonType"] == "maintenance"
        assert body["otherReason"] == ""
        assert body["createdAt"]

    def test_the_response_uses_the_wire_names_and_nothing_else(self, client, staff):
        body = mark(client, staff).json()

        expected = {
            "id", "venueId", "startDate", "endDate", "reasonType", "otherReason", "createdAt",
            "flaggedBookingsCount",
        }
        assert set(body) == expected
        assert body["flaggedBookingsCount"] == 0
        assert isinstance(body["id"], str)

    def test_the_range_is_stored_against_the_venue(self, client, staff, unavailability_repository):
        mark(client, staff)

        [stored] = unavailability_repository.entries
        assert stored.venue_id == 1
        assert stored.start_date.isoformat() == "2026-11-02"
        assert stored.end_date.isoformat() == "2026-11-06"








class TestTheReason:
    """US12.2: Structured reason types with optional custom text for "other"."""


    def test_other_reason_type_requires_custom_text(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="other", otherReason=""))

        assert "custom reason" in detail["message"].lower()










class TestEndNotBeforeStart:
    """AC2: the end date is not earlier than the start date — at every boundary."""

    def test_a_one_day_range_is_accepted(self, client, staff):
        """Equal dates are a single-day closure, the tightest valid range."""
        response = mark(client, staff, startDate="2026-11-02", endDate="2026-11-02")

        assert response.status_code == 201, response.text
        assert response.json()["startDate"] == response.json()["endDate"]


    def test_an_end_one_day_before_the_start_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, startDate="2026-11-02", endDate="2026-11-01"))

        assert detail["message"] == "The end date cannot be earlier than the start date."












class TestViewingRanges:
    """AC4: Coordinators see a venue's blackout periods when they view it."""

    def test_a_coordinator_sees_the_venues_ranges(self, client, staff, coordinator):
        created = mark(client, staff).json()

        response = client.get(path(), headers=coordinator)

        assert response.status_code == 200, response.text
        assert response.json() == [{**created, "flaggedBookingsCount": None}]












class TestWhoMayDoWhat:
    """Venue Staff record; anyone who can read the catalogue can view."""

    def test_a_coordinator_cannot_record_a_range(self, client, coordinator):
        response = mark(client, coordinator)

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["required"] == "venues:edit"
        assert detail["role"] == "Event Coordinator"











