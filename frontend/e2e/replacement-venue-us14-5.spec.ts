import { test, expect, api } from './replacement-fixtures'

test('AC2/AC3: replacement persists history and leaves other bookings untouched', async ({ page, request, world }) => {
  const headers = { Authorization: 'Bearer ' + world.session.token }
  const before = await request.get(api + '/events/' + world.eventId + '/bookings', { headers })
  expect(before.ok()).toBeTruthy()
  const originalBookings = await before.json()
  await page.getByRole('button', { name: 'Find a replacement venue for Great Hall', exact: true }).click()
  await page.getByLabel('Choose a replacement venue').selectOption('2')
  await page.getByRole('button', { name: 'Request replacement', exact: true }).click()
  await expect(page.getByText('Requested Bertha Room as a replacement.', { exact: false })).toBeVisible()
  await expect(page.locator('.booking-row')).toHaveCount(3)
  await page.reload()
  const oldRow = page.locator('.booking-row').filter({ has: page.locator('.booking-venue', { hasText: 'Great Hall' }) })
  const newRow = page.locator('.booking-row').filter({ has: page.locator('.booking-venue', { hasText: 'Bertha Room' }) })
  await expect(oldRow.locator('.booking-status')).toHaveText('Replaced')
  await expect(newRow.locator('.booking-status')).toHaveText('Requested')
  await expect(oldRow.getByRole('button')).toHaveCount(0)
  const after = await request.get(api + '/events/' + world.eventId + '/bookings', { headers })
  expect(after.ok()).toBeTruthy()
  const bookings = await after.json()
  expect(bookings).toHaveLength(3)
  expect(bookings.find((booking: { id: string }) => booking.id === '11')).toEqual(
    originalBookings.find((booking: { id: string }) => booking.id === '11'),
  )
  expect(bookings.find((booking: { venueId: string }) => booking.venueId === '2')).toMatchObject({
    eventId: world.eventId, startsAt: world.startsAt, endsAt: world.endsAt, status: 'Requested',
  })
  const duplicate = await request.post(api + '/bookings/' + world.bookingId + '/request-replacement', {
    headers, data: { venueId: '3' },
  })
  expect(duplicate.status()).toBe(409)
  const final = await request.get(api + '/events/' + world.eventId + '/bookings', { headers })
  expect(await final.json()).toEqual(bookings)
})
