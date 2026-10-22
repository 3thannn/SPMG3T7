# Test Cases for US8.4: Lead Reassigns an Event

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

## Workflow Visualization

```
Coordinator Lead → View Assigned Event → Click Reassign → Select New Coordinator → Confirm
                                                          ↓
                                        System updates coordinator_id
                                        System logs assignment change
                                                          ↓
                                              Success/Error Response
```

---

## 1. HAPPY PATH TEST CASES

### TC-US8.4-001: Lead Successfully Reassigns Event to Different Coordinator
- **Test Scenario**: Coordinator Lead reassigns an already-assigned event to a different coordinator
- **Pre-conditions**:
  - User is logged in as Coordinator Lead
  - Event exists in SUBMITTED status with id=100
  - Event is currently assigned to Coordinator A (id=2)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Send POST request to `/events/100/reassign` with Coordinator B's ID
  2. Verify response status code
  3. Verify event coordinator_id is updated to Coordinator B
  4. Verify reassignment is logged in event history
- **Test Data**:
  ```json
  {
    "coordinatorId": "10"
  }
  ```
- **Expected Result**:
  - HTTP 200 OK
  - Event coordinator_id updated to 10
  - Event status remains SUBMITTED (reassignment doesn't change status)
  - Assignment change logged in history

### TC-US8.4-002: Reassigned Event Is Visible to New Coordinator
- **Test Scenario**: After reassignment, the new coordinator can access the event
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Lead reassigns event from Coordinator A to Coordinator B
  2. Sign in as Coordinator B
  3. Attempt to GET the event
  4. Verify Coordinator B can view the event
- **Expected Result**:
  - HTTP 200 OK when Coordinator B retrieves event
  - Event details returned successfully

### TC-US8.4-003: Reassigned Event Is No Longer Visible to Previous Coordinator
- **Test Scenario**: After reassignment, the previous coordinator loses access
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Lead reassigns event from Coordinator A to Coordinator B
  2. Sign in as Coordinator A (previous coordinator)
  3. Attempt to GET the event
  4. Verify Coordinator A cannot view the event (404)
- **Expected Result**:
  - HTTP 404 Not Found when Coordinator A retrieves event
  - Coordinator A no longer has access

### TC-US8.4-004: Lead Can Reassign Event Multiple Times
- **Test Scenario**: A coordinator lead can reassign the same event to different coordinators sequentially
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - Coordinators B (id=10) and C (id=11) exist
- **Test Steps**:
  1. Lead reassigns event from A to B
  2. Lead reassigns event from B to C
  3. Verify final assignment is to Coordinator C
- **Expected Result**:
  - Both reassignments succeed (HTTP 200)
  - Event coordinator_id is 11 (Coordinator C)
  - Both reassignments are logged in history

### TC-US8.4-005: Reassignment Works for Events at Different Statuses
- **Test Scenario**: Lead can reassign events that are not just Submitted (e.g., Under Review, Approved)
- **Pre-conditions**:
  - Event exists in UNDER_REVIEW status, assigned to Coordinator A
  - Coordinator B exists
- **Test Steps**:
  1. Lead reassigns the Under Review event to Coordinator B
  2. Verify reassignment succeeds
- **Expected Result**:
  - HTTP 200 OK
  - Event coordinator_id updated to Coordinator B
  - Event status remains UNDER_REVIEW

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-US8.4-006: Only Coordinator Lead Can Reassign
- **Test Scenario**: Verify only users with COORDINATORS_ASSIGN permission can reassign
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - User is logged in as Coordinator Lead
- **Test Steps**:
  1. Verify Coordinator Lead has COORDINATORS_ASSIGN permission
  2. Send POST request to `/events/100/reassign`
  3. Verify request succeeds
- **Expected Result**:
  - HTTP 200 OK
  - Permission check passes
  - Event reassigned successfully

### TC-US8.4-007: Reassignment Audit Trail
- **Test Scenario**: Verify reassignment is captured in event history with correct metadata
- **Pre-conditions**:
  - Lead user has id=3
  - Event is assigned to Coordinator A (id=2)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Lead (id=3) reassigns event from Coordinator A to Coordinator B
  2. Retrieve event and check history
  3. Verify history contains assignment change
- **Expected Result**:
  - History shows coordinator_id changed from 2 to 10
  - Change attributed to Lead (user id=3)
  - Timestamp recorded

### TC-US8.4-008: Reassignment Doesn't Change Event Status
- **Test Scenario**: Reassigning an event doesn't alter its workflow status
- **Pre-conditions**:
  - Event exists in APPROVED status, assigned to Coordinator A
  - Coordinator B exists
- **Test Steps**:
  1. Note event status (APPROVED)
  2. Lead reassigns event to Coordinator B
  3. Verify event status is still APPROVED
- **Expected Result**:
  - Event status remains APPROVED before and after reassignment
  - Only coordinator_id changes

---

## 3. NEGATIVE TEST CASES

### TC-US8.4-009: Regular Coordinator Cannot Reassign
- **Test Scenario**: A regular coordinator cannot reassign events
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - User is logged in as regular Coordinator (not Lead)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Attempt to reassign event as regular Coordinator
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 403 Forbidden
  - Error message: "You do not have permission to assign coordinators"
  - Event assignment unchanged

### TC-US8.4-010: Event Organiser Cannot Reassign
- **Test Scenario**: Event owner/organiser cannot reassign coordinators
- **Pre-conditions**:
  - Event is owned by Organiser (id=1)
  - Event is assigned to Coordinator A (id=2)
  - User is logged in as the Organiser
- **Test Steps**:
  1. Attempt to reassign event as Organiser
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 403 Forbidden
  - Event assignment unchanged

### TC-US8.4-011: Cannot Reassign to Non-Existent Coordinator
- **Test Scenario**: Reassigning to a user ID that doesn't exist is rejected
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - User id=9999 does not exist
- **Test Steps**:
  1. Attempt to reassign event to user id=9999
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 400 Bad Request
  - Error message: "That coordinator does not exist"
  - Event assignment unchanged

### TC-US8.4-012: Cannot Reassign to Non-Coordinator Role
- **Test Scenario**: Reassigning to a user who is not a Coordinator is rejected
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
  - Venue Staff user exists (id=100, role=VENUE_STAFF)
- **Test Steps**:
  1. Attempt to reassign event to Venue Staff user
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 400 Bad Request
  - Error message: "That user is not a Coordinator"
  - Event assignment unchanged

### TC-US8.4-013: Cannot Reassign Unassigned Event
- **Test Scenario**: Attempting to reassign an event that has no coordinator is rejected
- **Pre-conditions**:
  - Event exists in SUBMITTED status with id=100
  - Event has coordinator_id = null (unassigned)
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Attempt to POST to `/events/100/reassign`
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 409 Conflict
  - Error message: "This event is not assigned to any coordinator. Use /assign instead."
  - Event remains unassigned

### TC-US8.4-014: Cannot Reassign Non-Existent Event
- **Test Scenario**: Attempting to reassign an event that doesn't exist
- **Pre-conditions**:
  - Event with id=999999 does NOT exist
  - Coordinator B exists (id=10)
- **Test Steps**:
  1. Send POST request to `/events/999999/reassign`
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 404 Not Found
  - Error message: "That event no longer exists"

### TC-US8.4-015: Missing Coordinator ID in Payload
- **Test Scenario**: Reassignment request without coordinatorId is rejected
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
- **Test Steps**:
  1. Send POST request to `/events/100/reassign` with empty payload `{}`
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 422 Unprocessable Entity (Pydantic validation error)
  - Error indicates coordinatorId is required

### TC-US8.4-016: Cannot Reassign to Same Coordinator (Idempotent Check)
- **Test Scenario**: Reassigning to the currently assigned coordinator is handled gracefully
- **Pre-conditions**:
  - Event is assigned to Coordinator A (id=2)
- **Test Steps**:
  1. Attempt to reassign event to Coordinator A (same coordinator)
  2. Verify behavior (either succeeds silently or gives helpful message)
- **Expected Result**:
  - Option A: HTTP 200 OK (idempotent, no actual change)
  - Option B: HTTP 400 Bad Request with message "This event is already assigned to that coordinator"
  - No duplicate history entry if Option A

---

## 4. BOUNDARY TEST CASES

### TC-US8.4-017: Reassign Event in Draft Status
- **Test Scenario**: Verify behavior when trying to reassign a Draft event
- **Pre-conditions**:
  - Event exists in DRAFT status
  - Event is owned by Organiser (no coordinator assigned)
- **Test Steps**:
  1. Attempt to reassign the Draft event
  2. Verify expected behavior
- **Expected Result**:
  - HTTP 409 Conflict (Draft events aren't assigned to coordinators)
  - Error message: "Only submitted events can be assigned to coordinators"

### TC-US8.4-018: Reassign Event in Rejected Status
- **Test Scenario**: Verify reassignment works for events in terminal states like Rejected
- **Pre-conditions**:
  - Event is in REJECTED status, assigned to Coordinator A
  - Coordinator B exists
- **Test Steps**:
  1. Attempt to reassign the Rejected event to Coordinator B
  2. Verify reassignment succeeds or fails appropriately
- **Expected Result**:
  - HTTP 200 OK (even rejected events might need coordinator reassignment for cleanup)
  - Event coordinator_id updated to Coordinator B

### TC-US8.4-019: Reassign with Invalid Coordinator ID Format
- **Test Scenario**: Providing a non-numeric coordinator ID is rejected
- **Pre-conditions**:
  - Event is assigned to Coordinator A
- **Test Steps**:
  1. Send reassignment request with coordinatorId="abc"
  2. Verify request is rejected
- **Expected Result**:
  - HTTP 400 Bad Request
  - Error message: "The coordinator ID must be a valid number"

---

## 5. ADDITIONAL EDGE CASES

### TC-US8.4-020: Reassignment After Event Status Changes
- **Test Scenario**: Ensure reassignment works correctly after event transitions through workflow
- **Pre-conditions**:
  - Event is Submitted and assigned to Coordinator A
  - Coordinator A moves event to Under Review
  - Coordinator B exists
- **Test Steps**:
  1. Lead reassigns the Under Review event to Coordinator B
  2. Verify Coordinator B can now review/decide the event
  3. Verify Coordinator A loses access
- **Expected Result**:
  - Reassignment succeeds (HTTP 200)
  - Coordinator B can review/approve/reject the event
  - Coordinator A cannot access it (404)

### TC-US8.4-021: Concurrent Reassignment Attempts
- **Test Scenario**: Two leads attempt to reassign the same event simultaneously
- **Pre-conditions**:
  - Event is assigned to Coordinator A
  - Two Coordinator Lead users logged in
  - Coordinators B and C exist
- **Test Steps**:
  1. Lead 1 reassigns to Coordinator B
  2. Lead 2 (simultaneously) reassigns to Coordinator C
  3. Verify final state
- **Expected Result**:
  - Both requests succeed (last write wins)
  - Event is assigned to whoever's request completed last
  - Both reassignments logged in history

---

## Summary

**Total Test Cases**: 21

**Breakdown**:
- Happy Path: 5 test cases
- Cross-cutting Quality: 3 test cases
- Negative Testing: 8 test cases
- Boundary Testing: 3 test cases
- Additional Edge Cases: 2 test cases

**Key Coverage Areas**:
1. ✅ Basic reassignment functionality
2. ✅ Access control (new coordinator gains access, old loses access)
3. ✅ Authorization (only Lead can reassign)
4. ✅ Audit trail (history tracking)
5. ✅ Status preservation (reassignment doesn't change event status)
6. ✅ Validation (coordinator exists, is a Coordinator role, etc.)
7. ✅ Error handling (non-existent events/coordinators, wrong roles, unassigned events)
8. ✅ Edge cases (multiple reassignments, different event statuses, concurrent access)

**Implementation Notes**:
1. **New Endpoint**: Create `POST /events/{event_id}/reassign` (separate from `/assign`)
   - Alternative: Modify existing `/assign` endpoint to allow reassignment
2. **Key Difference from US8.3**: Remove the "already assigned" check, allow changing coordinator_id
3. **History Tracking**: Log both old and new coordinator IDs in the change record
4. **RLS Consideration**: Ensure Supabase RLS policies allow the new coordinator to see the event
