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

    def test_far_over_capacity_says_both_numbers(self):
        [reason] = assess(VENUE, needs(headcount=300)).reasons

        assert "60" in reason
        assert "300" in reason


class TestLayout:


    def test_layouts_compare_without_case_or_extra_spaces(self):
        assert assess(VENUE, needs(layout="  Breakout   TABLES ")).suitable


    def test_a_layout_is_matched_whole_not_as_part_of_another(self):
        """"table" is not a layout this venue lists, even inside "Breakout tables"."""
        assert not assess(VENUE, needs(layout="table")).suitable



class TestFacilitiesAndAccessibility:


    def test_each_missing_facility_is_its_own_reason(self):
        verdict = assess(VENUE, needs(facilities=("PA system", "stage lighting", "bar")))

        assert verdict.reasons == (
            "It does not list stage lighting among its facilities.",
            "It does not list bar among its facilities.",
        )





class TestOperatingHours:

    def test_exactly_the_hours_is_suitable(self):
        assert assess(VENUE, needs(starts_at=at(2, 8), ends_at=at(2, 22))).suitable



    def test_running_overnight_is_not_suitable_and_says_how_to_book_it(self):
        [reason] = assess(VENUE, needs(starts_at=at(2, 9), ends_at=at(3, 17))).reasons

        assert reason.endswith("A booking over several days can be requested a day at a time.")


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




    def test_a_quoted_element_may_hold_a_comma_or_an_escaped_quote(self):
        assert listed_items(r'{"tables, chairs","the \"big\" screen"}') == (
            "tables, chairs",
            'the "big" screen',
        )


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

    def test_a_two_day_booking_at_an_all_day_venue(self):
        hours = parse_hours("00:00-24:00")
        assert hours is not None

        assert within_hours(hours, at(2, 9), at(3, 17))

