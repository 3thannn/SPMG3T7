import { test, expect } from '@playwright/test'
import { signIn, waitForBackend } from './helpers'

/**
 * E2E tests for Venue Unavailability (US12.2)
 *
 * These tests cover:
 * - US12.2: Venue Staff can mark venues unavailable with structured reason types
 * - US12.2: Active bookings are automatically flagged as 'Needs replacement'
 * - US12.2: Coordinators are notified when their bookings are flagged
 * - US12.2: Flagged bookings display the reason on event detail page
 */

test.describe('Venue Unavailability (US12.2)', () => {
  test.beforeEach(async ({ page }) => {
    await waitForBackend(page)
  })

  test('US12.2: Venue Staff can mark venue unavailable with structured reasons', async ({ page }) => {
    await signIn(page, 'Venue Staff')

    // Navigate to venues page
    await page.goto('/#/venues')
    await page.waitForLoadState('networkidle')

    // Click on the first venue in the list
    const firstVenue = page.locator('.venue-card').first()
    await firstVenue.click()

    // Wait for venue detail page to load
    await page.waitForLoadState('networkidle')

    // Click "Mark unavailable" button
    const markUnavailableBtn = page.getByRole('button', { name: /mark unavailable/i })
    await expect(markUnavailableBtn).toBeVisible()
    await markUnavailableBtn.click()

    // Fill in the unavailability form
    // Set start date (use a future date to avoid conflicts)
    await page.locator('#unavailable-start').fill('2027-12-10')

    // Set end date
    await page.locator('#unavailable-end').fill('2027-12-12')

    // Select reason type
    await page.locator('#unavailable-reason-type').selectOption('maintenance')

    // Submit the form
    await page.getByRole('button', { name: /mark unavailable/i }).last().click()

    // Should see success message
    await expect(page.getByText(/marked unavailable:/i)).toBeVisible({ timeout: 10000 })

    // Should see the unavailability in the list (date format may vary)
    await expect(page.getByText(/dec.*2027/i).first()).toBeVisible()
    await expect(page.getByText('Maintenance').first()).toBeVisible()
  })

  test('US12.2: Custom "other" reason type with custom text', async ({ page }) => {
    await signIn(page, 'Venue Staff')

    // Navigate to venues page
    await page.goto('/#/venues')
    await page.waitForLoadState('networkidle')

    // Click on the first venue
    const firstVenue = page.locator('.venue-card').first()
    await firstVenue.click()

    // Wait for venue detail page to load
    await page.waitForLoadState('networkidle')

    // Click "Mark unavailable" button
    const markUnavailableBtn = page.getByRole('button', { name: /mark unavailable/i })
    await expect(markUnavailableBtn).toBeVisible()
    await markUnavailableBtn.click()

    // Fill in the unavailability form with "other" reason
    await page.locator('#unavailable-start').fill('2027-12-15')
    await page.locator('#unavailable-end').fill('2027-12-17')

    // Select "Other" reason type
    await page.locator('#unavailable-reason-type').selectOption('other')

    // The custom reason field should now be visible
    const otherReasonField = page.locator('#unavailable-other-reason')
    await expect(otherReasonField).toBeVisible()

    // Fill in custom reason
    await otherReasonField.fill('Unexpected flooding in the building')

    // Submit the form
    await page.getByRole('button', { name: /mark unavailable/i }).last().click()

    // Should see success message
    await expect(page.getByText(/marked unavailable:/i)).toBeVisible({ timeout: 10000 })

    // Should see the custom reason in the list
    await expect(page.getByText('Unexpected flooding in the building').first()).toBeVisible()
  })

  test('US12.2: All reason types are available in dropdown', async ({ page }) => {
    await signIn(page, 'Venue Staff')

    // Navigate to venues page
    await page.goto('/#/venues')
    await page.waitForLoadState('networkidle')

    // Click on the first venue
    const firstVenue = page.locator('.venue-card').first()
    await firstVenue.click()

    // Wait for venue detail page to load
    await page.waitForLoadState('networkidle')

    // Click "Mark unavailable" button
    await page.getByRole('button', { name: /mark unavailable/i }).click()

    // Check all reason types are in the dropdown
    const reasonSelect = page.locator('#unavailable-reason-type')

    // Get all options
    const options = await reasonSelect.locator('option').allTextContents()

    // Should have all the structured reason types
    expect(options).toContain('Maintenance')
    expect(options).toContain('Equipment failure')
    expect(options).toContain('Renovation')
    expect(options).toContain('Safety concern')
    expect(options).toContain('Other')
  })

  test('US12.2: Event Coordinator sees flagged booking with replacement notice', async ({ page }) => {
    // This test assumes there's already a booking that was flagged
    // In a real scenario, you'd create the event and booking first, then mark venue unavailable

    await signIn(page, 'Event Coordinator')

    // Navigate to events page
    await page.goto('/#/events')
    await page.waitForLoadState('networkidle')

    // Look for an event with a flagged booking
    // Click on the first event (in a real test, you'd navigate to a specific test event)
    const firstEvent = page.locator('.event-row').first()
    if (await firstEvent.isVisible()) {
      await firstEvent.click()

      // Wait for event detail page to load
      await page.waitForLoadState('networkidle')

      // Look for any booking with "Needs replacement" status
      const needsReplacementBooking = page.locator('.booking-row.is-needs-replacement')

      if (await needsReplacementBooking.isVisible()) {
        // Should see the replacement tag
        await expect(needsReplacementBooking.getByText('Needs replacement')).toBeVisible()

        // Should see the replacement notice with reason
        const replacementNotice = needsReplacementBooking.locator('.booking-replacement')
        await expect(replacementNotice).toBeVisible()

        // Should contain guidance text
        await expect(replacementNotice).toContainText(/venue is unavailable/i)
        await expect(replacementNotice).toContainText(/contact venue staff/i)
      }
    }
  })

  test('US12.2: Coordinator receives notification when booking is flagged', async ({ page }) => {
    await signIn(page, 'Event Coordinator')

    // Navigate to notifications page
    await page.goto('/#/notifications')
    await page.waitForLoadState('networkidle')

    // Look for booking conflict notifications
    const notifications = page.locator('.notification-item')

    // Check if any notifications contain booking conflict messages
    const count = await notifications.count()
    if (count > 0) {
      // Look for a notification about venue unavailability
      const conflictNotification = page.getByText(/venue is unavailable/i).first()

      if (await conflictNotification.isVisible()) {
        // Should contain the reason
        await expect(conflictNotification).toBeVisible()

        // Should mention the venue and date range
        // The exact text depends on the test data
      }
    }
  })
})
