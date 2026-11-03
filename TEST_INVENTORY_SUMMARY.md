# Test Inventory Summary - SPMG3T7

**Generated:** 2026-11-03
**Total Tests:** 1,568

## Overview

This document summarizes the automated test suite for the SPM G3T7 Event Management System.

## Test Distribution

| Test Type    | Count | Percentage |
|--------------|-------|------------|
| Unit         | 581   | 37.1%      |
| Integration  | 953   | 60.8%      |
| E2E          | 34    | 2.2%       |
| **TOTAL**    | **1,568** | **100%** |

### By Category
- **Backend Tests:** 1,534 (98%)
- **Frontend Tests:** 34 (2%)

## Top Test Files (by count)

| Count | File | Primary Feature |
|-------|------|----------------|
| 90 | test_cancel_event_us4_6.py | Event Cancellation (US4.6) |
| 72 | test_booking_conflicts.py | Booking Conflict Detection |
| 64 | test_change_requests.py | Change Request Management |
| 52 | test_safety_check_us4_4.py | Safety Checks (US4.4) |
| 51 | test_booking_decisions.py | Booking Decision Workflow |
| 45 | test_registration_us20_2.py | Event Registration (US20.2) |
| 45 | test_venue_turnaround.py | Venue Turnaround Times |
| 41 | test_venue_suitability.py | Venue Suitability Analysis |
| 41 | test_venues.py | Venue Management |
| 40 | test_booking_store.py | Booking Repository (Unit) |

## Top User Stories (by test count)

| Count | User Story | Feature |
|-------|------------|---------|
| 90 | US4.6 | Event Cancellation |
| 52 | US4.4 | Safety Checks |
| 45 | US20.2 | Event Registration List |
| 37 | US20.1 | Event Registration |
| 37 | US17.1 | Safety Review |
| 37 | US12.3 | Venue Availability |
| 35 | US11.2 | Change Review |
| 30 | US9.5 | Venue Deletion Constraints |
| 29 | US20.3 | Registration Management |
| 28 | US14.5 | Replacement Venue |

## Test Types Explained

### Unit Tests (581)
- Test individual functions, classes, and modules in isolation
- Focus on business logic, data models, and repository operations
- Examples:
  - `test_booking_store.py` - Booking repository CRUD operations
  - `test_venue_store.py` - Venue repository queries
  - `test_equipment_store.py` - Equipment request storage
  - `test_registration_store.py` - Registration data operations

### Integration Tests (953)
- Test API endpoints with TestClient
- Verify multiple components working together
- Cover full request/response cycles
- Examples:
  - Booking conflict detection across venues
  - Change request approval workflows
  - Event cancellation cascades
  - Registration capacity management

### E2E Tests (34)
- Full browser automation using Playwright
- Test complete user journeys
- Verify frontend-backend integration
- Examples:
  - Coordinator lead assignment flow
  - Venue replacement workflow
  - Event submission and review process

## Files Reference

**Full CSV:** `test_inventory.csv` (1,569 rows including header)
**Location:** `/Users/ethan/Documents/GitHub/SPMG3T7/test_inventory.csv`
**OneDrive Copy:** `OneDrive/.../IS212.../Project/Test_Inventory_SPMG3T7.csv`

**CSV Columns:**
1. Test ID - Unique identifier (BT0001-BT1534, E2E0001-E2E0034)
2. Test Type - Unit/Integration/E2E
3. Category - Backend/Frontend
4. User Story - Reference to requirements (e.g., US9.4)
5. Feature - Human-readable feature name
6. Test File - Relative path to test file
7. Test Class - pytest class name (if applicable)
8. Test Name - Test function name
9. Full Name - Class::function format for unique identification

## Test Reduction Context

**Starting Point:** ~2,504 backend tests (before reduction)
**After Reduction:** 1,534 backend tests
**Tests Removed:** ~970 tests

### What Was Removed
1. **Coverage Scaffolding (59 tests)** - Guard tests that only checked for coverage
   - test_remaining_guards.py
   - test_event_route_guards.py
   - test_change_review_paths.py

2. **Infrastructure Test Classes (~300 tests)** - Removed duplicate Supabase/InMemory store testing classes while keeping core tests

3. **Redundant Parameterized Tests (~600 tests)** - Trimmed excessive parameterized test cases while keeping representative samples

### What Was Kept
- All unit tests for core repositories (booking, venue, equipment, registration)
- Essential integration tests for API endpoints
- Critical user story acceptance criteria tests
- All E2E tests for complete workflows

## Testing Pyramid Status

**Current State:**
```
    E2E (34) - 2%     ◢◣
  Integration (953)   ███
     60%              ███
  Unit (581) - 37%    ███████
                      ███████
```

**Note:** The pyramid is not ideal. Best practice suggests:
- Unit: 70% (~1,100 tests)
- Integration: 25% (~400 tests)
- E2E: 5% (~80 tests)

However, given the project context (integration-heavy FastAPI application with extensive API surface), the current distribution is acceptable for the scope.

## Running Tests

### Backend Tests
```bash
cd /Users/ethan/Documents/GitHub/SPMG3T7/backend
source .venv/bin/activate
pytest                                    # Run all 1,534 tests
pytest tests/test_venue_store.py         # Run specific file
pytest -k "test_booking"                 # Run tests matching pattern
pytest --collect-only                    # List all tests
```

### Frontend E2E Tests
```bash
cd /Users/ethan/Documents/GitHub/SPMG3T7/frontend
npx playwright test                      # Run all 34 e2e tests
npx playwright test e2e/coordinator-lead-assignment.spec.ts  # Run specific file
npx playwright test --headed             # Run with visible browser
```

## Key Metrics

- **Test Execution Time:** ~2-3 minutes (backend), ~5-8 minutes (e2e with headed)
- **Backend Test Coverage:** ~85% (estimated)
- **API Endpoints Tested:** ~60 routes
- **User Stories Covered:** 40+ user stories
- **Test Files:** 48 backend test files + 4 frontend e2e files

## Maintenance Notes

1. **Adding New Tests:** Follow existing file naming pattern `test_<feature>_us<X>_<Y>.py`
2. **Classification:** Use TestClient = Integration, Repository tests = Unit
3. **User Story Tags:** Include US reference in filename for traceability
4. **Parameterization:** Use sparingly - prefer focused, readable test cases
5. **Test Data:** Use fixtures from `conftest.py` for consistent test data

---

**Last Updated:** 2026-11-03
**Maintained By:** SPM G3T7 Team
**Project:** Event Management System
