"""The suitability rule on its own — US18.1.

`assess` is pure, so the rule is tested here without routes: one class per
condition in the story, in its order, then how the venue's free-text fields are
read. The route tests in test_venue_suitability.py check that the rule is
shown and enforced; this file checks that the rule is right.

Dates: 2027-11-01 is a Monday, 2027-11-02 a Tuesday, 2027-11-06 a Saturday and
2027-11-07 a Sunday.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app.suitability import BookingNeeds, assess, listed_items, parse_hours, within_hours
from app.venue_store import Venue

VENUE = Venue(
    id=1,
    name="Innovation Studio",
    location="Science Quarter, Building F",
    capacity=60,
    facilities="Movable staging, PA system, twin projectors, kitchenette",
    accessibility_features="Step-free access, hearing loop",
    operating_hours="08:00-22:00",
    supported_layouts="Breakout tables, standing, classroom",
    created_at="",
    updated_at="",
)


def needs(**overrides) -> BookingNeeds:
    base = BookingNeeds(
        headcount=60,
        starts_at=datetime(2027, 11, 2, 9, 0),
        ends_at=datetime(2027, 11, 2, 17, 0),
    )
    return replace(base, **overrides)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2027, 11, day, hour, minute)


class TestTheStorysTestCases:
    def test_headcount_equal_to_capacity_is_suitable(self):
        verdict = assess(VENUE, needs(headcount=60))

        assert verdict.suitable
        assert verdict.reasons == ()

    def test_headcount_one_over_capacity_is_not_suitable(self):
        verdict = assess(VENUE, needs(headcount=61))

        assert not verdict.suitable
        assert verdict.reasons == ("It holds 60 people, and this booking is for 61.",)


class TestCapacity:
    def test_under_capacity_is_suitable(self):
        assert assess(VENUE, needs(headcount=1)).suitable

    def test_far_over_capacity_says_both_numbers(self):
        [reason] = assess(VENUE, needs(headcount=300)).reasons

        assert "60" in reason
        assert "300" in reason


class TestLayout:
    def test_no_layout_asked_for_is_suitable(self):
        assert assess(VENUE, needs(layout="")).suitable

    def test_a_listed_layout_is_suitable(self):
        assert assess(VENUE, needs(layout="classroom")).suitable

    def test_layouts_compare_without_case_or_extra_spaces(self):
        assert assess(VENUE, needs(layout="  Breakout   TABLES ")).suitable

    def test_a_layout_not_listed_is_not_suitable_and_names_the_ones_that_are(self):
        [reason] = assess(VENUE, needs(layout="Theatre")).reasons

        assert reason == (
            "It does not support the Theatre layout. "
            "It supports: Breakout tables, standing, classroom."
        )

    def test_a_layout_is_matched_whole_not_as_part_of_another(self):
        """"table" is not a layout this venue lists, even inside "Breakout tables"."""
        assert not assess(VENUE, needs(layout="table")).suitable

    def test_a_venue_with_no_layouts_recorded_supports_none(self):
        venue = replace(VENUE, supported_layouts="")

        [reason] = assess(venue, needs(layout="classroom")).reasons

        assert reason == "It does not support the classroom layout. It has no layouts recorded."


class TestFacilitiesAndAccessibility:
    def test_listed_facilities_are_suitable(self):
        assert assess(VENUE, needs(facilities=("PA system", "kitchenette"))).suitable

    def test_a_facility_is_matched_as_part_of_what_is_listed(self):
        """"projector" is met by "twin projectors", as US9.3's filter would match it."""
        assert assess(VENUE, needs(facilities=("Projector",))).suitable

    def test_each_missing_facility_is_its_own_reason(self):
        verdict = assess(VENUE, needs(facilities=("PA system", "stage lighting", "bar")))

        assert verdict.reasons == (
            "It does not list stage lighting among its facilities.",
            "It does not list bar among its facilities.",
        )

    def test_a_listed_accessibility_need_is_suitable(self):
        assert assess(VENUE, needs(accessibility=("hearing loop",))).suitable

    def test_a_missing_accessibility_need_is_not_suitable(self):
        [reason] = assess(VENUE, needs(accessibility=("accessible toilets",))).reasons

        assert reason == "It does not list accessible toilets among its accessibility features."

    def test_a_venue_with_nothing_recorded_meets_no_need(self):
        """An unfilled field is not evidence of a feature, as US9.3 reads it."""
        venue = replace(VENUE, facilities="", accessibility_features="")

        verdict = assess(venue, needs(facilities=("projector",), accessibility=("lift",)))

        assert len(verdict.reasons) == 2


class TestOperatingHours:
    def test_inside_the_hours_is_suitable(self):
        assert assess(VENUE, needs()).suitable

    def test_exactly_the_hours_is_suitable(self):
        assert assess(VENUE, needs(starts_at=at(2, 8), ends_at=at(2, 22))).suitable

    def test_starting_before_opening_is_not_suitable(self):
        [reason] = assess(VENUE, needs(starts_at=at(2, 7, 30), ends_at=at(2, 12))).reasons

        assert reason == "The booking falls outside its operating hours (08:00-22:00)."

    def test_ending_after_closing_is_not_suitable(self):
        assert not assess(VENUE, needs(starts_at=at(2, 18), ends_at=at(2, 22, 1))).suitable

    def test_running_overnight_is_not_suitable_and_says_how_to_book_it(self):
        [reason] = assess(VENUE, needs(starts_at=at(2, 9), ends_at=at(3, 17))).reasons

        assert reason.endswith("A booking over several days can be requested a day at a time.")

    def test_a_closed_day_is_not_suitable(self):
        venue = replace(VENUE, operating_hours="Mon-Fri 08:00-22:00")

        assert assess(venue, needs(starts_at=at(2, 9), ends_at=at(2, 17))).suitable
        assert not assess(venue, needs(starts_at=at(6, 9), ends_at=at(6, 17))).suitable

    def test_hours_not_recorded_are_not_held_against_the_venue(self):
        venue = replace(VENUE, operating_hours="")

        verdict = assess(venue, needs(starts_at=at(2, 3), ends_at=at(2, 4)))

        assert verdict.suitable
        assert verdict.notes == (
            "Its operating hours are not recorded, so the booking time was not checked.",
        )

    def test_hours_that_cannot_be_read_are_noted_not_held_against_it(self):
        venue = replace(VENUE, operating_hours="By arrangement")

        verdict = assess(venue, needs())

        assert verdict.suitable
        assert verdict.notes == (
            "Its operating hours (By arrangement) could not be read, so the booking "
            "time was not checked.",
        )

    def test_readable_hours_leave_no_note(self):
        assert assess(VENUE, needs()).notes == ()


