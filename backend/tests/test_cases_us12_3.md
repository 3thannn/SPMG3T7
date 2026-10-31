# US12.3 venue availability view: test coverage

Scope source: the US12.3 user story and acceptance criteria (SPMG3T7-82).
Release 1 is the list view; the calendar grid is left for later, as the team
decided.

## Acceptance coverage

| Requirement | Evidence |
| --- | --- |
| AC1: pick a range from the venue's page; default the next 14 days, today included | `test_venue_availability_us12_3.py`: `TestTheDefaultRange`, `test_with_no_range_it_shows_the_next_14_days`, `TestPickingTheRange`; `VenueAvailability.test.tsx` "AC1: the range" |
| AC1: a range that cannot be used is refused in a sentence (to before from, bad or impossible date, over 366 days) | `test_a_range_that_cannot_be_used_is_refused`; frontend checks the same before sending ("the range helpers") |
| AC2: Confirmed, Requested, holds and unavailability periods, labelled by type, in time order | `TestWhatIsListed::test_each_entry_is_labelled_by_type`, `TestTheRange::test_it_is_chronological_by_when_the_venue_is_taken`; frontend "AC2" |
| AC2: holds show their expiry | `test_a_hold_says_when_it_expires`; frontend "shows when a hold expires" |
| AC3: bookings show the full occupied window, setup and turnaround included | `TestTheOccupiedWindow`, `test_a_booking_entry_carries_both_windows`; frontend "AC3" |
| AC3: setup alone can bring a booking into the range; touching at midnight is not overlap (US15.1's half-open windows) | `test_setup_alone_can_bring_a_booking_into_the_range`, `test_one_whose_turnaround_ends_at_midnight_on_the_first_day_is_not` |
| AC4: Expired, Cancelled and Rejected hidden; so are lapsed holds, Needs replacement and Replaced, which no longer hold the venue | `test_what_does_not_hold_the_venue_is_hidden`, `test_a_hold_past_its_expiry_is_hidden_before_the_sweep_marks_it` |
| Coordinators and Venue Staff can open it; other roles cannot | `test_a_role_without_the_catalogue_is_refused` (Organiser, 403) |
| A Coordinator sees titles only for events assigned to them (US8.6); Venue Staff see all | `test_a_coordinator_sees_only_their_own_events_titles`, `test_venue_staff_see_every_events_title` |
| Times read the same in any browser timezone | `VenueAvailability.test.tsx` "times read the same in any timezone" (UTC, Singapore, New York) |

## Checked by hand

Against the shared project's data, read only: Bugis Lecture Theatre lists its
one upcoming Requested booking and hides its Cancelled and Replaced ones;
Jurong Innovation Hub lists two Confirmed bookings and a Maintenance day in
time order, each booking widened by the venue's 10 minutes' setup and
turnaround.
