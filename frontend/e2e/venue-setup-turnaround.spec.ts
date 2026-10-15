import { test, expect, type Browser, type Page } from '@playwright/test'
import { signIn, signOut, waitForBackend, TEST_USERS } from './helpers'

/**
 * E2E tests for US9.4: set venue setup and turnaround time.
 *
 * These cover the user journeys for each acceptance criterion. The value rules
 * and boundaries (0, 1440, negatives, decimals, text) and the clash arithmetic
 * are unit tested in venueTurnaround.test.ts, VenueFormPage.test.tsx and
 * backend/tests/test_venue_turnaround.py.
 *
 * Venue and event names are unique, so the tests can run against a shared
 * database. Venues without bookings are deleted at the end of each test.
 */

let counter = 0

function uniqueName(label: string): string {
  counter += 1
  return `E2E US9.4 ${label} ${Date.now()}-${counter}`
}

/** The value shown next to a label in a venue's details. */
function detail(page: Page, label: string) {
  return page
    .locator('dt')
    .filter({ hasText: new RegExp(`^${label}$`) })
    .locator('xpath=following-sibling::dd[1]')
}

/** As Venue Staff, add a venue and return its id. */
async function addVenue(page: Page, name: string, setup?: string, turnaround?: string) {
  await page.goto('/#/venues/new')
  await page.getByLabel('Name').fill(name)
  await page.getByLabel('Location').fill('E2E Building, Level 1')
  await page.getByLabel('Capacity').fill('200')
  if (setup !== undefined) await page.getByLabel('Setup time (minutes)').fill(setup)
  if (turnaround !== undefined) {
    await page.getByLabel('Turnaround time (minutes)').fill(turnaround)
  }
  await page.getByRole('button', { name: 'Add venue' }).click()
  await expect(page.getByRole('heading', { name })).toBeVisible({ timeout: 10000 })
  return /#\/venues\/(\d+)/.exec(page.url())?.[1] ?? ''
}

/** As Venue Staff, change a venue's setup and turnaround time. */
async function editTimes(page: Page, venueId: string, setup: string, turnaround: string) {
  await page.goto(`/#/venues/${venueId}/edit`)
  await page.getByLabel('Setup time (minutes)').fill(setup)
  await page.getByLabel('Turnaround time (minutes)').fill(turnaround)
  await page.getByRole('button', { name: 'Save changes' }).click()
}

