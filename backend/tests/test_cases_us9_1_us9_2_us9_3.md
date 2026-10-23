# Test Cases for US9.1a–c, US9.2, US9.3: The Venue Catalogue

> **US9.1a–c** As Venue Staff, I want to add, edit and remove venue records, so
> that the catalogue matches the venues we actually have.
>
> **US9.2** As an Event Coordinator, I want to browse the venue catalogue and open
> any venue's details, so that I can choose a venue for an event.
>
> **US9.3** As an Event Coordinator, I want to filter the catalogue by capacity,
> location and accessibility, so that I only see venues that fit.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| US9.1a | Venue Staff add a venue: name, capacity (a positive whole number) and location required; facilities, accessibility features, supported layouts and operating hours optional | Done |
| US9.1b | Venue Staff edit any field except the system-generated ones (`id`, `created_at`) | Done |
| US9.1c | Venue Staff remove a venue | Done — a hard delete; since US14.1, refused while the venue has bookings |
| US9.2 | A Coordinator lists the catalogue and opens any venue, with every recorded detail | Done |
| US9.3 | A Coordinator filters by minimum capacity, location and accessibility, combined with AND | Done — filtered in Postgres |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Reading and writing belong to different roles.** Coordinators read (US9.2,
  US9.3); Venue Staff read and write (US9.1a–c). Neither role holds everything the
  other does, and Organisers see none of it.
- **Capacity must be at least 1.** A venue that holds nobody is not one anyone can
  plan around.
- **Names are unique** (`venues.name` is UNIQUE). A clash is answered with 409 and
  the name, not a database error.
- **Filters are literal text.** `%` and `_` are escaped, so typing "100%" does not
  match everything. An empty or whitespace-only box is not a filter. Location and
  accessibility match part of the text, ignoring case. Minimum capacity includes
  the number typed.
- **Delete is a hard delete** and answers 404 for a venue already gone, so a stale
  list is noticed instead of hidden.
- **Times are shown in Singapore time.** "Catalogue record last updated" converts the
  stored UTC `updated_at`.

## Workflow Visualization

