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

        assert set(body) == {"id", "venueId", "startDate", "endDate", "reasonType", "otherReason", "createdAt"}
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

        assert listed == [created]

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

        assert "other reason" in detail["message"].lower()

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

        assert "other reason" in detail["message"].lower()

    def test_custom_reason_at_the_limit_is_accepted(self, client, staff):
        response = mark(client, staff, reasonType="other", otherReason="x" * REASON_MAX)

        assert response.status_code == 201, response.text

    def test_custom_reason_one_over_the_limit_is_refused(self, client, staff):
        detail = refusal(mark(client, staff, reasonType="other", otherReason="x" * (REASON_MAX + 1)))

        assert str(REASON_MAX) in detail["message"]

    def test_the_limit_is_counted_after_trimming(self, client, staff):
        """Padding a custom reason that fits does not push it over."""
        response = mark(client, staff, reasonType="other", otherReason="  " + "x" * REASON_MAX + "  ")

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

        assert response.status_code == 201, response.text

    def test_a_refused_range_stores_nothing(self, client, staff, unavailability_repository):
        mark(client, staff, startDate="2026-11-02", endDate="2026-11-01")

        assert unavailability_repository.entries == []


class TestMalformedDates:
    """A date that cannot be read is a 400 with a sentence, never a 500 or a guess."""

    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    def test_a_missing_date_is_refused(self, client, staff, field):
        detail = refusal(mark(client, staff, **{field: None}))

        which = "start" if field == "startDate" else "end"
        assert detail["message"] == f"Give the {which} date."

    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_blank_date_is_refused(self, client, staff, field, blank):
        refusal(mark(client, staff, **{field: blank}))

    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    def test_a_null_date_is_refused(self, client, staff, field):
        response = client.post(path(), json={**RANGE, field: None}, headers=staff)

        refusal(response)

    def test_with_both_dates_missing_the_start_is_named_first(self, client, staff):
        detail = refusal(client.post(path(), json={}, headers=staff))

        assert detail["message"] == "Give the start date."

    @pytest.mark.parametrize(
        "text",
        [
            "not a date",
            "2026/11/02",  # wrong separator
            "02-11-2026",  # day first
            "2026-11-2",  # unpadded day
            "2026-1-02",  # unpadded month
            "26-11-02",  # two-digit year
            "20261102",  # ISO basic form — fromisoformat takes it, the API does not
            "2026-11-02T09:00:00",  # a datetime, not a date
            "2026-11-02Z",
            "+2026-11-02",
            "2026-W45-1",  # ISO week date
            "٢٠٢٦-١١-٠٢",  # Arabic-Indic digits
        ],
    )
    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    def test_a_date_not_written_yyyy_mm_dd_is_refused(self, client, staff, field, text):
        detail = refusal(mark(client, staff, **{field: text}))

        assert "YYYY-MM-DD" in detail["message"]

    @pytest.mark.parametrize(
        "text",
        [
            "2026-02-29",  # 2026 is not a leap year
            "2100-02-29",  # divisible by 100, not by 400: not a leap year
            "2026-02-30",
            "2026-04-31",  # thirty days hath April
            "2026-13-01",
            "2026-00-10",
            "2026-11-00",
            "2026-11-32",
            "0000-01-01",  # year zero is before `date.min`
        ],
    )
    @pytest.mark.parametrize("field", ["startDate", "endDate"])
    def test_a_date_not_on_the_calendar_is_refused(self, client, staff, field, text):
        detail = refusal(mark(client, staff, **{field: text}))

        assert "not a real calendar date" in detail["message"]

    def test_the_extremes_of_the_calendar_are_accepted(self, client, staff):
        """`date.min` and `date.max` as text: the widest range Python can hold."""
        response = mark(client, staff, startDate="0001-01-01", endDate="9999-12-31")

        assert response.status_code == 201, response.text

    def test_the_first_leap_day_in_a_400_year_is_accepted(self, client, staff):
        response = mark(client, staff, startDate="2000-02-29", endDate="2000-02-29")

        assert response.status_code == 201, response.text

    def test_a_date_that_is_not_text_is_refused_by_the_schema(self, client, staff):
        """A number never reaches the parser: Pydantic will not turn it into a string."""
        response = client.post(path(), json={**RANGE, "startDate": 20261102}, headers=staff)

        assert response.status_code == 422

    def test_a_body_that_is_not_an_object_is_refused(self, client, staff):
        response = client.post(path(), json=["2026-11-02", "2026-11-06"], headers=staff)

        assert response.status_code == 422

    def test_a_malformed_date_stores_nothing(self, client, staff, unavailability_repository):
        mark(client, staff, startDate="2026-02-30")

        assert unavailability_repository.entries == []


