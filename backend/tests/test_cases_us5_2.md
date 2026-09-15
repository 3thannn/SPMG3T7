# Test Cases for US5.2: Coordinator Edits Event Information

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

## Workflow Visualization

```
Coordinator → Login → View Events List → Select Event → Edit Fields → Save
                                                          ↓
                                        System logs change (important vs routine)
                                                          ↓
                                              Success/Error Response
```

---

## 1. HAPPY PATH TEST CASES

### TC-US5.2-001: Coordinator Successfully Edits Event Name (Routine Change)
- **Test Scenario**: Coordinator edits the name field of an event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=100
  - Original event name = "Team Building Workshop"
- **Test Steps**:
  1. Send PUT request to `/events/100` with updated name
  2. Verify response status code
  3. Verify event name is updated in database
  4. Verify change is logged as "routine"
- **Test Data**:
  ```json
  {
    "name": "Annual Team Building Workshop",
    "purpose": "Original purpose",
    "description": "Original description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event name updated to "Annual Team Building Workshop"
  - Change logged in event_changes table with change_type="routine"
  - changed_field="name"

### TC-US5.2-002: Coordinator Successfully Edits Proposed Date (Important Change)
- **Test Scenario**: Coordinator changes the proposed date of an event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=101
  - Original proposed_date = "2026-10-15T14:00:00"
- **Test Steps**:
  1. Send PUT request to `/events/101` with updated proposed_date
  2. Verify response status code
  3. Verify proposed_date is updated in database
  4. Verify change is logged as "important"
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-11-20T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event proposed_date updated to "2026-11-20T14:00:00"
  - Change logged in event_changes table with change_type="important"
  - changed_field="proposed_date"
  - old_value="2026-10-15T14:00:00", new_value="2026-11-20T14:00:00"

### TC-US5.2-003: Coordinator Successfully Edits Expected Attendance (Important Change)
- **Test Scenario**: Coordinator changes the expected attendance of an event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=102
  - Original expected_attendance = 50
- **Test Steps**:
  1. Send PUT request to `/events/102` with updated expected_attendance
  2. Verify response status code
  3. Verify expected_attendance is updated in database
  4. Verify change is logged as "important"
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 100
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event expected_attendance updated to 100
  - Change logged in event_changes table with change_type="important"
  - changed_field="expected_attendance"
  - old_value="50", new_value="100"

### TC-US5.2-004: Coordinator Successfully Edits Purpose (Routine Change)
- **Test Scenario**: Coordinator updates the purpose field of an event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=103
  - Original purpose = "Team building"
- **Test Steps**:
  1. Send PUT request to `/events/103` with updated purpose
  2. Verify response status code
  3. Verify purpose is updated in database
  4. Verify change is logged as "routine"
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Annual team bonding and skill development",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event purpose updated
  - Change logged in event_changes table with change_type="routine"
  - changed_field="purpose"

### TC-US5.2-005: Coordinator Successfully Edits Description (Routine Change)
- **Test Scenario**: Coordinator updates the description field of an event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=104
  - Original description = "Short description"
- **Test Steps**:
  1. Send PUT request to `/events/104` with updated description
  2. Verify response status code
  3. Verify description is updated in database
  4. Verify change is logged as "routine"
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "A comprehensive workshop covering team collaboration techniques, communication skills, and leadership development. Includes interactive activities and group discussions.",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event description updated
  - Change logged in event_changes table with change_type="routine"
  - changed_field="description"

### TC-US5.2-006: Coordinator Edits Multiple Fields (Mixed Important and Routine)
- **Test Scenario**: Coordinator updates both important and routine fields in one request
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=105
- **Test Steps**:
  1. Send PUT request to `/events/105` updating name (routine), proposed_date (important), and expected_attendance (important)
  2. Verify response status code
  3. Verify all fields are updated
  4. Verify multiple change logs are created with correct types
- **Test Data**:
  ```json
  {
    "name": "Updated Workshop Name",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-12-01T10:00:00",
    "expected_attendance": 75
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - All fields updated
  - 3 entries in event_changes table:
    - name change (routine)
    - proposed_date change (important)
    - expected_attendance change (important)

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-US5.2-007: Coordinator Authorization Check
- **Test Scenario**: Verify only users with EVENTS_EDIT permission can edit events
- **Pre-conditions**:
  - User is logged in as Coordinator (has EVENTS_EDIT permission)
  - Event exists in DRAFT status with id=106
- **Test Steps**:
  1. Verify coordinator has EVENTS_EDIT permission
  2. Send PUT request to `/events/106`
  3. Verify request succeeds
- **Test Data**: Any valid event update
- **Expected Result**:
  - HTTP 200 OK
  - Permission check passes
  - Event updated successfully

### TC-US5.2-008: Audit Trail Completeness
- **Test Scenario**: Verify all required audit information is captured for edits
- **Pre-conditions**:
  - User is logged in as Coordinator with user_id=20
  - Event exists in DRAFT status with id=107
- **Test Steps**:
  1. Send PUT request to `/events/107` updating proposed_date
  2. Query event_changes table for the logged change
  3. Verify all audit fields are populated
- **Test Data**: Update proposed_date
- **Expected Result**:
  - event_changes record contains:
    - event_id=107
    - changed_by_user_id=20
    - changed_field="proposed_date"
    - old_value (original date)
    - new_value (new date)
    - change_type="important"
    - changed_at (timestamp)

### TC-US5.2-009: Concurrent Edit Detection
- **Test Scenario**: Verify system handles concurrent edits gracefully
- **Pre-conditions**:
  - Two coordinators logged in (Coordinator A and Coordinator B)
  - Event exists in DRAFT status with id=108
- **Test Steps**:
  1. Coordinator A retrieves event at timestamp T1
  2. Coordinator B retrieves event at timestamp T1
  3. Coordinator A updates name at timestamp T2
  4. Coordinator B attempts to update name at timestamp T3
  5. Verify both updates are logged
- **Test Data**: Different name updates from each coordinator
- **Expected Result**:
  - Both updates succeed (last write wins)
  - Both changes logged in event_changes table
  - Event reflects the last update (from Coordinator B)

---

## 3. NEGATIVE TEST CASES

### TC-US5.2-010: Non-Coordinator Cannot Edit Events
- **Test Scenario**: Organizer (event owner without EVENTS_EDIT permission) cannot edit via coordinator path
- **Pre-conditions**:
  - User is logged in as Organizer (organiser_id=30)
  - User does NOT have EVENTS_EDIT permission
  - Event exists with id=109, organiser_id=30
- **Test Steps**:
  1. Send PUT request to `/events/109` with coordinator edit flag
  2. Verify request is rejected
- **Test Data**: Any event update
- **Expected Result**:
  - HTTP 403 Forbidden
  - Error message: "User does not have EVENTS_EDIT permission"
  - Event NOT updated
  - No change logged

### TC-US5.2-011: Anonymous User Cannot Edit Events
- **Test Scenario**: Unauthenticated user cannot edit events
- **Pre-conditions**:
  - No user logged in (no auth token)
  - Event exists with id=110
- **Test Steps**:
  1. Send PUT request to `/events/110` without authentication
  2. Verify request is rejected
- **Test Data**: Any event update
- **Expected Result**:
  - HTTP 401 Unauthorized
  - Error message: "Authentication required"
  - Event NOT updated

### TC-US5.2-012: Invalid Event ID
- **Test Scenario**: Coordinator attempts to edit non-existent event
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event with id=999999 does NOT exist
- **Test Steps**:
  1. Send PUT request to `/events/999999`
  2. Verify request is rejected
- **Test Data**: Any valid event data
- **Expected Result**:
  - HTTP 404 Not Found
  - Error message: "Event not found"
  - No change logged

### TC-US5.2-013: Missing Required Field (Name)
- **Test Scenario**: Coordinator attempts to save event without required name field
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=111
- **Test Steps**:
  1. Send PUT request to `/events/111` with empty/null name
  2. Verify request is rejected with validation error
- **Test Data**:
  ```json
  {
    "name": "",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Name is required"
  - Event NOT updated
  - No change logged

### TC-US5.2-014: Missing Required Field (Proposed Date)
- **Test Scenario**: Coordinator attempts to save event without required proposed_date field
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=112
- **Test Steps**:
  1. Send PUT request to `/events/112` with null proposed_date
  2. Verify request is rejected with validation error
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": null,
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Proposed date is required"
  - Event NOT updated
  - No change logged

### TC-US5.2-015: Past Proposed Date
- **Test Scenario**: Coordinator attempts to set proposed_date to a past date
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=113
  - Current date is 2026-09-10
- **Test Steps**:
  1. Send PUT request to `/events/113` with proposed_date in the past
  2. Verify request is rejected with validation error
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-08-01T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Proposed date cannot be in the past"
  - Event NOT updated
  - No change logged

### TC-US5.2-016: Negative Expected Attendance
- **Test Scenario**: Coordinator attempts to set negative expected_attendance
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=114
- **Test Steps**:
  1. Send PUT request to `/events/114` with negative expected_attendance
  2. Verify request is rejected with validation error
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": -10
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Expected attendance must be non-negative"
  - Event NOT updated
  - No change logged

### TC-US5.2-017: Invalid Data Type for Expected Attendance
- **Test Scenario**: Coordinator sends string instead of integer for expected_attendance
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=115
- **Test Steps**:
  1. Send PUT request to `/events/115` with string expected_attendance
  2. Verify request is rejected with validation error
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": "fifty"
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Expected attendance must be an integer"
  - Event NOT updated
  - No change logged

---

## 4. BOUNDARY TEST CASES

### TC-US5.2-018: Event Name at Maximum Length (Just Below)
- **Test Scenario**: Coordinator sets event name to 254 characters (just below 255 limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=116
- **Test Steps**:
  1. Send PUT request to `/events/116` with 254-character name
  2. Verify request succeeds
- **Test Data**:
  ```json
  {
    "name": "A" + ("B" * 253),  // 254 chars total
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event name updated successfully
  - Change logged

### TC-US5.2-019: Event Name at Maximum Length (Exactly At)
- **Test Scenario**: Coordinator sets event name to exactly 255 characters (at limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=117
- **Test Steps**:
  1. Send PUT request to `/events/117` with 255-character name
  2. Verify request succeeds
- **Test Data**:
  ```json
  {
    "name": "A" + ("B" * 254),  // 255 chars total
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event name updated successfully
  - Change logged

### TC-US5.2-020: Event Name Exceeds Maximum Length (Just Above)
- **Test Scenario**: Coordinator attempts to set event name to 256 characters (above limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=118
- **Test Steps**:
  1. Send PUT request to `/events/118` with 256-character name
  2. Verify request is rejected
- **Test Data**:
  ```json
  {
    "name": "A" + ("B" * 255),  // 256 chars total
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 50
  }
  ```
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Name exceeds maximum length of 255 characters"
  - Event NOT updated
  - No change logged

### TC-US5.2-021: Purpose at Maximum Length (Just Below)
- **Test Scenario**: Coordinator sets purpose to 499 characters (just below 500 limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=119
- **Test Steps**:
  1. Send PUT request to `/events/119` with 499-character purpose
  2. Verify request succeeds
- **Test Data**: Purpose with 499 characters
- **Expected Result**:
  - HTTP 200 OK
  - Event purpose updated successfully
  - Change logged

### TC-US5.2-022: Purpose at Maximum Length (Exactly At)
- **Test Scenario**: Coordinator sets purpose to exactly 500 characters (at limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=120
- **Test Steps**:
  1. Send PUT request to `/events/120` with 500-character purpose
  2. Verify request succeeds
- **Test Data**: Purpose with 500 characters
- **Expected Result**:
  - HTTP 200 OK
  - Event purpose updated successfully
  - Change logged

### TC-US5.2-023: Purpose Exceeds Maximum Length (Just Above)
- **Test Scenario**: Coordinator attempts to set purpose to 501 characters (above limit)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=121
- **Test Steps**:
  1. Send PUT request to `/events/121` with 501-character purpose
  2. Verify request is rejected
- **Test Data**: Purpose with 501 characters
- **Expected Result**:
  - HTTP 422 Unprocessable Entity
  - Validation error: "Purpose exceeds maximum length of 500 characters"
  - Event NOT updated
  - No change logged

### TC-US5.2-024: Expected Attendance at Minimum (Zero)
- **Test Scenario**: Coordinator sets expected_attendance to 0
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=122
- **Test Steps**:
  1. Send PUT request to `/events/122` with expected_attendance=0
  2. Verify request succeeds or is handled appropriately
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 0
  }
  ```
- **Expected Result**:
  - HTTP 200 OK (if 0 is valid) OR
  - HTTP 422 Unprocessable Entity with validation error "Expected attendance must be positive"
  - Decision needed: Is 0 attendance valid?

### TC-US5.2-025: Expected Attendance at Minimum Valid (One)
- **Test Scenario**: Coordinator sets expected_attendance to 1
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=123
- **Test Steps**:
  1. Send PUT request to `/events/123` with expected_attendance=1
  2. Verify request succeeds
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": "Team building",
    "description": "Description",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": 1
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event expected_attendance updated to 1
  - Change logged as important

### TC-US5.2-026: Proposed Date at Current Moment (Exactly Now)
- **Test Scenario**: Coordinator sets proposed_date to current timestamp
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=124
  - Current timestamp is 2026-09-10T15:30:00
- **Test Steps**:
  1. Get current timestamp
  2. Send PUT request to `/events/124` with proposed_date=current timestamp
  3. Verify request succeeds or is handled appropriately
- **Test Data**: proposed_date = current timestamp
- **Expected Result**:
  - HTTP 200 OK (if "now" is valid) OR
  - HTTP 422 Unprocessable Entity with validation error "Proposed date must be in the future"
  - Decision needed: Can events be proposed for "right now"?

### TC-US5.2-027: Proposed Date Just After Current Moment
- **Test Scenario**: Coordinator sets proposed_date to 1 minute in the future
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=125
  - Current timestamp is 2026-09-10T15:30:00
- **Test Steps**:
  1. Calculate timestamp 1 minute from now
  2. Send PUT request to `/events/125` with proposed_date=now+1min
  3. Verify request succeeds
- **Test Data**: proposed_date = current timestamp + 1 minute
- **Expected Result**:
  - HTTP 200 OK
  - Event proposed_date updated successfully
  - Change logged as important

---

## 5. ADDITIONAL EDGE CASES

### TC-US5.2-028: No Changes Made (Idempotent Save)
- **Test Scenario**: Coordinator "saves" event without changing any fields
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists with id=126 and specific field values
- **Test Steps**:
  1. Retrieve current event state
  2. Send PUT request with identical field values
  3. Verify response and check if changes are logged
- **Test Data**: Exact same values as current event state
- **Expected Result**:
  - HTTP 200 OK
  - Event remains unchanged
  - No entries added to event_changes table (no actual changes detected)

### TC-US5.2-029: Null/Empty Optional Fields
- **Test Scenario**: Coordinator sets optional fields (purpose, description, expected_attendance) to null/empty
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in DRAFT status with id=127
- **Test Steps**:
  1. Send PUT request to `/events/127` with null purpose, empty description, null expected_attendance
  2. Verify request succeeds
- **Test Data**:
  ```json
  {
    "name": "Workshop",
    "purpose": null,
    "description": "",
    "proposed_date": "2026-10-15T14:00:00",
    "expected_attendance": null
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Fields updated to null/empty values
  - Changes logged appropriately

### TC-US5.2-030: Coordinator Edits Event in SUBMITTED Status
- **Test Scenario**: Verify coordinator can edit events in SUBMITTED status (Sprint 1 reachable)
- **Pre-conditions**:
  - User is logged in as Coordinator
  - Event exists in SUBMITTED status with id=128
- **Test Steps**:
  1. Send PUT request to `/events/128` updating name
  2. Verify request succeeds
- **Test Data**: Any valid update
- **Expected Result**:
  - HTTP 200 OK
  - Event updated successfully
  - Change logged
  - Event status remains SUBMITTED (edit does not change status)

---

## Summary

**Total Test Cases**: 30

**Breakdown**:
- Happy Path: 6 test cases
- Cross-cutting Quality: 3 test cases
- Negative Testing: 8 test cases
- Boundary Testing: 10 test cases
- Additional Edge Cases: 3 test cases

**Key Coverage Areas**:
1. ✅ All editable fields (name, purpose, description, proposed_date, expected_attendance)
2. ✅ Important vs routine change classification
3. ✅ Authorization (coordinator permission check)
4. ✅ Authentication (anonymous rejection)
5. ✅ Audit trail completeness
6. ✅ Input validation (required fields, data types, constraints)
7. ✅ Boundary conditions (field length limits, min/max values)
8. ✅ Error handling (invalid IDs, past dates, negative numbers)
9. ✅ Edge cases (no changes, null values, different event statuses)

**Decisions Needed** (to clarify before implementation):
1. Is expected_attendance=0 valid?
2. Can proposed_date be set to current timestamp, or must it be in the future?
3. Should coordinator edits be allowed on events in statuses beyond SUBMITTED?