```
Coordinator ─ GET /venues?minCapacity=&location=&accessibility= ─► list, by name
            ─ GET /venues/{id} ───────────────────────────────────► one venue, read-only

Venue Staff ─ POST   /venues        (name, capacity, location required) ─► 201
            ─ PUT    /venues/{id}   (id, created_at never written)      ─► 200
            ─ DELETE /venues/{id}   (asks first in the page)            ─► 204
                       └─ already gone → 404; has bookings → 409 (US14.1)

Organiser   ─ any of the above ─► 403
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `test_venues.py` (routes and rules), `test_venue_store.py` (the Supabase store's queries, against a fake query builder) |
| Backend (regression) | `test_venue_bookings.py` — `test_a_booked_venue_cannot_be_deleted`, `test_an_unbooked_venue_still_deletes` |
| Frontend | `VenuesPage.test.tsx`, `VenueDetailPage.test.tsx`, `VenueFormPage.test.tsx`, `venuesStore.test.ts`, `permissions.test.ts` (US9.2 and US9.1a-c blocks) |
| Database | `SUPABASE_SETUP.sql` (`venues`), `SUPABASE_ADD_VENUE_LAYOUTS.sql` (`supported_layouts`), `SUPABASE_SEED_VENUES.sql` |

---

## 1. HAPPY PATH TEST CASES

### TC-V01: A Coordinator lists the catalogue (US9.2)
- **Test Steps**: `GET /venues` as a Coordinator
- **Expected Result**: 200; every venue, ordered by name, with name, location, capacity, facilities, accessibility features, layouts and hours; a detail never recorded comes back as empty text, not null
- **Automated**: `test_a_coordinator_sees_the_catalogue`, `test_the_catalogue_is_ordered_by_name`, `test_a_venue_carries_the_details_a_coordinator_needs`, `test_unrecorded_details_come_back_empty_rather_than_null`; frontend "lists every venue in the catalogue", "shows where a venue is and how many it holds", "counts what is on screen"

### TC-V02: A Coordinator opens one venue (US9.2)
- **Expected Result**: every detail is labelled; one not recorded says so; the page is read-only for a Coordinator and links back to the catalogue
- **Automated**: `test_a_coordinator_can_open_any_venue`; frontend "shows the venue and every recorded detail", "labels every detail, so an empty one is still accounted for", "says a detail is not recorded rather than leaving it blank", "gives a Coordinator nothing that writes", "tells a Coordinator the record is read-only to them", "offers a way back to the catalogue"

### TC-V03: Filter by capacity, location and accessibility together (US9.3)
- **Test Steps**: `GET /venues?minCapacity=200&location=library&accessibility=step-free`
- **Expected Result**: only venues meeting all three; still ordered by name; the page says the filters combine and that the list is filtered
- **Automated**: `test_minimum_capacity_keeps_the_venues_big_enough`, `test_location_matches_part_of_the_location`, `test_accessibility_matches_part_of_the_features`, `test_filters_combine_with_and_not_or`, `test_all_three_filters_at_once`, `test_filtering_still_comes_back_ordered_by_name`; frontend "offers a filter for each of the three criteria", "sends all three filters together", "says that the filters combine rather than leaving it ambiguous", "describes the list as filtered once it is"

### TC-V04: The filter runs in Postgres, not after the fact (US9.3)
- **Expected Result**: the Supabase store sends `gte` on capacity and `ilike` on location and on accessibility, all in one query; an empty filter is not sent
- **Automated**: `TestFilteringHappensInThePostgresQuery`

### TC-V05: Venue Staff add a venue (US9.1a)
- **Test Steps**: `POST /venues` with `{"name": "Seminar Room 9", "capacity": 40, "location": "School of Computing"}`
- **Expected Result**: 201; the venue has its own id and timestamps and appears in the catalogue; optional details are empty unless given
- **Automated**: `test_venue_staff_can_add_a_venue`, `test_a_created_venue_appears_in_the_catalogue`, `test_the_optional_details_are_optional`, `test_the_optional_details_are_kept_when_given`, `test_the_new_venue_carries_its_own_id_and_timestamps`; frontend "creates a venue from the three required fields alone", "sends the optional fields when they are filled in"

### TC-V06: Venue Staff edit a venue (US9.1b)
- **Expected Result**: every editable field changes; an optional field can be cleared; keeping its own name is fine; `updated_at` is stamped
- **Automated**: `test_venue_staff_can_change_a_venue`, `test_every_editable_field_actually_changes`, `test_an_optional_field_can_be_cleared`, `test_keeping_its_own_name_is_not_a_clash`, `test_updating_stamps_updated_at_itself`; frontend "loads the venue into the form when editing", "saves the change against that venue", "can clear an optional field, because editing is a replacement"

### TC-V07: Venue Staff remove a venue (US9.1c)
- **Test Steps**: delete the venue from its page, then confirm
- **Expected Result**: the page asks first, naming the venue and saying it cannot be undone; then 204; the venue leaves the catalogue and can no longer be opened; the row is gone, not flagged; other venues are untouched
- **Automated**: `test_venue_staff_can_remove_a_venue`, `test_a_deleted_venue_leaves_the_catalogue`, `test_a_deleted_venue_cannot_be_opened`, `test_it_is_a_hard_delete_not_a_flag`, `test_deleting_one_venue_leaves_the_others_alone`; frontend "does not delete on the first click", "asks first, naming the venue and saying it cannot be undone", "deletes once confirmed", "backs out without deleting"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-V10: Each role sees only what it may use
- **Expected Result**: Venue Staff see "Add a venue" and the edit form; a Coordinator sees neither; an empty catalogue invites Venue Staff to fill it and tells a Coordinator it is not theirs to fill
- **Automated**: frontend "offers Venue Staff a way to add a venue", "does not offer a Coordinator an action they do not hold", "invites Venue Staff to fill an empty catalogue", "tells a Coordinator an empty catalogue is not theirs to fill", "offers Venue Staff the edit form for this venue"; `permissions.test.ts` US9.2 and US9.1a-c blocks

### TC-V11: System-generated fields cannot be written
- **Expected Result**: an `id` or `created_at` in the request is ignored; the form has no input for them and never sends them
- **Automated**: `test_an_id_in_the_request_is_ignored`, `test_the_id_cannot_be_edited`, `test_created_at_cannot_be_edited`, `test_updating_never_sends_the_system_generated_fields`; frontend "has no input for a system-generated field", "never sends a system-generated field in the payload"

### TC-V12: Failures say what went wrong
- **Expected Result**: an unreachable API, a server fault and a refused filter each read differently; an empty result is told apart from an empty catalogue
- **Automated**: frontend "distinguishes an unreachable API from an empty catalogue", "sends a server fault to the backend log rather than to the API switch", "says what was wrong with a filter instead of blaming the API", "tells an empty result apart from an empty catalogue", "distinguishes an unreachable API from a missing venue"

### TC-V13: Text is trimmed, never searched or stored with spaces
- **Automated**: `test_surrounding_space_is_trimmed_from_the_fields`, `test_surrounding_space_is_trimmed_rather_than_searched_for`, `test_a_filter_is_trimmed_before_it_is_sent`; frontend "trims what was typed rather than storing the spaces", "trims a filter rather than searching for the spaces"

### TC-V14: The last-updated time is shown in Singapore time
- **Expected Result**: stored `2026-01-05T09:00:00` (UTC) shows as "Catalogue record last updated 05 Jan 2026, 17:00."
- **Automated**: frontend "shows when the record was last updated, in Singapore time"

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-V20 | An Organiser lists, opens or filters venues | 403 | `test_an_organiser_cannot_see_the_catalogue`, `test_an_organiser_cannot_open_a_venue_either`, `test_an_organiser_cannot_filter_what_they_cannot_read` |
| TC-V21 | A Coordinator or an Organiser creates, edits or deletes | 403 | `test_a_coordinator_cannot_create_a_venue`, `test_a_coordinator_cannot_update_a_venue`, `test_a_coordinator_cannot_delete_a_venue`, `test_an_organiser_cannot_write_either` |
| TC-V22 | Venue Staff open the events list or the user directory | 403 | `test_venue_staff_cannot_reach_the_events_list`, `test_venue_staff_cannot_read_the_user_directory` |
| TC-V23 | Signed out | 401 | `test_the_catalogue_needs_a_session`, `test_a_venue_needs_a_session`, `test_writing_needs_a_session_at_all`, `test_signing_out_is_enough_to_lose_access` |
| TC-V24 | Name, location or capacity missing, or only spaces | 400, "Give the venue a name." / "… a location." / "… a capacity." | `test_a_name_is_required`, `test_a_name_of_only_spaces_is_no_name`, `test_a_location_is_required`, `test_a_location_of_only_spaces_is_no_location`, `test_a_capacity_is_required`; frontend "refuses to submit without a name", "refuses to submit without a location", "refuses to submit without a capacity" |
| TC-V25 | Capacity not a number (`"many"`) | Refused (400 or 422) | `test_a_capacity_that_is_not_a_whole_number_is_refused`; frontend "refuses a capacity that is not a positive whole number" |
| TC-V26 | A name another venue already has (create or edit) | 409 `venue_name_taken`, naming the venue | `test_a_duplicate_name_is_a_conflict_not_a_crash`, `test_taking_the_name_of_another_venue_is_a_conflict`, `TestDuplicateNames`; frontend "shows the reason when the server refuses the name" |
| TC-V27 | Open, edit or delete a venue that is not there; an id that is not a number | 404, not 500 | `test_a_venue_that_does_not_exist_is_a_404`, `test_an_id_that_is_not_a_number_is_a_404_not_a_500`, `test_updating_a_venue_that_is_not_there`, `test_deleting_a_venue_that_is_not_there`; frontend "says when a venue is not in the catalogue", "says when the venue being edited is not there" |
| TC-V28 | Delete a venue an event has booked (since US14.1) | 409 `venue_in_use`, "<name> has venue bookings, so it cannot be removed from the catalogue." | `test_a_booked_venue_cannot_be_deleted`; frontend "shows the reason when the server refuses a delete" |
| TC-V29 | A filter that cannot be read: capacity not a number, negative or fractional; text over 200 characters | 400 with a sentence | `TestBadFilters` |
| TC-V30 | An Organiser sends a malformed filter | 403 (the role is checked first) | `test_a_refused_role_wins_over_a_malformed_filter` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-V40 | Capacity 0 / 1 | Refused / accepted | `test_a_capacity_must_be_positive`; frontend "requires the capacity to be positive" |
| TC-V41 | Capacity above 2,147,483,647 (the Postgres integer limit) | Refused with a sentence | `test_a_capacity_beyond_what_postgres_can_store_is_refused` |
| TC-V42 | Name over 255 / location over 500 characters | Refused with a sentence | `test_an_overlong_name_is_refused_with_a_sentence`, `test_an_overlong_location_is_refused_with_a_sentence` |
| TC-V43 | `minCapacity` equal to a venue's capacity | That venue is included | `test_minimum_capacity_is_inclusive` |
| TC-V44 | Empty or whitespace-only filter | Not a filter: the whole catalogue | `test_no_filters_still_returns_the_whole_catalogue`, `test_an_empty_filter_is_not_a_filter`, `test_a_whitespace_filter_is_not_a_filter`; frontend "asks for the whole catalogue before anything is filtered" |
| TC-V45 | `%` or `_` in a filter | Matched literally | `test_wildcards_in_a_filter_are_matched_literally`, `test_wildcards_are_escaped_rather_than_passed_through`, `test_underscores_are_escaped_too` |
| TC-V46 | Location in another case | Matched | `test_location_ignores_case` |
| TC-V47 | Nothing matches; a venue with no accessibility recorded | Empty list, not an error; never matched by an accessibility filter | `test_criteria_that_nothing_satisfies_is_an_empty_list`, `test_a_venue_with_nothing_recorded_never_matches_accessibility` |
| TC-V48 | Delete the same venue twice | 204, then 404 | `test_deleting_twice_says_so_the_second_time` |
| TC-V49 | An empty catalogue; one venue | `[]`, not an error; "venue" in the singular | `test_an_empty_catalogue_is_an_empty_list_not_an_error`; frontend "says the catalogue is empty when it is", "says venue rather than venues when there is one" |

The planning-date filter on the catalogue page (US12.1) and setup and turnaround
times (US9.4) have their own stories and tests.

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 168 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 199 passed |
