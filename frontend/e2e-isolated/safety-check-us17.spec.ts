import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { signOut, TEST_USERS } from '../e2e/helpers'

/**
 * US17.1 + US17.2 as one flow: the Safety Officer reviews an event Pending
 * Safety Check, and records a decision on it.
 *
 * US17.1 – Safety Officer review queue
 *   - List shows events in Pending Safety Check, oldest first.
 *   - Detail shows expected attendance, each booked venue's capacity, layout,
 *     accessibility and known restrictions, reserved equipment, and the
 *     event's accessibility requirements.
 *   - Read-only. Safety Officer role only.
 *
 * US17.2 – Safety Officer records a decision (reopened in Sprint 5)
 *   - Approve -> recorded as approved on the current stay; the event stays
 *     Pending Safety Check ("Safety approved, awaiting Coordinator
 *     confirmation") until the assigned Coordinator confirms it (US4.7).
 *   - Request changes -> Planning; note required; affected venue/equipment
 *     flagged for re-review; assigned Coordinator notified (US10.2).
 *   - Reject -> reason required; back to Planning with the reason
 *     (customer-confirmed).
 *   - Every decision is timestamped and attributable.
 *   - An event coming back into Pending Safety Check needs a fresh decision.
 *
 * Runs against `backend/e2e_server.py` (the real API over in-memory stores),
 * never the shared database; see playwright.isolated.config.ts. So the safety
 * rules exercised here are the server's own (`app/safety_decisions.py`,
 * `app/safety_check.py`). Its seed, reset before every test:
 *
 *   50 Charity Gala Night  Pending Safety Check since 10 days ago, 120 people.
 *                          Booking 50: Main Hall (capacity 100), Confirmed.
 *                          Equipment 50: Wireless microphone × 4, Reserved.
 *   51 Youth Workshop      Pending Safety Check since 5 days ago, 30 people.
 *                          Booking 51: Studio B, Confirmed.
 *
 * Credentials come from `e2e/helpers.ts`. Its `signIn` is not used because it
 * checks the Supabase display names; this seed's names come from
 * `backend/tests/conftest.py`, so sign-in here checks the role instead.
 */
const API = 'http://127.0.0.1:8001'

type FlowRole = 'Safety Officer' | 'Event Coordinator' | 'Event Organiser'

/** Display names in the e2e_server seed (`fixture_users()` in tests/conftest.py). */
const OFFICER = 'Alex'
const COORDINATOR = 'Priya'

const GALA = '50'
const WORKSHOP = '51'

// Exact server wording (app/safety_check.py, app/safety_decisions.py).
const FLAGS_OPEN =
  'The Safety Officer flagged arrangements for re-review. Mark each one ' +
  're-reviewed before sending the event for its safety check again.'
const AWAITING_COORDINATOR = 'Safety approved, awaiting Coordinator confirmation'
const CHECK_MOVED_ON =
  'This event was sent back and submitted again since you opened it. ' +
  'Reload it and review the current submission.'

type Decision = {
  outcome: 'approved' | 'changes-requested' | 'rejected'
  note: string
  decidedByName: string
  decidedAt: string
  checkStartedAt: string
  flags: unknown[]
}

/**
 * The real API, signed in as `role` with a session of its own. Used to check
 * what the server recorded, and to act "elsewhere" while a page is open.
 */
