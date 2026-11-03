import { test, expect, type Page } from '@playwright/test'
import { apiAs, as, confirmedEvent, planningEvent, reset } from './support'

/**
 * From Planning to a Confirmed event people register for, and cancelling one:
 * US4.4, US4.7, US10.3, US20.1, US20.2, US20.3, US4.6, and D3 (the Organiser
 * opens registration).
 */

test.beforeEach(async ({ request }) => {
  await reset(request)
})

const status = (page: Page) => page.locator('.status-badge-lg')

test('US4.4/US4.7/US10.3: sent for the safety check, approved, then confirmed by the Coordinator', async ({
  page,
  request,
}) => {
  const id = await planningEvent(request, 'Graduation Dinner')

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByRole('button', { name: /Send for safety check/i }).click()
  await expect(status(page)).toHaveText(/Pending Safety Check/)

  await as(page, 'Safety Officer', '/safety-review')
  await page.getByRole('link', { name: /Graduation Dinner/ }).click()
  await page.getByRole('button', { name: /^Approve/ }).click()
  await expect(page.getByText(/approved/i).first()).toBeVisible()

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByRole('button', { name: /^Confirm event/ }).click()
  await expect(status(page)).toHaveText(/Confirmed/)

  await as(page, 'Event Organiser', '/notifications')
  await expect(page.getByText('"Graduation Dinner" is confirmed and ready to go ahead.')).toBeVisible()
})

test('D3/US20.1/US20.2/US20.3: the Organiser opens registration, an Attendee registers and withdraws', async ({
  page,
  request,
}) => {
  const id = await confirmedEvent(request, 'Graduation Dinner')

  await as(page, 'Event Organiser', `/events/${id}`)
  await page.getByRole('checkbox', { name: 'Open registration to Attendees' }).check()
  await page.getByLabel('Capacity').fill('2')
  await page.getByRole('button', { name: 'Save registration' }).click()
  await expect(page.getByText('Registration is on: 0 of 2 places taken.')).toBeVisible()

  await as(page, 'Attendee', '/attend')
  const card = page.getByRole('listitem').filter({ hasText: 'Graduation Dinner' })
  await expect(card).toContainText('2 places left')
  await card.getByRole('button', { name: /^Register/ }).click()
  await page.getByRole('button', { name: 'Confirm registration' }).click()
  await expect(page.getByRole('status').first()).toBeVisible()

  await as(page, 'Event Organiser', `/events/${id}`)
  await expect(page.getByText('Casey', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('Registration is on: 1 of 2 places taken.')).toBeVisible()

  await as(page, 'Attendee', '/my-registrations')
  await page.getByRole('button', { name: /^Withdraw/ }).click()
  await page.getByRole('button', { name: 'Confirm withdrawal' }).click()
  await expect(page.getByText('Withdrawn').first()).toBeVisible()
  const organiser = await apiAs(request, 'Event Organiser')
  expect((await organiser.get(`/events/${id}/registration`)).registered).toBe(0)
})

test('US4.6: the Organiser cancels an event; its booking is released', async ({ page, request }) => {
  const id = await planningEvent(request, 'Graduation Dinner')

  await as(page, 'Event Organiser', `/events/${id}`)
  await page.getByRole('button', { name: 'Cancel this event…' }).click()
  await expect(page.getByRole('button', { name: 'Confirm cancellation' })).toBeDisabled()
  await page.getByLabel('Why is this event being cancelled?').fill('The speaker cannot attend.')
  await page.getByRole('button', { name: 'Confirm cancellation' }).click()

  await expect(status(page)).toHaveText(/Cancelled/)
  const coordinator = await apiAs(request, 'Event Coordinator')
  const [booking] = await coordinator.get(`/events/${id}/bookings`)
  expect(booking.status).toBe('Cancelled')
})
