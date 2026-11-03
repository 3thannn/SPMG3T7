"""The venue blackout endpoints — US12.1.

Venue Staff mark the date ranges a venue cannot be used; Coordinators see them
when they open the venue. The classes below follow the acceptance criteria in
order, then the boundaries of the one real rule (the end is not before the
start), then every way a request can be refused.

Fixture venues are 1 (Great Hall), 2 (Bertha Room) and 3 (Seminar Room 4); see
conftest. No blackout periods exist until a test records one.
"""

import pytest

from app.venues import REASON_MAX
from tests.conftest import COORDINATOR_ID, VENUE_STAFF_ID

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

    def test_the_record_keeps_who_marked_it(self, client, staff, unavailability_repository):
        mark(client, staff)

        assert unavailability_repository.entries[0].created_by_id == VENUE_STAFF_ID

    def test_a_stored_range_reads_back(self, client, staff):
        created = mark(client, staff).json()

        listed = client.get(path(), headers=staff).json()

        assert listed == [{**created, "flaggedBookingsCount": None}]

    def test_each_range_gets_its_own_id(self, client, staff):
        first = mark(client, staff).json()
        second = mark(client, staff, startDate="2026-12-01", endDate="2026-12-02").json()

        assert first["id"] != second["id"]

    def test_the_range_is_only_stored_for_the_venue_named(self, client, staff):
        mark(client, staff, venue_id=GREAT_HALL)

        assert client.get(path(SEMINAR_ROOM), headers=staff).json() == []

    def test_dates_are_trimmed_before_they_are_read(self, client, staff):
        response = mark(client, staff, startDate="  2026-11-02 ", endDate="\t2026-11-06\n")

        assert response.status_code == 201, response.text
        assert response.json()["startDate"] == "2026-11-02"

    def test_a_past_range_is_recorded(self, client, staff):
        """The story sets no rule about the past, so a closure last year is a record."""
        response = mark(client, staff, startDate="2020-01-01", endDate="2020-01-31")

        assert response.status_code == 201, response.text


class TestTheReason:
    """US12.2: Structured reason types with optional custom text for "other"."""

    def test_a_valid_reason_type_is_accepted(self, client, staff):
        response = mark(client, staff, reasonType="maintenance", otherReason="")

        assert response.status_code == 201, response.text
        assert response.json()["reasonType"] == "maintenance"
        assert response.json()["otherReason"] == ""

    def test_other_reason_type_requires_custom_text(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="other", otherReason=""))

        assert "custom reason" in detail["message"].lower()

    def test_other_reason_type_with_custom_text_is_accepted(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="Unexpected flooding")

        assert response.status_code == 201, response.text
        assert response.json()["reasonType"] == "other"
        assert response.json()["otherReason"] == "Unexpected flooding"

    def test_custom_text_is_trimmed(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="  Roof  repair ")

        assert response.json()["otherReason"] == "Roof  repair"

    def test_a_blank_custom_reason_for_other_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="other", otherReason="   "))

        assert "custom reason" in detail["message"].lower()

    def test_custom_reason_at_the_limit_is_accepted(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="x" * REASON_MAX)

        assert response.status_code == 201, response.text

    def test_custom_reason_one_over_the_limit_is_refused(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="x" * (REASON_MAX + 1))
        detail = refusal(response)

        assert str(REASON_MAX) in detail["message"]

    def test_the_limit_is_counted_after_trimming(self, client, staff):
        """Padding a custom reason that fits does not push it over."""
        text = "  " + "x" * REASON_MAX + "  "
        response = mark(client, staff, reasonType="other", otherReason=text)

        assert response.status_code == 201, response.text

    def test_missing_reason_type_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType=None))

        assert "reason type" in detail["message"].lower()

    def test_invalid_reason_type_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="invalid_type"))

        assert "maintenance" in detail["message"] or "valid" in detail["message"].lower()


class TestEndNotBeforeStart:
    """AC2: the end date is not earlier than the start date — at every boundary."""

    def test_a_one_day_range_is_accepted(self, client, staff):
        """Equal dates are a single-day closure, the tightest valid range."""
        response = mark(client, staff, startDate="2026-11-02", endDate="2026-11-02")

        assert response.status_code == 201, response.text
        assert response.json()["startDate"] == response.json()["endDate"]

    def test_an_end_one_day_after_the_start_is_accepted(self, client, staff):
        response = mark(client, staff, startDate="2026-11-02", endDate="2026-11-03")

        assert response.status_code == 201, response.text

    def test_an_end_one_day_before_the_start_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, startDate="2026-11-02", endDate="2026-11-01"))

        assert detail["message"] == "The end date cannot be earlier than the start date."

    def test_an_end_long_before_the_start_is_refused(self, client, staff):
        refusal(mark(client, staff, startDate="2026-11-02", endDate="2020-01-01"))

    def test_the_comparison_is_by_date_across_a_month_end(self, client, staff):
        """October has 31 days, so the 31st to the 1st is one day forward, not back."""
        assert mark(client, staff, startDate="2026-10-31", endDate="2026-11-01").status_code == 201
        refusal(mark(client, staff, startDate="2026-11-01", endDate="2026-10-31"))

    def test_the_comparison_is_by_date_across_a_year_end(self, client, staff):
        assert mark(client, staff, startDate="2026-12-31", endDate="2027-01-01").status_code == 201
        refusal(mark(client, staff, startDate="2027-01-01", endDate="2026-12-31"))

    def test_a_range_ending_on_a_leap_day_is_accepted(self, client, staff):
        response = mark(client, staff, startDate="2028-02-28", endDate="2028-02-29")

        assert response.status_code == 201, response.text

    def test_a_long_range_is_accepted(self, client, staff):
        """No upper bound on length: a long closure is still a closure."""
        response = mark(client, staff, startDate="2026-01-01", endDate="2030-12-31")
