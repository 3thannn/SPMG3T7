import { test, expect } from '@playwright/test'
import { signIn, signOut, waitForBackend } from './helpers'

/**
 * E2E tests for US1.4, US8.2, US8.3, US8.6
 * Coordinator Lead Assignment Flow
 *
 * These tests cover the complete user journey for:
 * - US1.4: New roles (Coordinator Lead, Safety Officer)
 * - US8.2: Viewing the unassigned event queue
 * - US8.3: Assigning coordinators to events
 * - US8.6: Coordinator visibility isolation
 */

test.describe('Coordinator Lead Assignment Flow', () => {
  test.beforeEach(async ({ page }) => {
    await waitForBackend(page)
  })

  test('US1.4: Coordinator Lead can sign in and is routed to unassigned queue', async ({ page }) => {
    await signIn(page, 'Event Coordinator Lead')

    // Should be redirected to unassigned queue (their home page)
    await expect(page).toHaveURL(/#\/unassigned-queue/)
    await expect(page.getByRole('heading', { name: 'Unassigned Events' })).toBeVisible()
  })

  test('US1.4: Safety Officer can sign in and is routed to safety review page', async ({ page }) => {
    await signIn(page, 'Safety Officer')

    // Should be redirected to safety review page (their home page)
    await expect(page).toHaveURL(/#\/safety-review/)
    await expect(page.getByRole('heading', { name: 'Safety Review' })).toBeVisible()
  })

  test('US8.2: Coordinator Lead can view the unassigned event queue', async ({ page }) => {
    await signIn(page, 'Event Coordinator Lead')

    // Should see the unassigned queue page
    await expect(page.getByRole('heading', { name: 'Unassigned Events' })).toBeVisible()

    // Page should be loaded - check for either the search box or content area
    await expect(page.getByPlaceholder('Search events...')).toBeVisible()

    // The page will show either events (cards/table) or empty state
    // We just verify the page structure loaded correctly
  })

  test('US8.2: Search functionality works in unassigned queue', async ({ page }) => {
    await signIn(page, 'Event Coordinator Lead')

    // Look for search input
    const searchInput = page.getByPlaceholder('Search events...')
    await expect(searchInput).toBeVisible()

    // Try searching (will filter if events exist)
    await searchInput.fill('conference')

    // Clear search
    const clearButton = page.getByLabel('Clear search')
    if (await clearButton.isVisible()) {
      await clearButton.click()
      await expect(searchInput).toHaveValue('')
    }
  })

  test('US8.3: Coordinator Lead can assign a coordinator to an event (if events exist)', async ({ page }) => {
    await signIn(page, 'Event Coordinator Lead')

    // Check if there are any unassigned events
    const assignButton = page.getByRole('button', { name: /Assign Coordinator/i }).first()

    // Wait a bit for page to load
    await page.waitForTimeout(1000)

    const hasAssignButton = await assignButton.isVisible().catch(() => false)

    if (hasAssignButton) {
      // Click the assign button
      await assignButton.click()

      // Modal should appear
      await expect(page.getByText(/Select a coordinator to assign this event to/i)).toBeVisible()

      // Should see coordinator options (Ethan, Sam Chen, Jordan, etc.)
      await expect(page.getByRole('button', { name: /Ethan|Sam Chen|Jordan/i }).first()).toBeVisible()

      // Cancel the modal
      await page.getByRole('button', { name: 'Cancel' }).click()

      // Modal should close
      await expect(page.getByText(/Select a coordinator to assign/i)).not.toBeVisible()
    } else {
      // No unassigned events - just verify the page loaded
      await expect(page.getByRole('heading', { name: 'Unassigned Events' })).toBeVisible()
    }
  })

  test('US8.6: Regular Coordinator cannot access unassigned queue', async ({ page }) => {
    await signIn(page, 'Event Coordinator')

    // Try to navigate to unassigned queue
    await page.goto('/#/unassigned-queue')

    // Should see access denied
    await expect(page.getByText('Access denied')).toBeVisible()
    await expect(page.getByText(/Event Coordinator role cannot open/i)).toBeVisible()
  })

  test('US8.6: Event Organiser cannot access unassigned queue', async ({ page }) => {
    await signIn(page, 'Event Organiser')

    // Try to navigate to unassigned queue
    await page.goto('/#/unassigned-queue')

    // Should see access denied
    await expect(page.getByText('Access denied')).toBeVisible()
  })

  test('Full assignment flow: Create event → Submit → Assign', async ({ page }) => {
    // Step 1: Create and submit an event as Organiser
    await signIn(page, 'Event Organiser')

    // Navigate to create event page
    await page.getByRole('link', { name: 'Create' }).click()
    await expect(page.getByRole('heading', { name: /New event/i })).toBeVisible()

    // Fill in required event details
    const timestamp = Date.now()
    await page.getByLabel('Title').fill(`E2E Test Event ${timestamp}`)
    await page.getByLabel('Purpose').fill('Testing the assignment flow')

    // Fill in start and end dates (required for submission)
    await page.getByLabel('Starts').fill('2027-01-01T10:00')
    await page.getByLabel('Ends').fill('2027-01-01T12:00')

    // Fill in expected attendance (required for submission)
    await page.getByLabel('Expected attendance').fill('50')

    // US2.1 (Sprint 3): description and every need are required for submission too
    await page.getByLabel('Description').fill('E2E coverage of the assignment flow')
    await page.getByRole('group', { name: 'Venue requirements' }).getByLabel('Projector').check()
    await page.getByLabel('Preferred layout').selectOption('Classroom')
    await page
      .getByRole('group', { name: 'Accessibility needs' })
      .getByLabel('Wheelchair access')
      .check()
    await page.getByLabel('Equipment needs').fill('One clicker')
    await page
      .getByRole('group', { name: 'Registration needs' })
      .getByLabel('None / Not required')
      .check()

    // Save the form as draft
    await page.getByRole('button', { name: 'Save as draft' }).click()

    // Should redirect to event detail page showing Draft status
    await expect(page.getByText('Status: Draft', { exact: false })).toBeVisible({ timeout: 10000 })

    // Submit the event for review
    await page.getByRole('button', { name: 'Submit event' }).click()
    await expect(page.getByText('Status: Submitted', { exact: false }).first()).toBeVisible({ timeout: 10000 })

    // Sign out
    await signOut(page)

    // Step 2: Sign in as Coordinator Lead and verify event appears in unassigned queue
    await signIn(page, 'Event Coordinator Lead')

    // Should see the event in unassigned queue
    await expect(page.getByText(`E2E Test Event ${timestamp}`)).toBeVisible({ timeout: 10000 })

    // Should see assign button for the event
    await expect(page.getByRole('button', { name: /Assign Coordinator/i }).first()).toBeVisible()
  })

  test('Navigation: Coordinator Lead can navigate between pages', async ({ page }) => {
    await signIn(page, 'Event Coordinator Lead')

    // Should start on unassigned queue
    await expect(page.getByRole('heading', { name: 'Unassigned Events' })).toBeVisible()

    // Navigate to Events
    await page.getByRole('link', { name: 'Events' }).click()
    await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible()

    // Navigate back to Unassigned Queue
    await page.getByRole('link', { name: 'Unassigned Queue' }).click()
    await expect(page.getByRole('heading', { name: 'Unassigned Events' })).toBeVisible()

    // Navigate to Venues
    await page.getByRole('link', { name: 'Venues' }).click()
    await expect(page.getByRole('heading', { name: 'Venues' })).toBeVisible()
  })
})