async function apiAs(request: APIRequestContext, role: FlowRole) {
  const { email, password } = TEST_USERS[role]
  const login = await request.post(`${API}/auth/login`, { data: { email, password } })
  expect(login.ok(), `sign in as ${role}`).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).token}` }
  return {
    async get(path: string) {
      const response = await request.get(`${API}${path}`, { headers })
      expect(response.ok(), `GET ${path}`).toBeTruthy()
      return response.json()
    },
    async post(path: string, data?: object) {
      const response = await request.post(`${API}${path}`, { headers, data })
      expect(response.ok(), `POST ${path}`).toBeTruthy()
      return response.json()
    },
  }
}

/** Sign in through the real form; the role in the nav says it worked. */
async function signInAs(page: Page, role: FlowRole) {
  await page.goto('/#/signin')
  await page.getByLabel('Email').fill(TEST_USERS[role].email)
  await page.getByLabel('Password').fill(TEST_USERS[role].password)
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('.topnav-role')).toHaveText(role, { timeout: 10000 })
}

/**
 * Sign in as `role` (signing out whoever is signed in first), then open
 * `route`. Returns the role, to pass back in next time.
 */
async function actAs(page: Page, signedIn: FlowRole | null, role: FlowRole, route: string) {
  if (signedIn) await signOut(page)
  await signInAs(page, role)
  await page.goto(`/#${route}`)
  return role
}

/** Click, wait for the decision the page sends on `eventId`, and return what it sent. */
async function sentWith(page: Page, eventId: string, action: string, click: () => Promise<void>) {
  const path = `/events/${eventId}/safety-check/${action}`
  const [request] = await Promise.all([
    page.waitForRequest((each) => each.method() === 'POST' && new URL(each.url()).pathname === path),
    click(),
  ])
  return request.postDataJSON()
}

