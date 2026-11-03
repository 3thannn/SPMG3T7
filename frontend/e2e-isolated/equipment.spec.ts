import { test, expect } from '@playwright/test'
import { apiAs, as, planningEvent, reset } from './support'

/**
 * Equipment from the catalogue to a reservation: US19.1, US19.2, US19.3 and
 * the Coordinator's notices (US10.2).
 */

test.beforeEach(async ({ request }) => {
  await reset(request)
})

const PROJECTOR = {
  name: 'Projector A',
  type: 'Projector',
  description: 'Ceiling-mounted HD projector',
  location: 'AV Store',
  totalQuantity: 3,
  outOfServiceQuantity: 1,
  outOfServiceReason: 'Lamp replacement',
}

test('US19.1: Technical Support add an item; a Coordinator sees usable stock, read-only', async ({
  page,
}) => {
  await as(page, 'Technical Support', '/equipment/new')
  await page.getByLabel('Name').fill(PROJECTOR.name)
  await page.getByLabel('Type').fill(PROJECTOR.type)
  await page.getByLabel('Location').fill(PROJECTOR.location)
  await page.getByLabel('Total quantity').fill('3')
  await page.getByLabel(/Out-of-service/i).first().fill('1')
  await page.getByLabel(/reason/i).fill('Lamp replacement')
  await page.getByRole('button', { name: /Save|Add equipment/ }).click()
  await expect(page.getByText('Projector A').first()).toBeVisible()

  await as(page, 'Event Coordinator', '/equipment')
  await expect(page.getByRole('link', { name: /Projector A/ })).toBeVisible()
  await expect(page.getByText('Usable of 3')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Add equipment' })).toHaveCount(0)
})

test('US19.2/US19.3/US10.2: a Coordinator requests a projector; Technical Support reserve it', async ({
  page,
  request,
}) => {
  const tech = await apiAs(request, 'Technical Support')
  await tech.post('/equipment', PROJECTOR)
  const id = await planningEvent(request, 'Graduation Dinner')

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByLabel('Catalogue item').selectOption({ label: 'Projector A' })
  // US19.2 AC1: the time needed starts as the event's own.
  const event = await (await apiAs(request, 'Event Coordinator')).get(`/events/${id}`)
  await expect(page.getByLabel('Needed from')).toHaveValue(event.startsAt)
  await expect(page.getByLabel('Needed until')).toHaveValue(event.endsAt)
  await page.getByLabel('Quantity').fill('2')
  await page.getByRole('button', { name: /Request equipment/ }).click()
  await expect(page.getByText('Requested').last()).toBeVisible()

  await as(page, 'Technical Support', '/equipment-requests')
  await page.getByRole('link', { name: /Projector/ }).first().click()
  await expect(page.getByText(/Available.*2|2 available/).first()).toBeVisible()
  await page.getByRole('button', { name: 'Reserve' }).click()
  await expect(page.locator('.equipment-request-detail-head')).toContainText('Reserved')

  await as(page, 'Event Coordinator', '/notifications')
  await expect(page.getByText(/Projector/).first()).toBeVisible()
})

test('US19.3: more than the usable stock shows the shortfall and cannot be reserved', async ({
  page,
  request,
}) => {
  const tech = await apiAs(request, 'Technical Support')
  await tech.post('/equipment', PROJECTOR)
  const id = await planningEvent(request, 'Graduation Dinner')
  const coordinator = await apiAs(request, 'Event Coordinator')
  const [item] = await coordinator.get('/equipment')
  const line = await coordinator.post(`/events/${id}/equipment-requests`, {
    equipmentType: 'Projector',
    equipmentId: Number(item.id),
    quantity: 3,
    technicalRequirements: '',
  })

  await as(page, 'Technical Support', `/equipment-requests/${line.id}`)

  await expect(page.getByRole('status').filter({ hasText: 'Shortfall: 1' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reserve', exact: true })).toBeDisabled()
})
