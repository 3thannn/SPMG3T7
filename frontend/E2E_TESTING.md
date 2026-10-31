# E2E Testing with Playwright

This document explains how to run and write end-to-end (E2E) tests for the SPMG3T7 frontend using Playwright.

## What is E2E Testing?

End-to-end testing simulates real user interactions with your application in a real browser. Unlike unit tests that test individual components, E2E tests verify that the entire application works together correctly.

## Prerequisites

1. **Backend must be running**: The E2E tests need the backend API to be available
2. **Database must be seeded**: Test users must exist in the database

## Running E2E Tests

### Run all E2E tests (headless mode)
```bash
npm run test:e2e
```

This runs all tests in the background without showing the browser. Perfect for CI/CD.

### Run tests with UI mode (recommended for development)
```bash
npm run test:e2e:ui
```

This opens Playwright's interactive UI where you can:
- See all your tests
- Run individual tests
- Watch tests execute step-by-step
- See screenshots and traces
- Debug failing tests

### Run tests in headed mode (watch the browser)
```bash
npm run test:e2e:headed
```

This runs tests with the browser visible so you can see what's happening.

### View test report
```bash
npm run test:e2e:report
```

After tests run, view the HTML report with screenshots and traces of failed tests.

## Test Structure

### Test Files

E2E tests are located in the `e2e/` directory:

```
frontend/
├── e2e/
│   ├── helpers.ts                          # Shared helper functions
│   ├── authentication.spec.ts              # Authentication flow tests
│   └── coordinator-lead-assignment.spec.ts # Coordinator assignment tests
├── playwright.config.ts                    # Playwright configuration
└── E2E_TESTING.md                         # This documentation
```

### Test Users

The following test users are available (defined in `e2e/helpers.ts`):

| Role                      | Email                  | Password       | Name   |
|--------------------------|------------------------|----------------|--------|
| Event Organiser          | dylan@spmg3t7.edu      | Sprint1!demo   | Dylan  |
| Event Coordinator        | priya@spmg3t7.edu      | Sprint1!demo   | Priya  |
| Event Coordinator Lead   | jordan@spmg3t7.edu     | Sprint1!demo   | Jordan |
| Safety Officer           | sam@spmg3t7.edu        | Sprint1!demo   | Sam    |
| Venue Staff              | alex@spmg3t7.edu       | Sprint1!demo   | Alex   |

## Writing E2E Tests

### Basic Test Structure

```typescript
import { test, expect } from '@playwright/test'
import { signIn, signOut } from './helpers'

test('description of what you are testing', async ({ page }) => {
  // 1. Setup: Sign in as the appropriate user
  await signIn(page, 'Event Organiser')

  // 2. Action: Perform user actions
  await page.getByRole('button', { name: 'Create Event' }).click()
  await page.getByLabel('Title').fill('My Event')

  // 3. Assert: Verify the expected outcome
  await expect(page.getByText('My Event')).toBeVisible()

  // 4. Cleanup: Sign out (optional)
  await signOut(page)
})
```

### Using Helper Functions

#### Sign In
```typescript
await signIn(page, 'Event Coordinator Lead')
```

#### Sign Out
```typescript
await signOut(page)
```

#### Wait for Backend
```typescript
await waitForBackend(page)
```

### Common Playwright Actions

#### Finding Elements

```typescript
// By role (recommended - most accessible)
page.getByRole('button', { name: 'Sign in' })
page.getByRole('heading', { name: 'Events' })
page.getByRole('link', { name: 'Create' })

// By label (for form inputs)
page.getByLabel('Email address')
page.getByLabel('Password')

// By placeholder
page.getByPlaceholder('Search events...')

// By text
page.getByText('Welcome to ConnectSphere')
```

#### Interacting with Elements

```typescript
// Click
await page.getByRole('button', { name: 'Submit' }).click()

// Type text
await page.getByLabel('Title').fill('My Event')

// Check checkbox
await page.getByRole('checkbox', { name: 'Agree' }).check()

// Select dropdown
await page.getByLabel('Status').selectOption('Approved')
```

#### Assertions

```typescript
// Element is visible
await expect(page.getByText('Success')).toBeVisible()

// Element is not visible
await expect(page.getByText('Error')).not.toBeVisible()

// URL matches
await expect(page).toHaveURL(/#\/events/)

// Element has text
await expect(page.getByRole('heading')).toHaveText('Events')

// Input has value
await expect(page.getByLabel('Title')).toHaveValue('My Event')
```

### Navigation

```typescript
// Navigate to a specific URL
await page.goto('/#/events')

// Click a link
await page.getByRole('link', { name: 'Venues' }).click()

// Go back
await page.goBack()

// Reload page
await page.reload()
```

## Test Coverage

### Authentication Tests (`authentication.spec.ts`)

Tests for US1.1, US1.2, US1.3:
- ✅ Sign in with valid credentials
- ✅ Sign in with invalid credentials shows error
- ✅ Sign out works correctly
- ✅ Each role routes to correct home page
- ✅ Role-based access control
- ✅ Session persistence across page reloads

### Coordinator Lead Assignment Tests (`coordinator-lead-assignment.spec.ts`)

Tests for US1.4, US8.2, US8.3, US8.6:
- ✅ Coordinator Lead can sign in and access unassigned queue
- ✅ Safety Officer can sign in and access safety review
- ✅ View unassigned event queue
- ✅ Search functionality in queue
- ✅ Assign coordinator to events
- ✅ Regular coordinator cannot access unassigned queue
- ✅ Full flow: Create event → Submit → Assign
- ✅ Navigation between pages

## Debugging Tests

### When a test fails:

1. **Run with UI mode**: `npm run test:e2e:ui`
   - See exactly which step failed
   - Inspect screenshots
   - View network requests

2. **Run in headed mode**: `npm run test:e2e:headed`
   - Watch the browser execute the test
   - See what the user would see

3. **Check the test report**: `npm run test:e2e:report`
   - View screenshots of failed tests
   - See the full trace of what happened

### Adding Debug Information

```typescript
// Add a pause to inspect the page manually
await page.pause()

// Take a screenshot
await page.screenshot({ path: 'debug.png' })

// Print to console
console.log('Current URL:', page.url())

// Wait for a specific condition
await page.waitForTimeout(1000) // Wait 1 second
```

## Best Practices

1. **Use role-based selectors**: `getByRole` is more reliable than CSS selectors
2. **Wait for elements**: Use `await expect().toBeVisible()` instead of `waitForTimeout`
3. **Keep tests independent**: Each test should work on its own
4. **Clean up after tests**: Sign out at the end if needed
5. **Use descriptive test names**: Make it clear what's being tested
6. **Group related tests**: Use `test.describe()` blocks
7. **Test user journeys**: Test complete flows, not just individual actions

## Continuous Integration

E2E tests will run automatically in CI when:
- You push to a pull request
- Tests run against a clean database
- Results appear in the GitHub Actions tab

## Troubleshooting

### "Target closed" error
- The page was closed unexpectedly
- Check if you're navigating away before assertions complete

### "Timeout waiting for element"
- Element might not exist or takes too long to load
- Increase timeout: `await expect(element).toBeVisible({ timeout: 10000 })`
- Check if you're signed in correctly

### Backend connection issues
- Make sure the backend is running
- Check `playwright.config.ts` for correct `baseURL`

## Learn More

- [Playwright Documentation](https://playwright.dev)
- [Writing Tests](https://playwright.dev/docs/writing-tests)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Locators](https://playwright.dev/docs/locators)
