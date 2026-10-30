import { test, expect, api } from './replacement-fixtures'

test('no available replacements gives an explicit empty state', async ({ page, request, world }) => {
  expect(world.bookingId).toBe('10')
  expect((await request.post(api + '/__test__/occupy-replacements')).ok()).toBeTruthy()
  await page.getByRole('button', { name: 'Find a replacement venue for Great Hall', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'No replacement venues are available' })).toBeVisible()
  await expect(page.getByLabel('Choose a replacement venue')).toHaveCount(0)
  await expect(page.locator('.booking-row')).toHaveCount(2)
})

test('a venue occupied after search is refused without replacing the old booking', async ({ page, request, world }) => {
  await page.getByRole('button', { name: 'Find a replacement venue for Great Hall', exact: true }).click()
  await page.getByLabel('Choose a replacement venue').selectOption('2')
  expect((await request.post(api + '/__test__/occupy-replacements')).ok()).toBeTruthy()
  await page.getByRole('button', { name: 'Request replacement', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('That venue is not available for the same time slot.')
  await expect(page.locator('.booking-row')).toHaveCount(2)
  const response = await request.get(api + '/events/' + world.eventId + '/bookings', {
    headers: { Authorization: 'Bearer ' + world.session.token },
  })
  const bookings = await response.json()
  expect(bookings).toHaveLength(2)
  expect(bookings.find((booking: { id: string }) => booking.id === world.bookingId).status).toBe('Needs replacement')
})

test.describe('organiser permissions', () => {
  test.use({ role: 'Event Organiser' })
  test('organiser can see history but cannot search or request a replacement', async ({ page, request, world }) => {
    await expect(page.locator('.booking-row').filter({ hasText: 'Great Hall' })).toContainText('Needs replacement')
    await expect(page.getByRole('button', { name: /Find a replacement venue/ })).toHaveCount(0)
    const headers = { Authorization: 'Bearer ' + world.session.token }
    const search = await request.get(api + '/bookings/' + world.bookingId + '/replacement-venues', { headers })
    expect(search.status()).toBe(403)
    const replacement = await request.post(api + '/bookings/' + world.bookingId + '/request-replacement', {
      headers, data: { venueId: '2' },
    })
    expect(replacement.status()).toBe(403)
  })
})
