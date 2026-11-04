import { test, expect } from '@playwright/test'
import { apiAs, approvedEvent, as, reset } from './support'

/** No venue needs, so suitability turns on capacity and the slot alone. */
const NO_NEEDS = {
  venueRequirements: 'None / Not required',
  preferredLayout: 'None / Not required',
  accessibilityNeeds: 'None / Not required',
}

/**
 * Venues and their bookings across Venue Staff and the Coordinator: US9.1a,
 * US9.2, US9.3, US12.1, US14.1, US14.2 (+ D7), US14.3, US14.5, US15.1, US16.1,
 * US18.1, US10.2.
 *
 * e2e_server's seed: event 1 "Open House" (Planning, Priya) has booking 1
 * (Great Hall, Requested), booking 2 (Great Hall, Confirmed) and booking 5
 * (Flagged Room, Needs replacement "Burst pipe").
 */

test.beforeEach(async ({ request }) => {
  await reset(request)
})

test('US9.1a/US9.2: Venue Staff add a venue; a Coordinator sees it read-only', async ({ page }) => {
  await as(page, 'Venue Staff', '/venues/new')
  await page.getByLabel('Name').fill('Atrium')
  await page.getByLabel('Location').fill('Science Quarter')
  await page.getByLabel('Capacity').fill('90')
  await page.getByRole('button', { name: 'Add venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Atrium' })).toBeVisible()

  await as(page, 'Event Coordinator', '/venues')
  await page.getByText('Atrium', { exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Atrium' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Edit venue/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Delete venue/ })).toHaveCount(0)
})

test('US9.3: the catalogue filters combine', async ({ page }) => {
  await as(page, 'Event Coordinator', '/venues')
  await page.getByLabel('Minimum capacity').fill('100')
  await page.getByRole('button', { name: 'Apply filters' }).click()

  await expect(page.getByText('Great Hall', { exact: true })).toBeVisible()
  await expect(page.getByText('Bertha Room', { exact: true })).toHaveCount(0)
})

test('US14.1/US18.1: a suitable venue is requested; one that is too small cannot be', async ({
  page,
  request,
}) => {
  const id = await approvedEvent(request, 'Careers Fair', { ...NO_NEEDS, expectedAttendance: 50 })

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByLabel('Venue', { exact: true }).selectOption('2')
  await expect(page.getByText('Not suitable')).toBeVisible()
  await expect(page.getByText('It holds 40 people, and this booking is for 50.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Request venue' })).toBeDisabled()

  await page.getByLabel('Venue', { exact: true }).selectOption('3')
  await expect(page.getByText('Suitable', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Request venue' }).click()
  await expect(page.locator('.booking-row').filter({ hasText: 'Seminar Room 4' })).toContainText(
    'Requested',
  )
})

test('US16.1/US10.2: Venue Staff approve a request and the Coordinator is told', async ({
  page,
}) => {
  await as(page, 'Venue Staff', '/booking-requests')
  const card = page.locator('li, article').filter({ hasText: 'Open House' }).first()
  await card.getByRole('button', { name: /^Approve/ }).click()
  await expect(page.getByRole('status').first()).toBeVisible()

  await as(page, 'Event Coordinator', '/events/1')
  await expect(page.locator('.booking-row').filter({ hasText: 'Great Hall' }).first()).toContainText(
    'Confirmed',
  )
  await as(page, 'Event Coordinator', '/notifications')
  await expect(page.getByText(/Great Hall/).first()).toBeVisible()
})

test('US16.1: a rejection needs a reason, which the Coordinator then sees', async ({ page }) => {
  await as(page, 'Venue Staff', '/booking-requests')
  const card = page.getByRole('listitem').filter({ hasText: 'Open House' }).first()
  await card.getByRole('button', { name: /^Reject/ }).first().click()
  await card.getByRole('button', { name: 'Reject booking' }).click()
  await expect(card.getByRole('alert')).toBeVisible()
  await card.getByLabel("Why can't this booking be supported?").fill('Closed for exams that week.')
  await card.getByRole('button', { name: 'Reject booking' }).click()

  await as(page, 'Event Coordinator', '/events/1')
  await expect(page.getByText('Closed for exams that week.').first()).toBeVisible()
})

test('US14.2 + D7: the Coordinator cancels a Confirmed booking with a reason', async ({
  page,
  request,
}) => {
  await as(page, 'Event Coordinator', '/events/1')
  const confirmed = page
    .getByRole('listitem')
    .filter({ hasText: 'Great Hall' })
    .filter({ hasText: 'Confirmed' })
  await confirmed.getByRole('button', { name: 'Cancel the Great Hall booking' }).click()
  await page.getByLabel('Why are you cancelling this booking?').fill('Moving to a smaller room.')
  await page.getByRole('button', { name: /^Cancel booking/ }).click()

  await expect(page.getByText(/Cancelled by Priya.*Moving to a smaller room\./)).toBeVisible()
  const coordinator = await apiAs(request, 'Event Coordinator')
  const bookings = await coordinator.get('/events/1/bookings')
  expect(bookings.find((b: { id: string }) => b.id === '2').status).toBe('Cancelled')
})

test('US15.1: a request for a taken slot is refused, naming the clash', async ({
  page,
  request,
}) => {
  const coordinator = await apiAs(request, 'Event Coordinator')
  const bookings = await coordinator.get('/events/1/bookings')
  const taken = bookings.find((b: { id: string }) => b.id === '2')
  const id = await approvedEvent(request, 'Careers Fair', {
    startsAt: taken.startsAt.slice(0, 16),
    endsAt: taken.endsAt.slice(0, 16),
    expectedAttendance: 50,
    ...NO_NEEDS,
  })

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByLabel('Venue', { exact: true }).selectOption('1')

  await expect(page.getByText(/booking #2/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Request venue' })).toBeDisabled()
})

test('US14.5: a flagged booking is replaced and kept as history', async ({ page }) => {
  await as(page, 'Event Coordinator', '/events/1')
  const flagged = page.locator('.booking-row').filter({ hasText: 'Flagged Room' })
  await expect(flagged).toContainText('Needs replacement')
  await expect(flagged).toContainText('Burst pipe')
  await flagged.getByRole('button', { name: /replacement/i }).click()
  await page.getByLabel('Choose a replacement venue').selectOption('3')
  await page.getByRole('button', { name: /Request .*replacement/i }).click()

  await expect(page.getByText(/Requested Seminar Room 4 as a replacement/)).toBeVisible()
  await expect(page.locator('.booking-row').filter({ hasText: 'Flagged Room' })).toContainText(
    'Replaced',
  )
})

test('US12.1: Venue Staff mark a venue unavailable; a Coordinator sees the dates', async ({
  page,
}) => {
  const start = new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10)
  await as(page, 'Venue Staff', '/venues/3')
  await page.getByLabel('Start date').fill(start)
  await page.getByLabel('End date').fill(start)
  await page.getByLabel(/reason/i).first().selectOption('maintenance')
  await page.getByRole('button', { name: 'Mark unavailable' }).click()
  await expect(page.getByText(/^Marked unavailable:/)).toContainText('No bookings were flagged.')

  await as(page, 'Event Coordinator', '/venues/3')
  await expect(page.getByRole('heading', { name: 'Unavailable dates' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mark unavailable' })).toHaveCount(0)
})

test('US14.3: Venue Staff hold a venue; the Coordinator turns it into a request', async ({
  page,
  request,
}) => {
  const id = await approvedEvent(request, 'Careers Fair', { ...NO_NEEDS, expectedAttendance: 50 })

  await as(page, 'Venue Staff', '/venues/3')
  await page.getByLabel(/^Event/).selectOption(id)
  const expiry = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 16)
  await page.getByLabel(/expir/i).fill(expiry)
  await page.getByRole('button', { name: /Place hold/ }).click()
  await expect(page.getByText('Held').first()).toBeVisible()

  await as(page, 'Event Coordinator', `/events/${id}`)
  const held = page.locator('.booking-row').filter({ hasText: 'Seminar Room 4' })
  await expect(held).toContainText('Held')
  await held.getByRole('button', { name: /Request/ }).click()
  await expect(held).toContainText('Requested')
})
