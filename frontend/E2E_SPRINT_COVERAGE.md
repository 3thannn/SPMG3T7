# E2E Test Coverage

## Summary

**Total: 20 E2E tests covering 7 User Stories**

These E2E tests cover Sprint 3 User Stories: US1.4, US8.2, US8.3, US8.6 (Coordinator Lead features)

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
- `e2e/helpers.ts` - Test utilities (signIn, signOut, test users)