class TestEveryReasonAtOnce:
    def test_all_four_conditions_are_reported_in_the_storys_order(self):
        verdict = assess(
            VENUE,
            needs(
                headcount=61,
                layout="Theatre",
                facilities=("stage lighting",),
                accessibility=("lift",),
                starts_at=at(2, 6),
                ends_at=at(2, 9),
            ),
        )

        assert [reason.split()[:4] for reason in verdict.reasons] == [
            ["It", "holds", "60", "people,"],
            ["It", "does", "not", "support"],
            ["It", "does", "not", "list"],
            ["It", "does", "not", "list"],
            ["The", "booking", "falls", "outside"],
        ]


class TestListedItems:
    def test_a_plain_list(self):
        assert listed_items("Theatre, standing,  cabaret ") == ("Theatre", "standing", "cabaret")

    def test_semicolons_and_new_lines_separate_too(self):
        assert listed_items("stage; PA\nlift") == ("stage", "PA", "lift")

    def test_a_postgres_array_literal(self):
        """What the catalogue holds where a seed wrote arrays into TEXT columns."""
        assert listed_items('{stage,"AV system","catering area"}') == (
            "stage",
            "AV system",
            "catering area",
        )

    def test_an_empty_array_literal_lists_nothing(self):
        assert listed_items("{}") == ()

    def test_a_quoted_element_may_hold_a_comma_or_an_escaped_quote(self):
        assert listed_items(r'{"tables, chairs","the \"big\" screen"}') == (
            "tables, chairs",
            'the "big" screen',
        )

    def test_nothing_recorded_lists_nothing(self):
        assert listed_items("") == ()
        assert listed_items("  ") == ()

    def test_array_literal_venues_are_assessed_like_any_other(self):
        venue = replace(
            VENUE,
            supported_layouts="{theatre,banquet}",
            facilities='{projector,stage,"AV system"}',
            accessibility_features='{"wheelchair access","hearing loop"}',
        )

        verdict = assess(
            venue,
            needs(
                layout="Banquet",
                facilities=("AV system",),
                accessibility=("wheelchair access",),
            ),
        )

        assert verdict.suitable


class TestParseHours:
    @pytest.mark.parametrize(
        "text",
        ["08:00-22:00", "8:00-22:00", "08:00 - 22:00", "08:00–22:00", "Daily 08:00-22:00"],
    )
    def test_one_window_every_day(self, text):
        hours = parse_hours(text)

        assert hours is not None
        assert all(hours[day] == [(8 * 60, 22 * 60)] for day in range(7))

    def test_a_day_range(self):
        hours = parse_hours("Mon-Sat 08:00-22:00")

        assert hours is not None
        assert set(hours) == {0, 1, 2, 3, 4, 5}

    def test_a_day_range_that_wraps_the_weekend(self):
        hours = parse_hours("Fri-Mon 10:00-16:00")

        assert hours is not None
        assert set(hours) == {4, 5, 6, 0}

    def test_full_day_names_and_words(self):
        assert set(parse_hours("Monday-Friday 09:00-17:00") or {}) == {0, 1, 2, 3, 4}
        assert set(parse_hours("Weekends 10:00-14:00") or {}) == {5, 6}

    def test_several_clauses(self):
        hours = parse_hours("Mon-Fri 09:00-17:00, Sat 10:00-14:00")

        assert hours is not None
        assert hours[5] == [(10 * 60, 14 * 60)]
        assert 6 not in hours

    def test_23_59_closes_at_midnight(self):
        hours = parse_hours("00:00-23:59")

        assert hours is not None
        assert hours[0] == [(0, 24 * 60)]

    @pytest.mark.parametrize(
        "text",
        [
            "By arrangement",
            "22:00-02:00",  # overnight: closes no later than it opens
            "08:00-08:00",
            "25:00-26:00",
            "Mon-Funday 09:00-17:00",
            "Mon-Fri 09:00-17:00, closed Sundays",
            "",
        ],
    )
    def test_what_cannot_be_read_is_none(self, text):
        assert parse_hours(text) is None


class TestWithinHours:
    def test_a_booking_up_to_midnight_at_an_all_day_venue(self):
        hours = parse_hours("00:00-23:59")
        assert hours is not None

        assert within_hours(hours, at(2, 20), at(3, 0))

    def test_a_two_day_booking_at_an_all_day_venue(self):
        hours = parse_hours("00:00-24:00")
        assert hours is not None

        assert within_hours(hours, at(2, 9), at(3, 17))

    def test_a_booking_into_a_closed_next_day(self):
        hours = parse_hours("Mon-Sat 00:00-24:00")
        assert hours is not None

        # Saturday evening into Sunday morning: Sunday is closed.
        assert not within_hours(hours, at(6, 20), at(7, 2))
