import { test, expect, type Page } from '@playwright/test'

/**
 * US9.5: block deleting a venue that has future bookings.
 *
 * Runs against `backend/e2e_server.py`, never the shared database; see
 * playwright.isolated.config.ts. Its seed has one venue per case:
 *
 *   1 Great Hall      two bookings still to come
 *   2 Bertha Room     one booking that has ended, one cancelled
 *   3 Seminar Room 4  never booked
 *   4 Flagged Room    flagged Needs replacement, still to come
 */


async function tryToDelete(page: Page, venueId: string, name: string) {
  await page.goto(`/#/venues/${venueId}`)
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
  await page.getByRole('button', { name: 'Delete venue' }).click()
  await page.getByRole('button', { name: 'Yes, delete it' }).click()
}

async function expectInCatalogue(page: Page, name: string, present: boolean) {
  await page.goto('/#/venues')
  await expect(page.getByRole('heading', { level: 1, name: 'Venues' })).toBeVisible()
  // No spec deletes the Great Hall, so once it shows, the catalogue has loaded.
  await expect(page.getByText('Great Hall', { exact: true })).toBeVisible()
  await expect(page.getByText(name, { exact: true })).toHaveCount(present ? 1 : 0)
}

test.describe('AC1: a venue with future bookings cannot be deleted', () => {
  test('staff are told to mark it unavailable instead, and the venue stays', async ({ page }) => {
    await tryToDelete(page, '1', 'Great Hall')

    await expect(page.getByRole('alert')).toHaveText(
      'Great Hall has 2 future bookings, so it cannot be deleted. Mark it unavailable ' +
        'instead, so the affected bookings are flagged for a replacement venue.',
    )
    await expect(page.getByRole('heading', { level: 1, name: 'Great Hall' })).toBeVisible()
    await expectInCatalogue(page, 'Great Hall', true)
  })
})