const status = (page: Page) => page.locator('.detail-banner[role="status"]')
const NAIVE_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${API}/__test__/reset`)).ok()).toBeTruthy()
})

test.describe('US17.1 + US17.2: Operational Safety Check flow', () => {
  test('review queue, request changes, re-review, reject, resubmit, approve and confirm', async ({ page, request }) => {
    const coordinatorApi = await apiAs(request, 'Event Coordinator')
    const firstStay = (await (await apiAs(request, 'Safety Officer')).get(`/events/${GALA}/safety-review`))
      .waitingSince as string
    let who: FlowRole | null = null

    await test.step('US17.1: the queue lists events Pending Safety Check, oldest first', async () => {
      // The Safety Officer lands on the queue straight after signing in (US1.4).
      await signInAs(page, 'Safety Officer')
      who = 'Safety Officer'
      await expect(page).toHaveURL(/#\/safety-review/)
      await expect(page.getByRole('heading', { name: 'Safety Review', level: 1 })).toBeVisible()
      const queue = page.getByRole('list', { name: 'Events pending safety check' })
      await expect(queue.getByRole('listitem')).toHaveCount(2)
      await expect(queue.getByRole('heading', { level: 2 })).toHaveText(['Charity Gala Night', 'Youth Workshop'])
      await expect(queue.getByRole('listitem').first()).toContainText('Expected attendance: 120 people')
      await expect(queue.getByRole('listitem').first()).toContainText('Pending Safety Check')
    })

    await test.step('US17.1: the detail shows everything needed for the assessment', async () => {
      await page.getByRole('link', { name: 'Charity Gala Night' }).click()
      await expect(page.getByRole('heading', { name: 'Charity Gala Night', level: 1 })).toBeVisible()
      const review = page.getByRole('region', { name: 'Safety review' })
      // Event-level facts
      await expect(review).toContainText('Expected attendance120 people')
      await expect(review).toContainText('Accessibility requirementsWheelchair access, Hearing loop')
      // Each booked venue: capacity, layout, accessibility, known restrictions
      const venue = review.getByRole('list', { name: 'Booked venues' }).getByRole('listitem').first()
      await expect(venue).toContainText('Main Hall')
      await expect(venue).toContainText('Capacity100 people')
      await expect(venue).toContainText('Headcount120 people')
      await expect(venue.getByRole('note')).toHaveText('More people are booked into this venue than it holds.')
      await expect(venue).toContainText('Theatre · supports Theatre, Banquet')
      await expect(venue).toContainText('Venue accessibilityRamp, accessible toilet')
      await expect(venue).toContainText('Accessibility asked forWheelchair access, Hearing loop')
      await expect(venue).toContainText('Operating hours: 08:00-23:00')
      await expect(venue).toContainText('Setup 60 minutes before, turnaround 30 minutes after')
      await expect(venue).toContainText('Floor resurfacing')
      // Reserved equipment
      const equipment = review.getByRole('list', { name: 'Reserved equipment' })
      await expect(equipment).toContainText('Wireless microphone × 4')
      await expect(equipment).toContainText('Technical requirements: Spare batteries')
    })

    await test.step('US17.1: the review itself is read-only', async () => {
      const review = page.getByRole('region', { name: 'Safety review' })
      await expect(review.locator('input, textarea, select, button')).toHaveCount(0)
      // The Safety Officer gets no event edit form either.
      await expect(page.getByRole('button', { name: /save/i })).toHaveCount(0)
    })

    await test.step('US17.2: request changes needs a note and flags the affected arrangements', async () => {
      const sendBack = page.getByRole('button', { name: 'Request changes', exact: true })
      await expect(sendBack).toBeDisabled()
      await page.getByLabel('What needs to change').fill('Attendance exceeds the hall capacity; move or cap it.')
      // Flag both kinds of arrangement: the venue booking and the equipment line.
      await page.getByRole('checkbox', { name: /Main Hall/ }).check()
      await page.getByRole('checkbox', { name: 'Wireless microphone × 4' }).check()
      await expect(sendBack).toBeEnabled()

      const sent = await sentWith(page, GALA, 'request-changes', () => sendBack.click())
      await expect(status(page)).toHaveText(
        'Changes requested. The event is back in Planning and the Coordinator has been told.')
      // Pinned to the stay the Safety Officer was looking at.
      expect(sent).toMatchObject({ flaggedBookingIds: ['50'], flaggedEquipmentIds: ['50'], checkStartedAt: firstStay })

      const event = await coordinatorApi.get(`/events/${GALA}`)
      expect(event.status).toBe('Planning')
      // Timestamped and attributable (US4.2 audit pattern).
      expect(event.history.at(-1)).toMatchObject({ from: 'Pending Safety Check', to: 'Planning',
        byName: OFFICER, notes: 'Attendance exceeds the hall capacity; move or cap it.' })
      const [decision] = (await coordinatorApi.get(`/events/${GALA}/safety-decisions`)) as Decision[]
      expect(decision).toMatchObject({ outcome: 'changes-requested', decidedByName: OFFICER })
      expect(decision.decidedAt).toMatch(NAIVE_TIMESTAMP)
      expect(decision.flags).toHaveLength(2)
    })

    await test.step('US17.2/US10.2: the assigned Coordinator is notified', async () => {
      who = await actAs(page, who, 'Event Coordinator', '/notifications')
      await expect(page.getByText('Safety changes', { exact: true })).toBeVisible()
      await expect(page.getByText(
        'The Safety Officer requested changes to "Charity Gala Night": Attendance exceeds the hall ' +
        'capacity; move or cap it. 2 arrangements flagged for re-review.')).toBeVisible()
    })

    await test.step('US17.2: flagged arrangements must be re-reviewed before resubmitting', async () => {
      await page.goto(`/#/events/${GALA}`)
      await expect(page.getByRole('heading', { name: 'Charity Gala Night', level: 1 })).toBeVisible()
      // The Safety Officer's last decision: what, who and when, and the note.
      const feedback = page.locator('.safety-feedback')
      await expect(feedback).toContainText(`Changes requested by ${OFFICER} ·`)
      await expect(feedback).toContainText('Attendance exceeds the hall capacity; move or cap it.')
      // US4.2 audit: the move back to Planning is in the status timeline too.
      await expect(page.locator('.timeline-note')).toContainText(
        'Attendance exceeds the hall capacity; move or cap it.')
      const send = page.getByRole('button', { name: 'Send for safety check' })
      await expect(page.getByText(FLAGS_OPEN)).toBeVisible()
      await expect(send).toBeDisabled()

      const flags = page.getByRole('list', { name: 'Flagged for re-review' }).getByRole('listitem')
      await expect(flags).toHaveCount(2)
      await expect(flags.nth(0)).toContainText('Main Hall')
      await expect(flags.nth(1)).toContainText('Wireless microphone × 4')

      // Every flag must be re-reviewed: one left open still blocks the resubmission.
      await page.getByRole('button', { name: 'Mark Main Hall re-reviewed' }).click()
      await expect(flags.nth(0)).toContainText(`Re-reviewed by ${COORDINATOR}`)
      await expect(flags.nth(1)).toContainText('Mark re-reviewed')
      await expect(page.getByText(FLAGS_OPEN)).toBeVisible()
      await expect(send).toBeDisabled()

      await page.getByRole('button', { name: 'Mark Wireless microphone × 4 re-reviewed' }).click()
      await expect(flags.nth(1)).toContainText(`Re-reviewed by ${COORDINATOR}`)
      await expect(send).toBeEnabled()
      await send.click()
      await expect(status(page)).toHaveText(
        'Sent for the safety check. The event is now Pending Safety Check.')
      await expect(page.getByText(/Waiting for the Safety Officer/)).toBeVisible()
    })

    await test.step('US17.2: back in Pending Safety Check, a fresh decision is needed; reject needs a reason', async () => {
      who = await actAs(page, who, 'Safety Officer', `/events/${GALA}`)
      // The decision controls are offered again, with the earlier decision as context.
      await expect(page.getByRole('heading', { name: 'Safety check decision' })).toBeVisible()
      await expect(page.getByRole('region', { name: 'Earlier safety decisions' }))
        .toContainText(`Changes requested by ${OFFICER}`)

      await page.getByRole('radio', { name: 'Reject' }).check()
      const reject = page.getByRole('button', { name: 'Reject safety check' })
      await expect(reject).toBeDisabled()
      // Flags belong to a request for changes only.
      await expect(page.getByRole('checkbox', { name: /Main Hall/ })).toHaveCount(0)
      await page.getByLabel('Reason for rejecting').fill('No crowd-control marshals arranged for 120 guests.')

      const sent = await sentWith(page, GALA, 'reject', () => reject.click())
      await expect(status(page)).toHaveText(
        'Rejected. The event is back in Planning with your reason, and the Coordinator has been told.')
      // Pinned to the second stay, not the first.
      expect(sent.checkStartedAt).not.toBe(firstStay)

      const event = await coordinatorApi.get(`/events/${GALA}`)
      expect(event.status).toBe('Planning')
      expect(event.history.at(-1)).toMatchObject({ byName: OFFICER,
        notes: 'No crowd-control marshals arranged for 120 guests.' })
    })

    await test.step('US17.2: the Coordinator sees the rejection reason and resubmits', async () => {
      who = await actAs(page, who, 'Event Coordinator', '/notifications')
      await expect(page.getByText('Safety check rejected', { exact: true })).toBeVisible()
      await expect(page.getByText(/rejected the safety check for "Charity Gala Night": No crowd-control/))
        .toBeVisible()

      await page.goto(`/#/events/${GALA}`)
      const feedback = page.locator('.safety-feedback')
      await expect(feedback).toContainText(`Rejected by ${OFFICER} ·`)
      await expect(feedback).toContainText('No crowd-control marshals arranged for 120 guests.')
      await page.getByRole('button', { name: 'Send for safety check' }).click()
      await expect(status(page)).toHaveText(
        'Sent for the safety check. The event is now Pending Safety Check.')
    })

    await test.step('US17.2: approve records the decision; the event awaits its Coordinator', async () => {
      who = await actAs(page, who, 'Safety Officer', `/events/${GALA}`)
      const earlier = page.getByRole('region', { name: 'Earlier safety decisions' })
      await expect(earlier).toContainText(`Rejected by ${OFFICER}`)
      await expect(earlier).toContainText(`Changes requested by ${OFFICER}`)
      await expect(page.getByText(/Approve it for its Coordinator to confirm/)).toBeVisible()
      const sent = await sentWith(page, GALA, 'approve',
        () => page.getByRole('button', { name: 'Approve safety check' }).click())

      await expect(status(page)).toHaveText(
        'Approved. The Coordinator confirms the event once everything else is in place.')
      expect(sent.checkStartedAt).toMatch(NAIVE_TIMESTAMP)
      expect(sent.checkStartedAt).not.toBe(firstStay)
      // Not Confirmed: still Pending Safety Check, and the page says what it waits for.
      const badge = page.locator('.detail-head .status-badge')
      await expect(badge).toContainText('Pending Safety Check')
      await expect(badge).toContainText(AWAITING_COORDINATOR)
      await expect(page.getByText(/You approved this safety check/)).toBeVisible()
      await expect(page.locator('.safety-approval')).toContainText(`Approved by ${OFFICER} ·`)
      await expect(page.getByRole('button', { name: 'Approve safety check' })).toHaveCount(0)

      const event = await coordinatorApi.get(`/events/${GALA}`)
      expect(event.status).toBe('Pending Safety Check')
      expect(event.safetyApproved).toBe(true)
      const decisions = (await coordinatorApi.get(`/events/${GALA}/safety-decisions`)) as Decision[]
      expect(decisions.map((each) => each.outcome)).toEqual(['approved', 'rejected', 'changes-requested'])
      expect(decisions[0].checkStartedAt).toBe(sent.checkStartedAt)
      for (const each of decisions) {
        expect(each.decidedByName).toBe(OFFICER)
        expect(each.decidedAt).toMatch(NAIVE_TIMESTAMP)
      }
    })

    await test.step('US17.1: a decided event leaves the queue', async () => {
      await page.getByRole('link', { name: 'Safety Review', exact: true }).click()
      const queue = page.getByRole('list', { name: 'Events pending safety check' })
      await expect(queue.getByRole('heading', { level: 2 })).toHaveText(['Youth Workshop'])
    })

    await test.step('US17.2: the Organiser sees it still pending, awaiting the Coordinator', async () => {
      who = await actAs(page, who, 'Event Organiser', `/events/${GALA}`)
      const badge = page.locator('.detail-head .status-badge')
      await expect(badge).toContainText('Pending Safety Check')
      await expect(badge).toContainText(AWAITING_COORDINATOR)
    })

    await test.step('US4.7: only the Coordinator confirming moves it to Confirmed', async () => {
      who = await actAs(page, who, 'Event Coordinator', `/events/${GALA}`)
      await expect(page.locator('.safety-approval')).toContainText(`Approved by ${OFFICER} ·`)
      const confirm = page.getByRole('button', { name: 'Confirm event' })
      await expect(confirm).toBeEnabled()
      await confirm.click()

      await expect(status(page)).toHaveText(
        'Confirmed. The Organiser has been told the event is going ahead.')
      const badge = page.locator('.detail-head .status-badge')
      await expect(badge).toHaveText('Status: Confirmed')
      const event = await coordinatorApi.get(`/events/${GALA}`)
      expect(event.status).toBe('Confirmed')
      expect(event.safetyApproved).toBe(false)
    })
  })

  test('US17.2: a decision on a submission that has since been resubmitted is refused', async ({ page, request }) => {
    await actAs(page, null, 'Safety Officer', `/events/${GALA}`)
    await expect(page.getByRole('heading', { name: 'Safety check decision' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Approve safety check' })).toBeEnabled()

    // Meanwhile, elsewhere: the event is sent back, and the Coordinator sends it again.
    const officerApi = await apiAs(request, 'Safety Officer')
    const coordinatorApi = await apiAs(request, 'Event Coordinator')
    const { waitingSince } = await officerApi.get(`/events/${GALA}/safety-review`)
    await officerApi.post(`/events/${GALA}/safety-check/request-changes`,
      { checkStartedAt: waitingSince, note: 'Sent back from another tab.' })
    await coordinatorApi.post(`/events/${GALA}/safety-check`)

    // The open page still holds the first submission, so its approval is refused.
    await page.getByRole('button', { name: 'Approve safety check' }).click()
    await expect(page.getByRole('alert')).toHaveText(CHECK_MOVED_ON)
    expect((await coordinatorApi.get(`/events/${GALA}`)).status).toBe('Pending Safety Check')
    const decisions = (await coordinatorApi.get(`/events/${GALA}/safety-decisions`)) as Decision[]
    expect(decisions.map((each) => each.outcome)).toEqual(['changes-requested'])
  })

  test('US17.1: with nothing Pending Safety Check, the queue says so', async ({ page, request }) => {
    // Decide both seeded events through the API first.
    const officerApi = await apiAs(request, 'Safety Officer')
    for (const id of [GALA, WORKSHOP]) {
      const { waitingSince } = await officerApi.get(`/events/${id}/safety-review`)
      await officerApi.post(`/events/${id}/safety-check/approve`, { checkStartedAt: waitingSince })
    }

    await actAs(page, null, 'Safety Officer', '/safety-review')
    await expect(page.getByRole('heading', { name: 'No events waiting for a safety check' })).toBeVisible()
    await expect(page.getByText('An event appears here once its Coordinator sends it for sign-off.')).toBeVisible()
    await expect(page.getByRole('list', { name: 'Events pending safety check' })).toHaveCount(0)
  })

  test('US17.2: a request for changes with nothing flagged does not block resubmission', async ({ page, request }) => {
    const coordinatorApi = await apiAs(request, 'Event Coordinator')
    let who = await actAs(page, null, 'Safety Officer', `/events/${WORKSHOP}`)
    await expect(page.getByRole('heading', { name: 'Safety check decision' })).toBeVisible()

    // Flags are optional: a note alone is enough to send the event back.
    await page.getByLabel('What needs to change').fill('Add a first-aider to the run sheet.')
    const sent = await sentWith(page, WORKSHOP, 'request-changes',
      () => page.getByRole('button', { name: 'Request changes', exact: true }).click())
    await expect(status(page)).toHaveText(
      'Changes requested. The event is back in Planning and the Coordinator has been told.')
    expect(sent).toMatchObject({ note: 'Add a first-aider to the run sheet.', flaggedBookingIds: [], flaggedEquipmentIds: [] })
    const [decision] = (await coordinatorApi.get(`/events/${WORKSHOP}/safety-decisions`)) as Decision[]
    expect(decision.flags).toEqual([])

    // The notice carries the note, with no "flagged for re-review" count.
    who = await actAs(page, who, 'Event Coordinator', '/notifications')
    await expect(page.getByText(
      'The Safety Officer requested changes to "Youth Workshop": Add a first-aider to the run sheet.',
      { exact: true })).toBeVisible()

    // With nothing to re-review, the Coordinator can send it straight back.
    await page.goto(`/#/events/${WORKSHOP}`)
    await expect(page.locator('.safety-feedback')).toContainText('Add a first-aider to the run sheet.')
    await expect(page.getByRole('list', { name: 'Flagged for re-review' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Send for safety check' }).click()
    await expect(status(page)).toHaveText(
      'Sent for the safety check. The event is now Pending Safety Check.')
    expect((await coordinatorApi.get(`/events/${WORKSHOP}`)).status).toBe('Pending Safety Check')
  })

  test('US17.1: the safety review queue is for the Safety Officer role only', async ({ page }) => {
    await actAs(page, null, 'Event Coordinator', '/safety-review')
    // Same access-denied check as e2e/authentication.spec.ts (US1.3).
    await expect(page.getByText('Access denied')).toBeVisible()
    await expect(page.getByText(
      'The Event Coordinator role cannot open the safety review queue. That is available to Safety Officer.',
    )).toBeVisible()
    await expect(page.getByRole('list', { name: 'Events pending safety check' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Safety Review', exact: true })).toHaveCount(0)
  })
})
