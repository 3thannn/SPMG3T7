# E2E Test Coverage

## Summary

**Total: 33 E2E tests covering 9 User Stories**

These E2E tests cover Sprint 3 User Stories: US1.4, US8.2, US8.3, US8.6 (Coordinator Lead features), US2.1 (event request, reopened with mandatory fields) and US9.4 (venue setup and turnaround time)

E2E tests cover the user journey for each acceptance criterion. Field-by-field validation and boundary values are covered by the unit tests (see [Unit-tested boundaries](#unit-tested-boundaries)).

---

## Test Coverage

### ✅ Fully Tested User Stories

| US ID | Title | E2E Tests |
|-------|-------|-----------|
| **US1.1** | Login | 3 tests |
| **US1.2** | Logout | 2 tests |
| **US1.3** | Baseline access enforcement | 4 tests |
| **US1.4** | Add Coordinator Lead and Safety Officer roles | 2 tests |
| **US8.2** | Lead views the unassigned queue | 2 tests |
| **US8.3** | Lead assigns a Coordinator | 1 test |
| **US8.6** | Coordinators only manage events assigned to them | 2 tests |
| **US2.1** | Mandatory fields + set options on event request (reopened) | 6 tests |
| **US9.4** | Set venue setup and turnaround time | 7 tests |
| | **Additional tests** | 4 tests (session persistence, navigation, full flow) |

---

## What Is Tested

### 1. Authentication (US1.1, US1.2, US1.3)
- Valid/invalid sign-in credentials
- Sign-out functionality
- Role-based access control
- Session persistence

### 2. New Roles (US1.4)
- Coordinator Lead can sign in and is routed to unassigned queue
- Safety Officer can sign in and is routed to safety review page

### 3. Unassigned Queue (US8.2)
- Lead can view unassigned events
- Search functionality works

### 4. Assignment (US8.3)
- Lead can open assignment modal
- Lead can see available coordinators

### 5. Visibility (US8.6)
- Regular coordinators cannot access unassigned queue
- Event organisers cannot access unassigned queue

### 6. Full Flow Test
- Create event → Submit → Appears in unassigned queue → Can be assigned

### 7. Event Request (US2.1, reopened in Sprint 3) — `e2e/event-request-mandatory-fields.spec.ts`
- A complete request is submitted and saved with every answer, including a "None / Not required" answer (checked after a reload)
- Layout, facilities and accessibility are picked from set options; "None / Not required" clears options already ticked
- Missing fields show a clear error and block submit
- A draft saves without the checks (US2.2), is refused on submit while incomplete, and is submitted once complete
- Only an Organiser can open the event request form
- If the connection fails on submit, the answers are kept

### 8. Venue Setup and Turnaround Time (US9.4) — `e2e/venue-setup-turnaround.spec.ts`
- Both times default to 0 on a new venue
- Venue Staff set both times on create and change them on edit
- A time that is not a whole number of minutes is refused, and the saved value is kept
- Coordinators see both times on the venue detail view, without an edit option
- Only Venue Staff can set the times (Coordinator is denied the add and edit pages)
- Re-check (US15.2): a change that makes two bookings clash lists the clash and removes nothing — both bookings stay on their events
- Re-check: a turnaround that exactly fills the gap between bookings is not a clash, and goes straight back to the venue

The re-check tests create their own bookings through the full journey: Organiser submits two events 30 minutes apart, the Coordinator Lead assigns them, and the Coordinator approves them and requests the venue.

Every test uses unique event and venue names and dates relative to today, so it can run against a shared database. Venues without bookings are deleted at the end of each test; the venue used by the re-check tests keeps its bookings, so it cannot be deleted.

### Unit-tested boundaries

These are deliberately not repeated as E2E tests:

| Story | Unit tests | What they cover |
|-------|------------|-----------------|
| **US2.1** | `src/pages/NewEventPage.test.tsx`, `src/draftRules.test.ts`, `src/eventNeeds.test.ts`, `backend/tests/test_event_needs.py` | Each of the 11 required fields on its own, "None / Not required" for every need, whitespace-only answers, attendance limits (0, 1, negative, decimal, 2,147,483,647), end time vs start time, past dates, text lengths, off-list values refused by the API |
| **US9.4** | `src/venueTurnaround.test.ts`, `src/pages/VenueFormPage.test.tsx`, `backend/tests/test_venue_turnaround.py` | Minutes of 0, 1, 1440 and 1441, negatives, decimals and text; Venue Staff only on the API; the occupied-window arithmetic; back-to-back vs overlapping bookings; cancelled bookings ignored; "new" vs "already overlapping" clashes |

---

## How to Run Tests

```bash
# Run all tests
npx playwright test

# Run with visible browser
npx playwright test --headed

# Run with UI mode
npx playwright test --ui

# Run specific test file
npx playwright test e2e/authentication.spec.ts

# View test report
npx playwright show-report
```

---

## Test Files

- `e2e/authentication.spec.ts` - 11 tests for authentication and access control
- `e2e/coordinator-lead-assignment.spec.ts` - 9 tests for coordinator lead features
- `e2e/event-request-mandatory-fields.spec.ts` - 6 tests for the US2.1 event request 
- `e2e/venue-setup-turnaround.spec.ts` - 7 tests for US9.4 venue setup and turnaround time 
- `e2e/helpers.ts` - Test utilities (signIn, signOut, test users)
