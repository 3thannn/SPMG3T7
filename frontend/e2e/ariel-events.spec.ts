import { test, expect } from './ariel-fixtures'

test.describe.configure({ timeout: 180_000 })

test('SPMG3T7-27 / SPMG3T7-29: own draft saves, persists and submits exactly once', async ({ page, world }) => {
  const event = await world.event('Draft')
  await world.open(page, 'organiser', '/events')
  await page.getByRole('link').filter({ hasText: event.title }).click()
  await page.getByLabel('Purpose', { exact: true }).fill('Updated draft purpose')
  await page.getByRole('button', { name: 'Save draft', exact: true }).click()
  await expect.poll(async () => (await world.call('organiser', 'GET', `/events/${event.id}`)).purpose).toBe('Updated draft purpose')
  await page.reload()
  await expect(page.getByLabel('Purpose', { exact: true })).toHaveValue('Updated draft purpose')
  expect((await world.call('organiser', 'GET', `/events/${event.id}`)).status).toBe('Draft')
  await page.getByRole('button', { name: 'Submit event', exact: true }).click()
  await expect(page.getByText('Status: Submitted', { exact: false }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Save draft', exact: true })).toHaveCount(0)
  const duplicate = await world.response('organiser', 'POST', `/events/${event.id}/submit`)
  expect(duplicate.status()).toBe(409)
  const saved = await world.call('organiser', 'GET', `/events/${event.id}`)
  const submissions = saved.history.filter(h => h.to === 'Submitted')
  expect(submissions).toHaveLength(1)
  expect(submissions[0].byId).toBe((await world.session('organiser')).id)
  expect(Date.parse(submissions[0].at)).not.toBeNaN()
  expect(saved.coordinatorId).toBeNull()
  // A regular Coordinator cannot see this unassigned event, even by direct URL/API.
  expect((await world.response('coordinator', 'GET', `/events/${event.id}`)).status()).toBe(404)
})

for (const decision of ['approve', 'reject'] as const) {
  test(`SPMG3T7-35 / SPMG3T7-38 / SPMG3T7-60: assigned review ${decision}`, async ({ page, world }) => {
    const event = await world.event('Under Review', decision)
    expect(event.status).toBe('Under Review')
    expect(event.history.some(h => h.from === 'Submitted' && h.to === 'Under Review')).toBeTruthy()
    await world.open(page, 'coordinator', `/events/${event.id}`)
    if (decision === 'reject') {
      await expect(page.getByRole('button', { name: 'Reject event', exact: true })).toBeDisabled()
      await page.getByLabel('Reason for rejection', { exact: true }).fill('Test rejection reason')
    }
    await page.getByRole('button', { name: `${decision === 'approve' ? 'Approve' : 'Reject'} event`, exact: true }).click()
    const status = decision === 'approve' ? 'Approved' : 'Rejected'
    await expect.poll(async () => (await world.call('organiser', 'GET', `/events/${event.id}`)).status).toBe(status)
    await world.open(page, 'organiser', `/events/${event.id}`)
    await expect(page.getByText(`Status: ${status}`, { exact: false }).first()).toBeVisible()
    if (decision === 'reject') await expect(page.locator('.timeline-note').filter({ hasText: 'Test rejection reason' })).toBeVisible()
    const saved = await world.call('organiser', 'GET', `/events/${event.id}`)
    expect(saved.history.filter(h => h.to === status)).toHaveLength(1)
    expect(saved.history.find(h => h.to === status)?.byId).toBe((await world.session('coordinator')).id)
    expect((await world.response('coordinator', 'POST', `/events/${event.id}/approve`)).status()).toBe(409)
  })
}

test('SPMG3T7-60: first venue starts Planning; safety approval gates completion', async ({ page, world }) => {
  const event = await world.event()
  expect(event.status).toBe('Planning')
  expect(event.history.filter(h => h.from === 'Approved' && h.to === 'Planning')).toHaveLength(1)
  const bookings = await world.call<{ id: string }[]>('coordinator', 'GET', `/events/${event.id}/bookings`)
  await world.call('venue', 'POST', `/booking-requests/${bookings[0].id}/approve`)
  await world.call('coordinator', 'POST', `/events/${event.id}/safety-check`)
  await world.call('safety', 'POST', `/events/${event.id}/safety-check/approve`)
  await world.open(page, 'coordinator', `/events/${event.id}`)
  await expect(page.getByRole('button', { name: 'Mark Completed', exact: true })).toBeDisabled()
  expect((await world.response('coordinator', 'POST', `/events/${event.id}/complete`)).status()).toBe(409)
  // Only the test event is edited. Real server time, rather than a browser clock, controls completion.
  const day = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10)
  await world.call('coordinator', 'PUT', `/events/${event.id}`, { ...world.draft(), startsAt: `${day}T10:00`, endsAt: `${day}T12:00` })
  await page.reload()
  await page.getByRole('button', { name: 'Mark Completed', exact: true }).click()
  await expect.poll(async () => (await world.call('organiser', 'GET', `/events/${event.id}`)).status).toBe('Completed')
})
