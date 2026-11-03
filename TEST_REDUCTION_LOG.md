# Test Reduction Execution Log

## Baseline (3 November 2026)

| Layer | Count | Details |
|---|---:|---|
| Backend pytest | 2,504 collected | 73 test files in tests/ |
| Frontend Vitest | ~1,400 tests | To be measured |
| Isolated Playwright | 10 tests | Currently passing |
| **Total** | **~3,914** | |

**Target:** 610-690 meaningful tests (~660 planning number)

## Phase 1: Coverage Scaffolding Removal

### Backend Guard/Route Files Analysis

Files identified for consolidation/removal:
1. `test_remaining_guards.py` - 367 lines, contains 27 tests
   - Session account removal
   - Permission denial messages
   - Notification failure handling
   - Registration race conditions
   - Booking/venue edge cases

2. `test_event_route_guards.py` - 244 lines, contains 12 tests
   - To be analyzed

3. `test_change_review_paths.py` - 264 lines, contains 20 tests
   - Route-level coverage tests

**Total in scaffold files:** 59 tests

### Action Plan

**Step 1:** Analyze each test in guard files to identify:
- Tests with unique behavior → move to owning feature file
- Tests duplicating existing coverage → delete
- Pure coverage scaffolding → delete

**Step 2:** Remove frontend coverage files:
- `*.paths.test.*`
- `*.calls.test.*`
- `*.routes.test.*`

## Decisions Log

| Test ID | File | Unique Behavior | Decision | Moved To | Reviewer | Result |
|---|---|---|---|---|---|---|
| | | | | | | |

## Test Count After Each Change

| Commit | Backend | Frontend | E2E | Total | Coverage % |
|---|---:|---:|---:|---:|---|
| Baseline | 2,504 | ~1,400 | 10 | ~3,914 | 100% / 94.81% |