class TestNoConflictChecks:
    """AC5: this sprint only records blackout periods — nothing is compared."""

    def test_overlapping_ranges_are_both_recorded(self, client, staff):
        first = mark(client, staff, startDate="2026-11-02", endDate="2026-11-10")
        second = mark(client, staff, startDate="2026-11-05", endDate="2026-11-20")

        assert first.status_code == second.status_code == 201
        assert len(client.get(path(), headers=staff).json()) == 2

    def test_the_same_range_twice_is_recorded_twice(self, client, staff):
        mark(client, staff)
        mark(client, staff)

        assert len(client.get(path(), headers=staff).json()) == 2

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

    def test_a_coordinator_sees_the_venues_ranges(self, client, staff, coordinator):
        created = mark(client, staff).json()

        response = client.get(path(), headers=coordinator)

        assert response.status_code == 200, response.text
        assert response.json() == [created]

    def test_venue_staff_see_them_too(self, client, staff):
        mark(client, staff)

        response = client.get(path(), headers=staff)

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_a_venue_with_no_ranges_is_an_empty_list_not_an_error(self, client, coordinator):
        response = client.get(path(), headers=coordinator)

        assert response.status_code == 200
        assert response.json() == []

    def test_ranges_come_back_soonest_first_whatever_order_they_were_entered(
        self, client, staff, coordinator
    ):
        mark(client, staff, startDate="2027-03-01", endDate="2027-03-05")
        mark(client, staff, startDate="2026-11-02", endDate="2026-11-06")
        mark(client, staff, startDate="2026-12-24", endDate="2026-12-26")

        starts = [r["startDate"] for r in client.get(path(), headers=coordinator).json()]

        assert starts == ["2026-11-02", "2026-12-24", "2027-03-01"]

    def test_ranges_starting_the_same_day_are_ordered_by_end(self, client, staff, coordinator):
        mark(client, staff, startDate="2026-11-02", endDate="2026-11-09")
        mark(client, staff, startDate="2026-11-02", endDate="2026-11-03")

        ends = [r["endDate"] for r in client.get(path(), headers=coordinator).json()]

        assert ends == ["2026-11-03", "2026-11-09"]

    def test_identical_ranges_keep_the_order_they_were_recorded_in(
        self, client, staff, coordinator
    ):
        first = mark(client, staff, reasonType="other", otherReason="first").json()
        second = mark(client, staff, reasonType="other", otherReason="second").json()

        listed = client.get(path(), headers=coordinator).json()

        assert [r["id"] for r in listed] == [first["id"], second["id"]]

    def test_only_the_venues_own_ranges_are_shown(self, client, staff, coordinator):
        mark(client, staff, venue_id=GREAT_HALL, reasonType="other", otherReason="Hall closed")
        mark(client, staff, venue_id=SEMINAR_ROOM, reasonType="other", otherReason="Room closed")

        listed = client.get(path(SEMINAR_ROOM), headers=coordinator).json()

        assert [r["otherReason"] for r in listed] == ["Room closed"]
        assert all(r["venueId"] == SEMINAR_ROOM for r in listed)

    def test_past_ranges_are_still_shown(self, client, staff, coordinator):
        mark(client, staff, startDate="2020-01-01", endDate="2020-01-02")

        assert len(client.get(path(), headers=coordinator).json()) == 1

    def test_viewing_changes_nothing(self, client, staff, coordinator, unavailability_repository):
        mark(client, staff)
        before = list(unavailability_repository.entries)

        client.get(path(), headers=coordinator)

        assert unavailability_repository.entries == before


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

    def test_a_missing_venue_is_named_before_bad_dates(self, client, staff):
        """404 before 400: there is no venue for the dates to be wrong about."""
        response = mark(client, staff, venue_id="999", endDate="2000-01-01")

        assert response.status_code == 404

    def test_a_missing_venue_stores_nothing(self, client, staff, unavailability_repository):
        mark(client, staff, venue_id="999")

        assert unavailability_repository.entries == []

    def test_a_deleted_venue_no_longer_has_ranges_to_show(self, client, staff):
        mark(client, staff)
        assert client.delete(f"/venues/{GREAT_HALL}", headers=staff).status_code == 204

        assert client.get(path(), headers=staff).status_code == 404


