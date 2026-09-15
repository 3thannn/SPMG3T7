"""The event request rules, on their own — Event Request Creation.

These are unit tests over `app.event_request_rules`: no client, no session, no
store. The endpoint tests in `test_event_requests.py` cover the same rules
through a request; this file is where each rule is pinned down one at a time,
including the malformed inputs a form cannot produce but a hand-written client
can.

Every case that involves "the past" passes an explicit `today`, so the suite
means the same thing in September as it does in November.
"""

from datetime import date, time

import pytest

from app.event_request_rules import (
    ATTENDANCE_MAX,
    DESCRIPTION_MAX,
    NAME_MAX,
    PURPOSE_MAX,
    InvalidField,
    parse_date,
    parse_time,
    validated,
)

TODAY = date(2026, 9, 15)

COMPLETE = {
    "name": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks, then supper.",
    "proposed_date": "2026-11-02",
    "start_time": "18:00",
    "end_time": "21:30",
    "expected_attendance": 120,
}


def check(**overrides):
    """Validate a complete request with some fields swapped out."""
    return validated(**{**COMPLETE, **overrides}, today=TODAY)


def refusal(**overrides) -> InvalidField:
    """The InvalidField a bad request raises, for asserting field and message."""
    with pytest.raises(InvalidField) as caught:
        check(**overrides)
    return caught.value


class TestParsingADate:
    def test_a_plain_iso_date(self):
        assert parse_date("2026-11-02") == date(2026, 11, 2)

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "02-11-2026",
            "2026/11/02",
            "20261102",  # date.fromisoformat takes this; the form never sends it
            "2026-11-02T18:00",
            "2026-W45-1",
            "not a date",
            "2026-11-2",
        ],
    )
    def test_anything_that_is_not_that_format(self, raw):
        assert parse_date(raw) is None

    @pytest.mark.parametrize("raw", ["2026-02-30", "2026-13-01", "2026-00-10"])
    def test_a_well_formed_day_that_does_not_exist(self, raw):
        """The shape is right and the day is not — 31 February is still no date."""
        assert parse_date(raw) is None


class TestParsingATime:
    def test_hours_and_minutes(self):
        assert parse_time("18:00") == time(18, 0)

    def test_seconds_are_accepted(self):
        """A <input type="time"> sends them once its step is finer than a minute."""
        assert parse_time("18:00:30") == time(18, 0, 30)

    @pytest.mark.parametrize(
        "raw",
        ["", "6pm", "18", "18:00+08:00", "1:00", "18:00:00.5", "half past six"],
    )
    def test_anything_else(self, raw):
        assert parse_time(raw) is None

    @pytest.mark.parametrize("raw", ["25:00", "18:60", "18:00:61"])
    def test_a_well_formed_time_that_does_not_exist(self, raw):
        assert parse_time(raw) is None


class TestACompleteRequest:
    def test_it_comes_back_with_every_field(self):
        request = check()

        assert request.name == "Faculty Welcome Night"
        assert request.purpose == "Welcome the new intake."
        assert request.description == "Talks, then supper."
        assert request.expected_attendance == 120

    def test_the_date_and_the_two_times_become_two_timestamps(self):
        """The form asks three questions; `events` holds two columns."""
        request = check()

        assert request.starts_at == "2026-11-02T18:00"
        assert request.ends_at == "2026-11-02T21:30"

    def test_seconds_are_dropped_from_the_stored_timestamps(self):
        request = check(start_time="18:00:30", end_time="21:30:45")

        assert request.starts_at == "2026-11-02T18:00"
        assert request.ends_at == "2026-11-02T21:30"

    def test_surrounding_whitespace_is_trimmed(self):
        request = check(
            name="  Faculty Welcome Night  ",
            purpose="  Welcome the new intake.  ",
            description="  Talks.  ",
            proposed_date=" 2026-11-02 ",
            start_time=" 18:00 ",
            end_time=" 21:30 ",
        )

        assert request.name == "Faculty Welcome Night"
        assert request.purpose == "Welcome the new intake."
        assert request.description == "Talks."
        assert request.starts_at == "2026-11-02T18:00"


