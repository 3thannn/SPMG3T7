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





    def test_a_stored_range_reads_back(self, client, staff):
        created = mark(client, staff).json()

        listed = client.get(path(), headers=staff).json()

        assert listed == [{**created, "flaggedBookingsCount": None}]






class TestTheReason:
    """US12.2: Structured reason types with optional custom text for "other"."""


    def test_other_reason_type_requires_custom_text(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="other", otherReason=""))

        assert "custom reason" in detail["message"].lower()





    def test_custom_reason_one_over_the_limit_is_refused(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="x" * (REASON_MAX + 1))
        detail = refusal(response)

        assert str(REASON_MAX) in detail["message"]


    def test_missing_reason_type_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType=None))

        assert "reason type" in detail["message"].lower()

    def test_invalid_reason_type_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="invalid_type"))

        assert "maintenance" in detail["message"] or "valid" in detail["message"].lower()


class TestEndNotBeforeStart:
    """AC2: the end date is not earlier than the start date — at every boundary."""



    def test_an_end_one_day_before_the_start_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, startDate="2026-11-02", endDate="2026-11-01"))

        assert detail["message"] == "The end date cannot be earlier than the start date."








class TestMalformedDates:
    """A date that cannot be read is a 400 with a sentence, never a 500 or a guess."""

    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    def test_a_missing_date_is_refused(self, client, staff, field):
        detail = refusal(mark(client, staff, **{field: None}))

        which = "start" if field == "startDate" else "end"
        assert detail["message"] == f"Give the {which} date."












class TestNoConflictChecks:
    """AC5: this sprint only records blackout periods — nothing is compared."""



    def test_a_range_over_an_existing_event_date_is_recorded(self, client, staff, auth_headers):
        """An event already planned inside the range does not block the closure.

        Events carry no venue until Sprint 3's bookings, so there is nothing to
        conflict with — this pins down that recording does not go looking.
        """
        event = client.post(
            "/events",
            json={"title": "Charity Gala", "startsAt": "2026-11-04T18:00"},
            headers=auth_headers("Event Organiser"),
        )
        assert event.status_code == 201, event.text

        assert mark(client, staff).status_code == 201


class TestViewingRanges:
    """AC4: Coordinators see a venue's blackout periods when they view it."""






    def test_identical_ranges_keep_the_order_they_were_recorded_in(
        self, client, staff, coordinator
    ):
        first = mark(client, staff, reasonType="other", otherReason="first").json()
        second = mark(client, staff, reasonType="other", otherReason="second").json()

        listed = client.get(path(), headers=coordinator).json()

        assert [r["id"] for r in listed] == [first["id"], second["id"]]





class TestUnknownVenue:
    """A range belongs to a venue that exists; asking about one that does not is 404."""

    @pytest.mark.parametrize("venue_id", ["999", "abc", "0", "-1", "1.5"])
    def test_recording_against_a_missing_venue_is_404(self, client, staff, venue_id):
        response = mark(client, staff, venue_id=venue_id)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "venue_not_found"

    @pytest.mark.parametrize("venue_id", ["999", "abc", "0", "-1", "1.5"])
    def test_viewing_a_missing_venue_is_404(self, client, coordinator, venue_id):
        response = client.get(path(venue_id), headers=coordinator)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "venue_not_found"





class TestWhoMayDoWhat:
    """Venue Staff record; anyone who can read the catalogue can view."""



    def test_an_organiser_cannot_view_ranges(self, client, staff, auth_headers):
        """Organisers hold no venue permission at all (US9.2), so this is no exception."""
        mark(client, staff)

        response = client.get(path(), headers=auth_headers("Event Organiser"))

        assert response.status_code == 403
        assert response.json()["detail"]["required"] == "venues:read"









class TestPlanningAroundBlackouts:
    """US12.1 "so that Coordinators don't consider it": the catalogue leaves out, for the
    dates being planned, any venue marked unavailable on one of them.

    The Great Hall is closed 2-6 November in every test here. Two inclusive
    ranges overlap when each starts no later than the other ends, so the edges
    that matter are the 1st (clear), the 2nd (blocked), the 6th (blocked) and
    the 7th (clear).
    """

    @pytest.fixture(autouse=True)
    def hall_closed(self, client, staff):
        response = mark(client, staff, startDate="2026-11-02", endDate="2026-11-06")
        assert response.status_code == 201, response.text

    def names(self, client, headers, **params) -> list[str]:
        response = client.get("/venues", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [venue["name"] for venue in response.json()]




    @pytest.mark.parametrize(
        ("params", "hall_shown"),
        [
            ({"availableFrom": "2026-11-06"}, False),
            ({"availableFrom": "2026-11-07"}, True),
            ({"availableTo": "2026-11-02"}, False),
            ({"availableTo": "2026-11-01"}, True),
        ],
    )
    def test_either_date_alone_means_that_one_day(self, client, coordinator, params, hall_shown):
        assert ("Great Hall" in self.names(client, coordinator, **params)) is hall_shown











    def test_an_end_before_the_start_is_refused(self, client, coordinator):
        response = client.get(
            "/venues",
            params={"availableFrom": "2026-11-06", "availableTo": "2026-11-05"},
            headers=coordinator,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_filter"
        assert "cannot be earlier" in detail["message"]

    @pytest.mark.parametrize(
        ("params", "box"),
        [
            ({"availableFrom": "04/11/2026"}, "available-from"),
            ({"availableTo": "04/11/2026"}, "available-to"),
            ({"availableFrom": "2026-11-04", "availableTo": "tomorrow"}, "available-to"),
            ({"availableFrom": "soon", "availableTo": "2026-11-04"}, "available-from"),
        ],
    )
    def test_a_malformed_date_is_refused_naming_its_box(self, client, coordinator, params, box):
        response = client.get("/venues", params=params, headers=coordinator)

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_filter"
        assert detail["message"] == f"Give the {box} date as YYYY-MM-DD."

