import { test, expect, type Page } from '@playwright/test'
import {
  apiAs,
  approvedEvent,
  as,
  assignedEvent,
  eventBody,
  reset,
  submittedEvent,
} from './support'

/** The event page's own status badge (the history repeats each status). */
const status = (page: Page) => page.locator('.status-badge-lg')

/**
 * The event request from the Organiser's form to the Coordinator's decision:
 * US2.1, US2.2, US4.2, US4.3, US7.3, US8.2, US8.3, US10.1, US11.1, US11.2, and
 * D2 (a Rejected event resubmitted).
 */

test.beforeEach(async ({ request }) => {
  await reset(request)
})

async function fillTheForm(page: Page, title: string) {
  const body = eventBody(title)
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('Purpose').fill(body.purpose)
  await page.getByLabel('Description').fill(body.description)
  await page.getByLabel('Starts').fill(body.startsAt)
  await page.getByLabel('Ends').fill(body.endsAt)
  await page.getByLabel('Expected attendance').fill('30')
  await page.getByRole('group', { name: 'Venue requirements' }).getByLabel('Projector').check()
  await page.getByLabel('Preferred layout').selectOption('Theatre')
  await page
    .getByRole('group', { name: 'Accessibility needs' })
    .getByLabel('Wheelchair access')
    .check()
  await page.getByLabel('Equipment needs').fill('One microphone')
  await page
    .getByRole('group', { name: 'Registration needs' })
    .getByLabel('None / Not required')
    .check()
}

test('US2.2/US4.2: a draft is saved, kept as Draft, then submitted exactly once', async ({
  page,
  request,
}) => {
  await as(page, 'Event Organiser', '/events/new')
  await fillTheForm(page, 'Open Day 2027')
  await page.getByRole('button', { name: 'Save as draft' }).click()
  await expect(status(page)).toHaveText(/Draft/)

  await page.reload()
  await expect(page.getByLabel('Title')).toHaveValue('Open Day 2027')
  await page.getByRole('button', { name: 'Submit event' }).click()

  await expect(status(page)).toHaveText(/Submitted/)
  await expect(page.getByRole('button', { name: 'Submit event' })).toHaveCount(0)
  const organiser = await apiAs(request, 'Event Organiser')
  const [event] = (await organiser.get('/events')).filter(
    (each: { title: string }) => each.title === 'Open Day 2027',
  )
  expect(event.status).toBe('Submitted')
})

test('US2.1: submitting an empty form names every missing field', async ({ page }) => {
  await as(page, 'Event Organiser', '/events/new')
  await page.getByLabel('Title').fill('Half-finished idea')

  await page.getByRole('button', { name: 'Submit', exact: true }).click()

  await expect(page.locator('form').getByRole('alert').first()).toHaveText(
    'Some required details are missing or invalid. Fix the highlighted fields to submit.',
  )
  for (const message of [
    'Give the event a purpose.',
    'Give the event a description.',
    'Choose the accessibility needs, or None / Not required.',
    'Describe the equipment needs, or choose None / Not required.',
    'Describe the registration needs, or choose None / Not required.',
  ]) {
    await expect(page.getByText(message)).toBeVisible()
  }
  await expect(page).toHaveURL(/#\/events\/new$/)
})

test('US2.2: a Coordinator does not see an Organiser draft', async ({ page, request }) => {
  const organiser = await apiAs(request, 'Event Organiser')
  await organiser.post('/events', eventBody('Secret Draft'))

  await as(page, 'Event Coordinator', '/events')

  await expect(page.getByRole('heading', { name: 'Events', level: 1 })).toBeVisible()
  await expect(page.getByText('Secret Draft')).toHaveCount(0)
})

test('US8.2/US8.3: the Lead assigns a submitted event and the Coordinator sees it Under Review', async ({
  page,
  request,
}) => {
  await submittedEvent(request, 'Careers Fair')

  await as(page, 'Event Coordinator Lead', '/unassigned-queue')
  const card = page.locator('.event-card, .event-row').filter({ hasText: 'Careers Fair' })
  await card.getByRole('button', { name: /Assign Coordinator/i }).click()
  await page.getByRole('button', { name: /Priya/ }).first().click()
  await expect(page.locator('.event-card, .event-row').filter({ hasText: 'Careers Fair' })).toHaveCount(0)

  await as(page, 'Event Coordinator', '/events')
  const row = page.getByRole('link', { name: /Careers Fair/ })
  await expect(row).toBeVisible()
  await row.click()
  await expect(status(page)).toHaveText(/Under Review/)
})

test('US7.3/US10.1: a clarification request reaches the Organiser', async ({ page, request }) => {
  const id = await assignedEvent(request, 'Alumni Night')

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByLabel('What do you need from them?').fill('Which caterer?')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByText('Which caterer?').first()).toBeVisible()

  await as(page, 'Event Organiser', `/events/${id}`)
  await expect(page.getByText('Which caterer?').first()).toBeVisible()
})

test('US4.3/US10.1: approving notifies the Organiser', async ({ page, request }) => {
  const id = await assignedEvent(request, 'Alumni Night')

  await as(page, 'Event Coordinator', `/events/${id}`)
  await page.getByRole('button', { name: 'Approve event' }).click()
  await expect(status(page)).toHaveText(/Approved/)

  await as(page, 'Event Organiser', '/notifications')
  await expect(page.getByText('"Alumni Night" was approved.')).toBeVisible()
})

test('US4.3 + D2: a rejection shows its reason; the Organiser revises and resubmits', async ({
  page,
  request,
}) => {
  const id = await assignedEvent(request, 'Alumni Night')
  const coordinator = await apiAs(request, 'Event Coordinator')
  await coordinator.post(`/events/${id}/reject`, { reason: 'The hall is booked that week.' })

  await as(page, 'Event Organiser', `/events/${id}`)
  await expect(page.getByText('The hall is booked that week.').first()).toBeVisible()
  await page.getByLabel('Title').fill('Alumni Night (new date)')
  await page.getByRole('button', { name: 'Resubmit event' }).click()

  await expect(status(page)).toHaveText(/Submitted/)
  const lead = await apiAs(request, 'Event Coordinator Lead')
  const queue = await lead.get('/events/unassigned')
  expect(queue.map((event: { title: string }) => event.title)).toContain('Alumni Night (new date)')
})

test('US11.1/US11.2: the Organiser proposes a change and the Coordinator accepts it', async ({
  page,
  request,
}) => {
  const id = await approvedEvent(request, 'Alumni Night')

  await as(page, 'Event Organiser', `/events/${id}`)
  await page.getByRole('button', { name: 'Request changes' }).click()
  await page.getByLabel('Expected attendance').fill('45')
  await page.getByRole('button', { name: 'Submit change request' }).click()
  await expect(page.getByText(/Awaiting the Coordinator's review/)).toBeVisible()

  await as(page, 'Event Coordinator', `/events/${id}`)
  const proposal = page.getByRole('list', { name: 'Proposed changes' })
  await expect(proposal).toContainText('45 people')
  await expect(proposal).toContainText('30 people')
  await expect(proposal).toContainText('Important')
  await page.getByRole('button', { name: /^Approve changes/ }).click()

  await expect(page.getByLabel('Expected attendance').or(page.getByText('45 people')).first()).toBeVisible()
  const organiser = await apiAs(request, 'Event Organiser')
  expect((await organiser.get(`/events/${id}`)).expectedAttendance).toBe(45)
})
