import { test, expect, type Page } from '@playwright/test'
import { signIn, waitForBackend } from './helpers'

/**
 * E2E tests for US2.1 (reopened in Sprint 3): mandatory fields and set options
 * on the event request.
 *
 * These cover the user journeys for each acceptance criterion. Field-by-field
 * validation and boundaries (each missing field, attendance limits, dates,
 * lengths) are unit tested in NewEventPage.test.tsx, draftRules.test.ts,
 * eventNeeds.test.ts and backend/tests/test_event_needs.py.
 *
 * Event titles are unique and dates are relative to today, so the tests can run
 * against a shared database.
 */

const NOT_REQUIRED = 'None / Not required'

function futureDate(): string {
  const date = new Date()
  date.setDate(date.getDate() + 30)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function group(page: Page, name: string) {
  return page.getByRole('group', { name })
}

async function openNewEventForm(page: Page) {
  await signIn(page, 'Event Organiser')
  await page.getByRole('link', { name: 'Create' }).click()
  await expect(page.getByRole('heading', { name: 'New event' })).toBeVisible()
}

/** Name, description, purpose, date, start/end time and attendance. */
async function fillDetails(page: Page, title: string) {
  const day = futureDate()
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('Starts').fill(`${day}T18:00`)
  await page.getByLabel('Ends').fill(`${day}T21:00`)
  await page.getByLabel('Purpose').fill('Welcome the new intake.')
  await page.getByLabel('Expected attendance').fill('120')
  await page.getByLabel('Description').fill('Talks, a campus tour and a networking dinner.')
}

/** Venue requirements, layout, accessibility, equipment and registration needs. */
async function fillNeeds(page: Page) {
  await group(page, 'Venue requirements').getByLabel('Stage', { exact: true }).check()
  await group(page, 'Venue requirements').getByLabel('Projector').check()
  await page.getByLabel('Preferred layout').selectOption('Theatre')
  await group(page, 'Accessibility needs').getByLabel('Wheelchair access').check()
  await page.getByLabel('Equipment needs').fill('Two wireless microphones')
  await group(page, 'Registration needs').getByLabel(NOT_REQUIRED).check()
}

test.describe('US2.1 Event request — mandatory fields and set options', () => {
  test.beforeEach(async ({ page }) => {
    await waitForBackend(page)
  })

  test('A complete request is submitted and saved with every answer', async ({ page }) => {
    const title = `E2E US2.1 complete ${Date.now()}`
    await openNewEventForm(page)
    await fillDetails(page, title)
    await fillNeeds(page)

    await page.getByRole('button', { name: 'Submit', exact: true }).click()

    await expect(page.getByText('Status: Submitted', { exact: false }).first()).toBeVisible({
      timeout: 10000,
    })
    // Reloading reads the event back from the server, so this checks it was saved.
    await page.reload()
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    for (const answer of ['Stage, Projector', 'Theatre', 'Wheelchair access', NOT_REQUIRED]) {
      await expect(page.getByText(answer, { exact: true })).toBeVisible()
    }
  })

  test('Layout, facilities and accessibility are picked from set options', async ({ page }) => {
    await openNewEventForm(page)

    await expect(page.getByLabel('Preferred layout').locator('option')).toContainText([
      'Theatre',
      'Classroom',
      'Banquet',
      NOT_REQUIRED,
    ])
    const venue = group(page, 'Venue requirements')
    await venue.getByLabel('Stage', { exact: true }).check()
    await venue.getByLabel(NOT_REQUIRED).check()

    // Choosing "None / Not required" clears the options already ticked.
    await expect(venue.getByLabel('Stage', { exact: true })).not.toBeChecked()
  })

  test('Missing fields show a clear error and block submit', async ({ page }) => {
    await openNewEventForm(page)
    await fillDetails(page, `E2E US2.1 missing ${Date.now()}`)

    await page.getByRole('button', { name: 'Submit', exact: true }).click()

    await expect(page.getByRole('alert')).toHaveText(
      'Some required details are missing or invalid. Fix the highlighted fields to submit.',
    )
    await expect(
      page.getByText('Choose a preferred layout, or None / Not required.'),
    ).toBeVisible()
    await expect(page).toHaveURL(/#\/events\/new$/)
  })

  test('A draft saves without the checks, and is submitted once complete', async ({ page }) => {
    await openNewEventForm(page)
    await page.getByLabel('Title').fill(`E2E US2.1 draft ${Date.now()}`)

    await page.getByRole('button', { name: 'Save as draft' }).click()
    await expect(page.getByText('Status: Draft', { exact: false }).first()).toBeVisible({
      timeout: 10000,
    })

    // Submitting the incomplete draft is still refused...
    await page.getByRole('button', { name: 'Submit event' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText('Status: Draft', { exact: false }).first()).toBeVisible()

    // ...until it is filled in.
    await fillDetails(page, `E2E US2.1 draft ${Date.now()}`)
    await fillNeeds(page)
    await page.getByRole('button', { name: 'Submit event' }).click()
    await expect(page.getByText('Submitted. The status change has been recorded.')).toBeVisible({
      timeout: 10000,
    })
  })

  test('Only an Organiser can open the event request form', async ({ page }) => {
    await signIn(page, 'Event Coordinator')

    await page.goto('/#/events/new')

    await expect(page.getByText('Access denied')).toBeVisible()
  })

  test('If the connection fails on submit, the answers are kept', async ({ page }) => {
    const title = `E2E US2.1 offline ${Date.now()}`
    await openNewEventForm(page)
    await fillDetails(page, title)
    await fillNeeds(page)
    await page.route('**/events', (route) =>
      route.request().method() === 'POST' ? route.abort('failed') : route.continue(),
    )

    await page.getByRole('button', { name: 'Submit', exact: true }).click()

    await expect(page.getByRole('alert')).toContainText('Could not submit the event.')
    await expect(page.getByLabel('Title')).toHaveValue(title)
    await expect(page.getByLabel('Preferred layout')).toHaveValue('Theatre')
  })
})