/** As Venue Staff, remove a venue that has no bookings. */
async function deleteVenue(page: Page, venueId: string) {
  await page.goto(`/#/venues/${venueId}`)
  await page.getByRole('button', { name: 'Delete venue' }).click()
  await page.getByRole('button', { name: 'Yes, delete it' }).click()
  await expect(page).toHaveURL(/#\/venues$/, { timeout: 10000 })
}

test.describe('US9.4 Venue setup and turnaround time', () => {
  test.beforeEach(async ({ page }) => {
    await waitForBackend(page)
  })

  test('Both times default to 0 on a new venue', async ({ page }) => {
    await signIn(page, 'Venue Staff')
    await page.goto('/#/venues/new')
    await expect(page.getByLabel('Setup time (minutes)')).toHaveValue('0')
    await expect(page.getByLabel('Turnaround time (minutes)')).toHaveValue('0')

    const venueId = await addVenue(page, uniqueName('Defaults'))

    await expect(detail(page, 'Setup time')).toHaveText('None')
    await expect(detail(page, 'Turnaround time')).toHaveText('None')
    await deleteVenue(page, venueId)
  })

  test('Venue Staff set both times on create and change them on edit', async ({ page }) => {
    await signIn(page, 'Venue Staff')
    const venueId = await addVenue(page, uniqueName('Create and edit'), '30', '45')
    await expect(detail(page, 'Setup time')).toHaveText('30 minutes')
    await expect(detail(page, 'Turnaround time')).toHaveText('45 minutes')

    await editTimes(page, venueId, '90', '15')

    await expect(detail(page, 'Setup time')).toHaveText('90 minutes (1 h 30 min)', {
      timeout: 10000,
    })
    await expect(detail(page, 'Turnaround time')).toHaveText('15 minutes')
    await deleteVenue(page, venueId)
  })

  test('A time that is not a whole number of minutes is refused', async ({ page }) => {
    await signIn(page, 'Venue Staff')
    const venueId = await addVenue(page, uniqueName('Refused'), '20', '10')

    await editTimes(page, venueId, '-5', '10')

    await expect(page.getByRole('alert')).toHaveText('The setup time cannot be negative.')
    await page.goto(`/#/venues/${venueId}`)
    await expect(detail(page, 'Setup time')).toHaveText('20 minutes')
    await deleteVenue(page, venueId)
  })

  test('Coordinators see both times on the venue detail view', async ({ page }) => {
    await signIn(page, 'Venue Staff')
    const name = uniqueName('Coordinator view')
    const venueId = await addVenue(page, name, '30', '45')
    await signOut(page)

    await signIn(page, 'Event Coordinator')
    await page.goto(`/#/venues/${venueId}`)

    await expect(page.getByRole('heading', { name })).toBeVisible()
    await expect(detail(page, 'Setup time')).toHaveText('30 minutes')
    await expect(detail(page, 'Turnaround time')).toHaveText('45 minutes')
    await expect(page.getByRole('button', { name: 'Edit venue' })).toHaveCount(0)

    await signOut(page)
    await signIn(page, 'Venue Staff')
    await deleteVenue(page, venueId)
  })

  test('Only Venue Staff can set the times', async ({ page }) => {
    await signIn(page, 'Event Coordinator')

    await page.goto('/#/venues/new')
    await expect(page.getByText('Access denied')).toBeVisible()

    await page.goto('/#/venues/1/edit')
    await expect(page.getByText('Access denied')).toBeVisible()
  })
})

// --- Changing a time re-checks the venue's bookings (US15.2) -----------------------
//
// This needs real bookings, so the setup walks the full journey for two events
// 30 minutes apart at one venue: the Organiser submits, the Coordinator Lead
// assigns, and the Coordinator approves and requests the venue.

type BookedVenue = { venueId: string; venueName: string; eventIds: string[] }

function bookingDay(): string {
  const date = new Date()
  date.setDate(date.getDate() + 45)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

async function submitEvent(page: Page, title: string, starts: string, ends: string) {
  const day = bookingDay()
  await page.goto('/#/events/new')
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('Starts').fill(`${day}T${starts}`)
  await page.getByLabel('Ends').fill(`${day}T${ends}`)
  await page.getByLabel('Purpose').fill('Check venue turnaround.')
  await page.getByLabel('Expected attendance').fill('50')
  await page.getByLabel('Description').fill('Created by the US9.4 end-to-end tests.')
  for (const name of [
    'Venue requirements',
    'Accessibility needs',
    'Equipment needs',
    'Registration needs',
  ]) {
    await page.getByRole('group', { name }).getByLabel('None / Not required').check()
  }
  await page.getByLabel('Preferred layout').selectOption('None / Not required')
  await page.getByRole('button', { name: 'Submit', exact: true }).click()
  await expect(page).toHaveURL(/#\/events\/\d+$/, { timeout: 10000 })
  return /#\/events\/(\d+)$/.exec(page.url())?.[1] ?? ''
}

async function assignToCoordinator(page: Page, title: string) {
  await page.goto('/#/unassigned-queue')
  await page
    .locator('.event-card')
    .filter({ hasText: title })
    .getByRole('button', { name: /Assign Coordinator/ })
    .click()
  await page
    .getByRole('button', { name: new RegExp(TEST_USERS['Event Coordinator'].name) })
    .click()
  await expect(page.getByText(title)).toHaveCount(0, { timeout: 10000 })
}

async function approveAndBook(page: Page, eventId: string, venueName: string) {
  // Through the events list, as a Coordinator would get there, so each event's
  // booking form starts from that event's own times.
  await page.goto('/#/events')
  await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible()
  await page.goto(`/#/events/${eventId}`)
  await page.getByRole('button', { name: 'Approve event' }).click()
  await expect(page.getByText('Approved. The status change has been recorded.')).toBeVisible({
    timeout: 10000,
  })
  await page
    .getByLabel('Venue', { exact: true })
    .selectOption({ label: `${venueName} — holds 200` })
  await expect(page.getByText('Suitable', { exact: true })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: 'Request venue' }).click()
  await expect(page.getByText(`Requested ${venueName}.`, { exact: false })).toBeVisible({
    timeout: 10000,
  })
}

/** A new venue with Event A (10:00-12:00) and Event B (12:30-14:00) booked. */
async function bookedVenue(browser: Browser): Promise<BookedVenue> {
  const page = await browser.newPage()
  const venueName = uniqueName('Booked hall')
  const titles = [uniqueName('Event A'), uniqueName('Event B')]

  await signIn(page, 'Venue Staff')
  const venueId = await addVenue(page, venueName)
  await signOut(page)

  await signIn(page, 'Event Organiser')
  const eventIds = [
    await submitEvent(page, titles[0], '10:00', '12:00'),
    await submitEvent(page, titles[1], '12:30', '14:00'),
  ]
  await signOut(page)

  await signIn(page, 'Event Coordinator Lead')
  for (const title of titles) await assignToCoordinator(page, title)
  await signOut(page)

  await signIn(page, 'Event Coordinator')
  for (const eventId of eventIds) await approveAndBook(page, eventId, venueName)
  await signOut(page)

  await page.close()
  return { venueId, venueName, eventIds }
}

test.describe('US9.4 Re-check of bookings after a time change', () => {
  test.describe.configure({ mode: 'serial', timeout: 240_000 })

  let booked: BookedVenue

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(240_000)
    booked = await bookedVenue(browser)
  })

  test('A change that makes bookings clash flags them, without removing any', async ({
    page,
  }) => {
    await signIn(page, 'Venue Staff')

    // Event A's turnaround now runs to 12:31, past Event B's 12:30 start.
    await editTimes(page, booked.venueId, '0', '31')

    await expect(
      page.getByRole('heading', { name: 'Saved — 1 booking clash needs attention' }),
    ).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('listitem').getByText('New with this change')).toBeVisible()
    await expect(page.getByText('Nothing has been cancelled or removed.', { exact: false }))
      .toBeVisible()
    await signOut(page)

    // Both bookings are still on their events.
    await signIn(page, 'Event Coordinator')
    for (const eventId of booked.eventIds) {
      await page.goto('/#/events')
      await page.goto(`/#/events/${eventId}`)
      const bookings = page.getByRole('list', { name: 'Venue bookings for this event' })
      await expect(bookings.getByText(booked.venueName)).toBeVisible({ timeout: 10000 })
      await expect(bookings.getByText('Cancelled')).toHaveCount(0)
    }
  })

  test('A change that leaves enough time goes straight back to the venue', async ({ page }) => {
    await signIn(page, 'Venue Staff')

    // A turnaround that exactly fills the 30-minute gap is not a clash.
    await editTimes(page, booked.venueId, '0', '30')

    await expect(page).toHaveURL(new RegExp(`#/venues/${booked.venueId}$`), { timeout: 10000 })
    await expect(detail(page, 'Turnaround time')).toHaveText('30 minutes')
  })
})
