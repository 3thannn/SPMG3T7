import { test, expect } from '@playwright/test'
import { signIn, signOut, waitForBackend, TEST_USERS } from './helpers'

/**
 * E2E tests for Authentication flows (US1.1, US1.2, US1.3)
 *
 * These tests cover:
 * - US1.1: Sign in and session management
 * - US1.2: Sign out
 * - US1.3: Role-based access control
 */

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await waitForBackend(page)
  })

  test('US1.1: User can sign in with valid credentials', async ({ page }) => {
    await page.goto('/#/signin')

    // Fill in credentials
    await page.getByLabel('Email').fill(TEST_USERS['Event Organiser'].email)
    await page.getByLabel('Password').fill(TEST_USERS['Event Organiser'].password)

    // Sign in
    await page.locator('form').getByRole('button', { name: 'Sign in' }).click()

    // Should be redirected and see user name in TopNav
    await expect(page.locator('.topnav-name')).toHaveText(TEST_USERS['Event Organiser'].name)

    // Should see role in header
    await expect(page.locator('.topnav-role')).toHaveText('Event Organiser')
  })

  test('US1.1: Invalid password shows error', async ({ page }) => {
    await page.goto('/#/signin')

    await page.getByLabel('Email').fill(TEST_USERS['Event Organiser'].email)
    await page.getByLabel('Password').fill('WrongPassword123!')

    await page.locator('form').getByRole('button', { name: 'Sign in' }).click()

    // Should see error message
    await expect(page.getByText(/incorrect|invalid|wrong/i)).toBeVisible()

    // Should still be on sign in page
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('US1.1: Unknown email shows error', async ({ page }) => {
    await page.goto('/#/signin')

    await page.getByLabel('Email').fill('nonexistent@example.com')
    await page.getByLabel('Password').fill('SomePassword123!')

    await page.locator('form').getByRole('button', { name: 'Sign in' }).click()

    // Should see error message
    await expect(page.getByText(/incorrect|invalid|wrong/i)).toBeVisible()
  })

  test('US1.2: User can sign out', async ({ page }) => {
    await signIn(page, 'Event Organiser')

    // Verify signed in (name is in TopNav)
    await expect(page.locator('.topnav-name')).toHaveText(TEST_USERS['Event Organiser'].name)

    // Sign out
    await signOut(page)

    // Should be on landing page with "Sign in" button visible in header
    await expect(page.getByRole('banner').getByRole('button', { name: 'Sign in' })).toBeVisible()

    // Should not see user name anymore
    await expect(page.locator('.topnav-name')).not.toBeVisible()
  })

  test('US1.2: After sign out, protected pages require re-authentication', async ({ page }) => {
    await signIn(page, 'Event Organiser')

    // Sign out
    await signOut(page)

    // Try to access protected page
    await page.goto('/#/events')

    // Should be redirected to sign in
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('US1.3: Each role is routed to their correct home page', async ({ page }) => {
    // Test Organiser
    await signIn(page, 'Event Organiser')
    await expect(page).toHaveURL(/#\/events/)
    await signOut(page)

    // Test Coordinator
    await signIn(page, 'Event Coordinator')
    await expect(page).toHaveURL(/#\/events/)
    await signOut(page)

    // Test Coordinator Lead
    await signIn(page, 'Event Coordinator Lead')
    await expect(page).toHaveURL(/#\/unassigned-queue/)
    await signOut(page)

    // Test Safety Officer
    await signIn(page, 'Safety Officer')
    await expect(page).toHaveURL(/#\/safety-review/)
    await signOut(page)

    // Test Venue Staff
    await signIn(page, 'Venue Staff')
    await expect(page).toHaveURL(/#\/venues/)
  })

  test('US1.3: Organiser cannot create venue', async ({ page }) => {
    await signIn(page, 'Event Organiser')

    // Try to access venue creation page
    await page.goto('/#/venues/new')

    // Should see access denied
    await expect(page.getByText('Access denied')).toBeVisible()
    await expect(page.getByText(/cannot open/i)).toBeVisible()
  })

  test('US1.3: Coordinator cannot create events', async ({ page }) => {
    await signIn(page, 'Event Coordinator')

    // Try to access event creation page
    await page.goto('/#/events/new')

    // Should see access denied
    await expect(page.getByText('Access denied')).toBeVisible()
    await expect(page.getByText(/Event Coordinator role cannot open creating an event/i)).toBeVisible()
  })

  test('US1.3: Venue Staff can create venues', async ({ page }) => {
    await signIn(page, 'Venue Staff')

    // Navigate to venues
    await page.getByRole('link', { name: 'Venues' }).click()

    // Should see "Add venue" button
    const addButton = page.getByRole('button', { name: 'Add venue' })
    await expect(addButton).toBeVisible()

    // Click to open form
    await addButton.click()

    // Should see venue form heading "Add a venue"
    await expect(page.getByRole('heading', { name: 'Add a venue' })).toBeVisible()
  })

  test('Session persistence: Refreshing page keeps user signed in', async ({ page }) => {
    await signIn(page, 'Event Organiser')

    // Verify signed in
    await expect(page.locator('.topnav-name')).toHaveText(TEST_USERS['Event Organiser'].name)

    // Reload page
    await page.reload()

    // Should still be signed in
    await expect(page.locator('.topnav-name')).toHaveText(TEST_USERS['Event Organiser'].name)
    await expect(page.locator('.topnav-role')).toHaveText('Event Organiser')
  })

  test('Navigation links are role-appropriate', async ({ page }) => {
    // Organiser should see Create link
    await signIn(page, 'Event Organiser')
    await expect(page.getByRole('link', { name: 'Create' })).toBeVisible()
    await signOut(page)

    // Coordinator should NOT see Create link
    await signIn(page, 'Event Coordinator')
    await expect(page.getByRole('link', { name: 'Create' })).not.toBeVisible()
    await signOut(page)

    // Coordinator Lead should see Unassigned Queue link
    await signIn(page, 'Event Coordinator Lead')
    await expect(page.getByRole('link', { name: 'Unassigned Queue' })).toBeVisible()
  })
})