class TestTheRequiredFields:
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_a_name_is_required(self, blank):
        assert refusal(name=blank).message == "Give the event a name."

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_purpose_is_required(self, blank):
        """Optional in the US4.2 draft; required here, because a request is complete."""
        assert refusal(purpose=blank).message == "Say what the event is for."

    @pytest.mark.parametrize("blank", ["", "  "])
    def test_a_proposed_date_is_required(self, blank):
        assert refusal(proposed_date=blank).message == "Give the event a proposed date."

    @pytest.mark.parametrize("blank", ["", "  "])
    def test_a_start_time_is_required(self, blank):
        assert refusal(start_time=blank).message == "Give the event a start time."

    @pytest.mark.parametrize("blank", ["", "  "])
    def test_an_end_time_is_required(self, blank):
        assert refusal(end_time=blank).message == "Give the event an end time."

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_an_expected_attendance_is_required(self, blank):
        assert refusal(expected_attendance=blank).message == "Give the expected attendance."

    def test_the_description_stays_optional(self):
        """The story names five required fields; the rest are the organiser's choice."""
        assert check(description="").description == ""

    def test_each_refusal_names_the_field_it_is_about(self):
        """So the form can put the sentence beside the input rather than on top."""
        assert refusal(name="").field == "name"
        assert refusal(purpose="").field == "purpose"
        assert refusal(proposed_date="").field == "proposedDate"
        assert refusal(start_time="").field == "startTime"
        assert refusal(end_time="").field == "endTime"
        assert refusal(expected_attendance=None).field == "expectedAttendance"
        assert refusal(description="x" * (DESCRIPTION_MAX + 1)).field == "description"


class TestTheLengthLimits:
    def test_a_name_may_fill_the_column(self):
        assert check(name="x" * NAME_MAX).name == "x" * NAME_MAX

    def test_a_name_longer_than_the_column_is_refused(self):
        """events.name is VARCHAR(255); saying so beats a database error."""
        assert "255 characters" in refusal(name="x" * (NAME_MAX + 1)).message

    def test_a_purpose_may_fill_the_column(self):
        assert check(purpose="x" * PURPOSE_MAX).purpose == "x" * PURPOSE_MAX

    def test_a_purpose_longer_than_the_column_is_refused(self):
        assert "500 characters" in refusal(purpose="x" * (PURPOSE_MAX + 1)).message

    def test_a_description_may_reach_the_chosen_limit(self):
        assert len(check(description="x" * DESCRIPTION_MAX).description) == DESCRIPTION_MAX

    def test_a_longer_description_is_refused(self):
        """`text` has no limit of its own, so this one is the team's choice."""
        assert "2000 characters" in refusal(description="x" * (DESCRIPTION_MAX + 1)).message


class TestTheProposedDate:
    def test_a_malformed_date_says_what_shape_it_wants(self):
        assert refusal(proposed_date="02-11-2026").message == (
            "Give the proposed date as YYYY-MM-DD."
        )

    def test_yesterday_is_refused(self):
        assert refusal(proposed_date="2026-09-14").message == (
            "The proposed date cannot be in the past."
        )

    def test_a_date_years_back_is_refused(self):
        assert refusal(proposed_date="2001-01-01").field == "proposedDate"

    def test_today_is_allowed(self):
        """"Not in the past" includes today: an event can be arranged this morning."""
        assert check(proposed_date="2026-09-15").starts_at == "2026-09-15T18:00"

    def test_tomorrow_is_allowed(self):
        assert check(proposed_date="2026-09-16").starts_at == "2026-09-16T18:00"

    def test_the_real_today_is_used_when_none_is_given(self):
        """The default path: a date well in the past is refused without a fixture."""
        with pytest.raises(InvalidField) as caught:
            validated(**{**COMPLETE, "proposed_date": "1999-01-01"})

        assert caught.value.message == "The proposed date cannot be in the past."

    def test_the_real_today_lets_a_future_date_through(self):
        """The other half of the default path, so neither branch goes unexercised."""
        far_off = date.today().replace(year=date.today().year + 1).isoformat()

        assert validated(**{**COMPLETE, "proposed_date": far_off}).starts_at.startswith(
            far_off
        )


