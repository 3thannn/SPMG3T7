# Playwright E2E Testing - Quick Start Guide

## What I've Set Up For You

I've configured Playwright end-to-end testing for your application. Here's everything that's been added:

### Files Created

1. **`playwright.config.ts`** - Configuration for Playwright
2. **`e2e/helpers.ts`** - Reusable test helper functions
3. **`e2e/authentication.spec.ts`** - Tests for sign in/out and roles
4. **`e2e/coordinator-lead-assignment.spec.ts`** - Tests for your new features
5. **`E2E_TESTING.md`** - Complete documentation
6. **`.gitignore`** - Updated to ignore Playwright artifacts

### NPM Scripts Added

I added these commands to `package.json`:

- `npm run test:e2e` - Run all E2E tests
- `npm run test:e2e:ui` - Run with interactive UI (BEST for development!)
- `npm run test:e2e:headed` - Run with visible browser
- `npm run test:e2e:report` - View test results

## How to Run Tests (3 Easy Steps!)

### Step 1: Make sure backend is running
```bash
# In the backend directory
cd ../backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Step 2: Run the E2E tests
```bash
# In the frontend directory
cd frontend
npm run test:e2e:ui
```

### Step 3: Watch the magic! ✨
The Playwright UI will open and you can:
- Click on any test to run it
- Watch it execute in the browser
- See screenshots if tests fail
- Debug step-by-step

## What Tests Are Included

### Authentication Tests (13 tests)
- ✅ Sign in with valid/invalid credentials
- ✅ Sign out functionality
- ✅ Role-based routing (each role goes to their home page)
- ✅ Access control (who can access what)
- ✅ Session persistence

### Coordinator Lead Assignment Tests (9 tests)
- ✅ Coordinator Lead can access unassigned queue
- ✅ Search and filter events
- ✅ Assign coordinators to events
- ✅ Complete flow: Create → Submit → Assign
- ✅ Access restrictions for other roles
- ✅ Navigation between pages

## What is E2E Testing?

**Simple explanation**: E2E tests open a real browser and interact with your app just like a real user would.

**Why it's useful**:
- Tests the whole application working together
- Catches bugs that unit tests miss
- Verifies user journeys actually work
- Gives you confidence before deploying

## How Tests Work

1. **Playwright opens a browser** (Chrome in this case)
2. **Navigates to your app** (localhost:5173)
3. **Simulates user actions** (clicking, typing, etc.)
4. **Checks results** (is the right thing displayed?)
5. **Reports pass/fail** (with screenshots of failures)

## Example Test Explained

```typescript
test('User can sign in', async ({ page }) => {
  // 1. Go to sign in page
  await page.goto('/#/signin')

  // 2. Fill in email
  await page.getByLabel('Email address').fill('dylan@spmg3t7.edu')

  // 3. Fill in password
  await page.getByLabel('Password').fill('Sprint1!demo')

  // 4. Click sign in button
  await page.getByRole('button', { name: 'Sign in' }).click()

  // 5. Verify we're signed in (check user name appears)
  await expect(page.getByText('Dylan')).toBeVisible()
})
```

## Troubleshooting

### Backend not running?
Tests will fail with timeout errors. Make sure backend is running on port 8000.

### Tests failing?
1. Run with UI mode: `npm run test:e2e:ui`
2. Click the failing test
3. See exactly where it fails
4. Check the screenshot

### Need help?
Read the full documentation in `E2E_TESTING.md`

## What's Next?

You can:
1. **Run the tests** to see them in action
2. **Modify existing tests** to match your requirements
3. **Add new tests** for other features
4. **Run in CI** - tests work in GitHub Actions too!

## Quick Tips

- Use `test:e2e:ui` during development (easiest to debug)
- Use `test:e2e` in CI/CD (runs headless)
- Tests are independent - run them in any order
- Each test signs in fresh - no state carried over

---

**Have fun testing! If you need help writing more tests, just ask!** 🎭
