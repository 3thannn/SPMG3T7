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

from app.suitability import BookingNeeds, assess
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






class TestLayout:



    def test_a_layout_not_listed_is_not_suitable_and_names_the_ones_that_are(self):
        [reason] = assess(VENUE, needs(layout="Theatre")).reasons

        assert reason == (
            "It does not support the Theatre layout. "
            "It supports: Breakout tables, standing, classroom."
        )




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


    def test_ending_after_closing_is_not_suitable(self):
        assert not assess(VENUE, needs(starts_at=at(2, 18), ends_at=at(2, 22, 1))).suitable







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






