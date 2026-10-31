import { test, expect } from './ariel-fixtures'

test.describe.configure({ timeout: 180_000 })

for (const accept of [true, false]) {
  test(`SPMG3T7-78: ${accept ? 'clarification, amendment, acceptance and arrangement flags' : 'reject changes with reason and preserve current values'}`, async ({ page, world }) => {
    const event = await world.event()
    await world.open(page, 'organiser', `/events/${event.id}`)
    await page.getByRole('button', { name: 'Request changes', exact: true }).click()
    await page.getByLabel('Expected attendance', { exact: true }).fill('50')
    await page.getByRole('button', { name: 'Submit change request', exact: true }).click()
    await expect(page.getByText(/Change request sent/)).toBeVisible()
    if (accept) {
      await world.open(page, 'coordinator', `/events/${event.id}`)
      await page.getByLabel('What do you need from them?').fill('Please revise attendance to 41')
      await page.getByRole('button', { name: 'Send request', exact: true }).click()
      await expect.poll(async () => (await world.call('organiser', 'GET', `/events/${event.id}`)).awaitingReply).toBe(true)
      await world.open(page, 'organiser', `/events/${event.id}`)
      await page.getByRole('button', { name: 'Request changes', exact: true }).click()
      await expect(page.getByLabel('Expected attendance', { exact: true })).toHaveValue('50')
      await page.getByLabel('Expected attendance', { exact: true }).fill('41')
      await page.getByRole('button', { name: 'Submit change request', exact: true }).click()
      await expect(page.getByText(/Change request sent/)).toBeVisible()
    }
    await world.open(page, 'coordinator', `/events/${event.id}`)
    const proposal = page.getByRole('list', { name: 'Proposed changes', exact: true })
    await expect(proposal).toContainText('Important')
    await expect(proposal).toContainText('40 people')
    await expect(proposal).toContainText(`${accept ? 41 : 50} people`)
    if (accept) {
      await page.getByRole('button', { name: 'Approve changes', exact: true }).click()
      await expect(page.getByRole('region', { name: 'Arrangement review' })).toContainText('Conflict')
      await page.reload()
      await expect(page.getByRole('region', { name: 'Arrangement review' })).toContainText('Conflict')
    } else {
      await expect(page.getByRole('button', { name: 'Reject changes', exact: true })).toBeDisabled()
      await page.getByLabel('Reason for rejecting the changes', { exact: true }).fill('Capacity cannot accommodate 50')
      await page.getByRole('button', { name: 'Reject changes', exact: true }).click()
    }
    await expect.poll(async () => (await world.call('organiser', 'GET', `/events/${event.id}`)).changeRequested).toBe(false)
    const saved = await world.call('organiser', 'GET', `/events/${event.id}`)
    expect(saved).toMatchObject({ status: 'Planning', expectedAttendance: accept ? 41 : 40, changeRequested: false })
    expect(saved.lastChangeReview?.outcome).toBe(accept ? 'approved' : 'rejected')
    expect(saved.reviewHistory?.length).toBeGreaterThan(0)
    const bookings = await world.call<{ status: string }[]>('coordinator', 'GET', `/events/${event.id}/bookings`)
    expect(bookings[0].status).toBe('Requested')
    await world.open(page, 'organiser', `/events/${event.id}`)
    if (!accept) await expect(page.getByText('Capacity cannot accommodate 50', { exact: true }).first()).toBeVisible()
    await page.goto('/#/notifications')
    await expect(page.locator('.notification-list').first()).toContainText(event.title)
  })
}