class TestWhoMayDoWhat:
    """Venue Staff record; anyone who can read the catalogue can view."""

    def test_a_coordinator_cannot_record_a_range(self, client, coordinator):
        response = mark(client, coordinator)

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["required"] == "venues:edit"
        assert detail["role"] == "Event Coordinator"

    def test_an_organiser_cannot_record_a_range(self, client, auth_headers):
        response = mark(client, auth_headers("Event Organiser"))

        assert response.status_code == 403
        assert response.json()["detail"]["required"] == "venues:edit"

    def test_an_organiser_cannot_view_ranges(self, client, staff, auth_headers):
        """Organisers hold no venue permission at all (US9.2), so this is no exception."""
        mark(client, staff)

        response = client.get(path(), headers=auth_headers("Event Organiser"))

        assert response.status_code == 403
        assert response.json()["detail"]["required"] == "venues:read"

    def test_a_refused_role_stores_nothing(self, client, coordinator, unavailability_repository):
        mark(client, coordinator)

        assert unavailability_repository.entries == []

    def test_the_role_is_checked_before_the_venue(self, client, coordinator):
        """A Coordinator learns nothing about which venue ids exist from a write."""
        assert mark(client, coordinator, venue_id="999").status_code == 403

    def test_the_role_is_checked_before_the_dates(self, client, coordinator):
        assert mark(client, coordinator, endDate="2000-01-01").status_code == 403

    def test_recording_needs_a_session(self, client):
        assert client.post(path(), json=RANGE).status_code == 401

    def test_viewing_needs_a_session(self, client):
        assert client.get(path()).status_code == 401

    def test_a_bad_token_is_refused(self, client):
        headers = {"Authorization": "Bearer not-a-real-token"}

        assert client.post(path(), json=RANGE, headers=headers).status_code == 401
        assert client.get(path(), headers=headers).status_code == 401

    def test_a_coordinator_is_not_the_one_recorded_as_marking_it(
        self, client, staff, unavailability_repository
    ):
        """The author is the signed-in user, not something the body can claim."""
        client.post(path(), json={**RANGE, "createdById": COORDINATOR_ID}, headers=staff)

        assert unavailability_repository.entries[0].created_by_id == VENUE_STAFF_ID


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

    def test_without_dates_the_whole_catalogue_is_shown(self, client, coordinator):
        """A blackout hides nothing until a Coordinator says when they are planning for."""
        assert self.names(client, coordinator) == ["Bertha Room", "Great Hall", "Seminar Room 4"]

    @pytest.mark.parametrize(
        ("available_from", "available_to"),
        [
            ("2026-11-02", "2026-11-06"),  # exactly the blackout
            ("2026-10-28", "2026-11-02"),  # ends on its first day
            ("2026-11-06", "2026-11-10"),  # starts on its last day
            ("2026-11-03", "2026-11-04"),  # inside it
            ("2026-10-01", "2026-12-01"),  # around it
        ],
    )
    def test_a_window_touching_the_blackout_leaves_the_venue_out(
        self, client, coordinator, available_from, available_to
    ):
        names = self.names(
            client, coordinator, availableFrom=available_from, availableTo=available_to
        )

        assert names == ["Bertha Room", "Seminar Room 4"]

    @pytest.mark.parametrize(
        ("available_from", "available_to"),
        [
            ("2026-10-28", "2026-11-01"),  # ends the day before
            ("2026-11-07", "2026-11-10"),  # starts the day after
        ],
    )
    def test_a_window_just_clear_of_the_blackout_keeps_the_venue(
        self, client, coordinator, available_from, available_to
    ):
        names = self.names(
            client, coordinator, availableFrom=available_from, availableTo=available_to
        )

        assert "Great Hall" in names

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

    def test_a_one_day_window_is_accepted(self, client, coordinator):
        names = self.names(
            client, coordinator, availableFrom="2026-11-04", availableTo="2026-11-04"
        )

        assert "Great Hall" not in names

    def test_blank_dates_are_no_filter(self, client, coordinator):
        names = self.names(client, coordinator, availableFrom="  ", availableTo="")

        assert "Great Hall" in names

    def test_dates_are_trimmed(self, client, coordinator):
        names = self.names(
            client, coordinator, availableFrom=" 2026-11-02 ", availableTo=" 2026-11-06 "
        )

        assert "Great Hall" not in names

    def test_the_dates_combine_with_the_other_filters(self, client, coordinator):
        """AND, like every other filter: 50 seats and free on the 4th."""
        names = self.names(client, coordinator, minCapacity="50", availableFrom="2026-11-04")

        assert names == ["Seminar Room 4"]

    def test_only_the_closed_venue_is_left_out(self, client, staff, coordinator):
        mark(client, staff, venue_id=SEMINAR_ROOM, startDate="2027-01-01", endDate="2027-01-02")

        names = self.names(client, coordinator, availableFrom="2026-11-04")

        assert names == ["Bertha Room", "Seminar Room 4"]

    def test_several_closed_venues_are_all_left_out(self, client, staff, coordinator):
        mark(client, staff, venue_id=SEMINAR_ROOM, startDate="2026-11-04", endDate="2026-11-04")

        names = self.names(client, coordinator, availableFrom="2026-11-04")

        assert names == ["Bertha Room"]

    def test_a_venue_blocked_twice_over_the_window_is_left_out_once(
        self, client, staff, coordinator
    ):
        mark(client, staff, startDate="2026-11-05", endDate="2026-11-20")

        names = self.names(
            client, coordinator, availableFrom="2026-11-01", availableTo="2026-11-30"
        )

        assert names == ["Bertha Room", "Seminar Room 4"]

    def test_a_venue_is_shown_again_for_dates_outside_every_blackout(
        self, client, staff, coordinator
    ):
        mark(client, staff, startDate="2026-12-24", endDate="2026-12-26")

        names = self.names(
            client, coordinator, availableFrom="2026-11-10", availableTo="2026-12-20"
        )

        assert "Great Hall" in names

    def test_venue_staff_can_filter_too(self, client, staff):
        assert "Great Hall" not in self.names(client, staff, availableFrom="2026-11-04")

    def test_an_organiser_still_cannot_read_the_catalogue(self, client, auth_headers):
        response = client.get(
            "/venues",
            params={"availableFrom": "2026-11-04"},
            headers=auth_headers("Event Organiser"),
        )

        assert response.status_code == 403

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

    @pytest.mark.parametrize("param", ["availableFrom", "availableTo"])
    def test_a_date_not_on_the_calendar_is_refused(self, client, coordinator, param):
        response = client.get("/venues", params={param: "2026-02-29"}, headers=coordinator)

        assert response.status_code == 400
        assert "not a real calendar date" in response.json()["detail"]["message"]