class TestTheTimes:
    def test_a_malformed_start_time_says_what_shape_it_wants(self):
        assert refusal(start_time="6pm").message == "Give the start time as HH:MM."

    def test_a_malformed_end_time_says_what_shape_it_wants(self):
        assert refusal(end_time="half nine").message == "Give the end time as HH:MM."

    def test_an_end_before_the_start_is_refused(self):
        assert refusal(start_time="18:00", end_time="17:00").message == (
            "The end time must be after the start time."
        )

    def test_an_end_equal_to_the_start_is_refused(self):
        """A zero-length event is not an event."""
        assert refusal(start_time="18:00", end_time="18:00").field == "endTime"

    def test_a_minute_is_enough(self):
        assert check(start_time="18:00", end_time="18:01").ends_at == "2026-11-02T18:01"

    def test_the_comparison_is_by_time_and_not_by_text(self):
        """"09:00" sorts before "9:00" as text; neither is how clocks work."""
        assert check(start_time="09:00", end_time="10:00").ends_at == "2026-11-02T10:00"


class TestTheExpectedAttendance:
    def test_a_positive_integer_is_kept(self):
        assert check(expected_attendance=1).expected_attendance == 1

    def test_a_numeric_string_is_read_as_a_number(self):
        """A form posts strings; the rule should not care which way it arrived."""
        assert check(expected_attendance="250").expected_attendance == 250

    def test_a_numeric_string_with_spaces_is_read_too(self):
        assert check(expected_attendance="  250  ").expected_attendance == 250

    def test_an_explicit_plus_is_read(self):
        assert check(expected_attendance="+7").expected_attendance == 7

    def test_zero_is_refused(self):
        """The story says positive, and an event nobody attends needs no venue."""
        assert refusal(expected_attendance=0).message == (
            "Expected attendance must be at least 1."
        )

    @pytest.mark.parametrize("value", [-1, "-5"])
    def test_a_negative_number_is_refused(self, value):
        assert refusal(expected_attendance=value).message == (
            "Expected attendance must be at least 1."
        )

    @pytest.mark.parametrize("value", ["twenty", "12.5", "1e3", "12 people", "1,000"])
    def test_something_that_is_not_a_whole_number_is_refused(self, value):
        assert refusal(expected_attendance=value).message == (
            "Expected attendance must be a whole number."
        )

    @pytest.mark.parametrize("value", [12.5, 12.0, [12], {"n": 12}])
    def test_a_json_type_that_is_not_a_number_is_refused(self, value):
        """A hand-written client can send these; a browser form cannot."""
        assert refusal(expected_attendance=value).message == (
            "Expected attendance must be a whole number."
        )

    @pytest.mark.parametrize("value", [True, False])
    def test_a_boolean_is_refused_rather_than_read_as_one_or_zero(self, value):
        """bool subclasses int in Python, so `true` would otherwise mean 1."""
        assert refusal(expected_attendance=value).message == (
            "Expected attendance must be a whole number."
        )

    def test_the_ceiling_may_be_reached(self):
        assert check(expected_attendance=ATTENDANCE_MAX).expected_attendance == ATTENDANCE_MAX

    def test_above_the_ceiling_is_refused(self):
        """A slipped keypress, not a real crowd."""
        assert "1,000,000" in refusal(expected_attendance=ATTENDANCE_MAX + 1).message


class TestTheOrderOfTheChecks:
    """The form reads top to bottom, so the first thing wrong is the first field."""

    def test_the_name_is_reported_before_the_date(self):
        assert refusal(name="", proposed_date="nonsense").field == "name"

    def test_the_date_is_reported_before_the_times(self):
        assert refusal(proposed_date="", start_time="nonsense").field == "proposedDate"

    def test_the_start_is_reported_before_the_end(self):
        assert refusal(start_time="", end_time="nonsense").field == "startTime"

    def test_the_attendance_is_reported_last(self):
        """Everything above it is right, so the only thing left to complain about."""
        assert refusal(expected_attendance="lots").field == "expectedAttendance"
