import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

/**
 * Browser tests for Dylan's stories: sign-in and access (US1.1-1.3), event
 * status (US4.1/4.2), clarification (US7.3), the venue catalogue (US9.1-9.3),
 * venue bookings and suitability (US14.1, US14.2, US18.1), hold expiry
 * (US14.4), cancelling an event (US4.6) and attendee registration
 * (US20.1-20.3).
 *
 * Runs against `backend/e2e_server.py`, never the shared database; see
 * playwright.isolated.config.ts. Each test resets that server, builds what it
 * needs through the API, and then does the story's own steps in the browser.
 *
 * The seed's Main Hall (venue 5) holds 100, has a stage, takes Theatre layouts
 * and is free 45 days out, which is where these events go.
 */
const API = 'http://127.0.0.1:8001'
const PASSWORD = 'Sprint1!demo'
const EMAIL = {
  organiser: 'organiser@spmg3t7.edu',
  coordinator: 'coordinator@spmg3t7.edu',
  lead: 'coordinatorlead@spmg3t7.edu',
  staff: 'venuestaff@spmg3t7.edu',
  safety: 'safetyofficer@spmg3t7.edu',
  attendee: 'attendee@spmg3t7.edu',
} as const
type Who = keyof typeof EMAIL

const NAME: Record<Who, string> = {
  organiser: 'Dylan',
  coordinator: 'Priya',
  lead: 'Jordan',
  staff: 'Sam',
  safety: 'Alex',
  attendee: 'Casey',
}

const MAIN_HALL = '5'

/** Singapore-local "YYYY-MM-DDTHH:MM", `days` from today at `hour`. */
function at(days: number, hour: number): string {
  const sgt = new Date(Date.now() + 8 * 3600_000 + days * 86_400_000)
  return `${sgt.toISOString().slice(0, 10)}T${String(hour).padStart(2, '0')}:00`
}

class Api {
  private tokens = new Map<Who, string>()

  constructor(private request: APIRequestContext) {}

  async call(who: Who, method: string, path: string, data?: unknown) {
    if (!this.tokens.has(who)) {
      const login = await this.request.post(`${API}/auth/login`, {
        data: { email: EMAIL[who], password: PASSWORD },
      })
      expect(login.ok(), await login.text()).toBeTruthy()
      this.tokens.set(who, (await login.json()).token)
    }
    const response = await this.request.fetch(`${API}${path}`, {
      method,
      data,
      headers: { Authorization: `Bearer ${this.tokens.get(who)}` },
    })
    expect(response.ok(), `${who} ${method} ${path}: ${await response.text()}`).toBeTruthy()
    return response.status() === 204 ? null : response.json()
  }

  /** Organiser creates and submits; the Lead assigns Priya. Under Review. */
  async assignedEvent(title: string) {
    const event = await this.call('organiser', 'POST', '/events', {
      title,
      purpose: 'Welcome the new intake.',
      description: 'Talks and a tour.',
      startsAt: at(45, 18),
      endsAt: at(45, 21),
      expectedAttendance: 80,
      venueRequirements: 'Stage',
      preferredLayout: 'Theatre',
      accessibilityNeeds: 'None / Not required',
      equipmentNeeds: 'None / Not required',
      registrationNeeds: 'Open registration',
    })
    await this.call('organiser', 'POST', `/events/${event.id}/submit`)
    return this.call('lead', 'POST', `/events/${event.id}/assign`, { coordinatorId: '2' })
  }

  async approvedEvent(title: string) {
    const event = await this.assignedEvent(title)
    return this.call('coordinator', 'POST', `/events/${event.id}/approve`)
  }

  /** Approved, Main Hall booked and confirmed, safety-checked: Confirmed. */
  async confirmedEvent(title: string) {
    const event = await this.approvedEvent(title)
    const booking = await this.call('coordinator', 'POST', `/events/${event.id}/bookings`, {
      venueId: MAIN_HALL,
      startsAt: at(45, 18),
      endsAt: at(45, 21),
      headcount: 80,
      layout: 'Theatre',
      facilities: 'Stage',
    })
    await this.call('staff', 'POST', `/booking-requests/${booking.id}/approve`)
    await this.call('coordinator', 'POST', `/events/${event.id}/safety-check`)
    return this.call('safety', 'POST', `/events/${event.id}/safety-check/approve`, {})
  }

  async openRegistration(eventId: string) {
    await this.call('coordinator', 'PUT', `/events/${eventId}/registration`, {
      open: true,
      capacity: 20,
    })
  }
}

async function signIn(page: Page, who: Who) {
  await page.goto('/#/signin')
  await page.getByLabel('Email').fill(EMAIL[who])
  await page.getByLabel('Password').fill(PASSWORD)
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('.topnav-name')).toHaveText(NAME[who])
}

test.beforeEach(async ({ request }) => {
  expect((await request.post(`${API}/__test__/reset`)).ok()).toBeTruthy()
})

test('US1.1-1.3: sign in, a role is kept to its own pages, sign out', async ({ page }) => {
  await signIn(page, 'attendee')
  await page.goto('/#/events')
  await expect(page.getByText(/cannot|not available|access/i).first()).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.goto('/#/events')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})

test('US4.1/4.2: an Organiser drafts an event and submits it', async ({ page }) => {
  await signIn(page, 'organiser')
  await page.goto('/#/events/new')
  await page.getByLabel('Title').fill('Open House')
  await page.getByLabel('Starts').fill(at(45, 18))
  await page.getByLabel('Ends').fill(at(45, 21))
  await page.getByLabel('Purpose').fill('Show prospective students around.')
  await page.getByLabel('Expected attendance').fill('80')
  await page.getByLabel('Description').fill('Tours and talks.')
  await page.getByRole('group', { name: 'Venue requirements' }).getByLabel('Stage').check()
  await page.getByLabel('Preferred layout').selectOption('Theatre')
  await page.getByRole('group', { name: 'Accessibility needs' }).getByLabel('Wheelchair access').check()
  await page.getByLabel('Equipment needs').fill('Two wireless microphones')
  await page.getByRole('group', { name: 'Registration needs' }).getByLabel('None / Not required').check()

  await page.getByRole('button', { name: 'Submit', exact: true }).click()

  await expect(page.getByText('Submitted').first()).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: 'Open House' })).toBeVisible()
})

test('US7.3: a Coordinator asks the Organiser for clarification', async ({ page, request }) => {
  const api = new Api(request)
  const event = await api.assignedEvent('Careers Fair')

  await signIn(page, 'coordinator')
  await page.goto(`/#/events/${event.id}`)
  await page.getByLabel('What do you need from them?').fill('Which rooms do the talks need?')
  await page.getByRole('button', { name: 'Send request' }).click()

  await expect(page.getByText('Which rooms do the talks need?').first()).toBeVisible()
})

test('US9.1-9.3: Venue Staff add a venue and the catalogue filters find it', async ({ page }) => {
  await signIn(page, 'staff')
  await page.goto('/#/venues/new')
  await page.locator('#venue-name').fill('Rooftop Terrace')
  await page.locator('#venue-location').fill('Main Campus, Building D')
  await page.locator('#venue-capacity').fill('250')
  await page.getByRole('button', { name: 'Add venue' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Rooftop Terrace' })).toBeVisible()

  await page.goto('/#/venues')
  await page.getByLabel('Minimum capacity').fill('200')
  await page.getByLabel('Location').fill('Building D')
  await page.getByRole('button', { name: /Search|Apply|Show/ }).first().click()

  await expect(page.getByText('Rooftop Terrace', { exact: true })).toBeVisible()
  await expect(page.getByText('Great Hall', { exact: true })).toHaveCount(0)
})

test('US14.1, US18.1, US14.2: request a suitable venue, then cancel that booking', async ({
  page,
  request,
}) => {
  const api = new Api(request)
  const event = await api.approvedEvent('Alumni Evening')

  await signIn(page, 'coordinator')
  await page.goto(`/#/events/${event.id}`)
  await page.getByLabel('Venue', { exact: true }).selectOption(MAIN_HALL)
  await expect(page.getByText(/Suitable/).first()).toBeVisible()
  await page.getByRole('button', { name: 'Request venue' }).click()

  const row = page.locator('li', { hasText: 'Main Hall' }).first()
  await expect(row.getByText('Requested')).toBeVisible()

  await page.getByRole('button', { name: 'Cancel the Main Hall booking' }).click()
  await page.getByLabel('Why are you cancelling this booking?').fill('Numbers dropped.')
  await page.getByRole('button', { name: 'Cancel booking' }).click()

  await expect(row.getByText('Cancelled', { exact: true })).toBeVisible()
})

test('US14.4: a hold expires at its deadline and can no longer be requested', async ({
  page,
  request,
}) => {
  const api = new Api(request)
  const event = await api.approvedEvent('Sports Day')
  const expires = new Date(Date.now() + 8 * 3600_000 + 5_000).toISOString().slice(0, 19)
  await api.call('staff', 'POST', '/holds', {
    venueId: MAIN_HALL,
    eventId: event.id,
    startsAt: at(45, 18),
    endsAt: at(45, 21),
    expiresAt: expires,
  })

  await signIn(page, 'coordinator')
  await page.goto(`/#/events/${event.id}`)
  const row = page.locator('li', { hasText: 'Main Hall' }).first()
  await expect(row.getByText('Held', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Request the held Main Hall' })).toBeVisible()

  await page.waitForTimeout(6_000)
  await page.reload()

  await expect(row.getByText('Hold expired', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Request the held Main Hall' })).toHaveCount(0)
})

test('US4.6: cancelling a Confirmed event releases its booking and registrations', async ({
  page,
  request,
}) => {
  const api = new Api(request)
  const event = await api.confirmedEvent('Open House')
  await api.openRegistration(event.id)
  await api.call('attendee', 'POST', `/attendee/events/${event.id}/registrations`, {
    name: 'Casey Tan',
    email: EMAIL.attendee,
  })

  await signIn(page, 'coordinator')
  await page.goto(`/#/events/${event.id}`)
  await expect(page.getByText('Confirmed').first()).toBeVisible()
  await page.getByRole('button', { name: 'Cancel this event…' }).click()
  await page.getByLabel('Why is this event being cancelled?').fill('Venue flooded.')
  await page.getByRole('button', { name: 'Confirm cancellation' }).click()

  await expect(page.getByText('Cancelled').first()).toBeVisible()
  const booking = page.locator('li', { hasText: 'Main Hall' }).first()
  await expect(booking.getByText('Cancelled', { exact: true })).toBeVisible()
  await expect(page.getByText('Event Cancelled').first()).toBeVisible()
})

test('US20.1-20.3: an Attendee registers and withdraws; the Organiser sees it', async ({
  page,
  request,
}) => {
  const api = new Api(request)
  const event = await api.confirmedEvent('Graduation Gala')
  await api.openRegistration(event.id)

  await signIn(page, 'attendee')
  await page.goto('/#/attend')
  await page.getByRole('button', { name: 'Register for Graduation Gala' }).click()
  await page.getByLabel('Name').fill('Casey Tan')
  await page.getByLabel('Email').fill(EMAIL.attendee)
  await page.getByRole('button', { name: 'Confirm registration' }).click()

  await page.goto('/#/my-registrations')
  await expect(page.getByText('Graduation Gala').first()).toBeVisible()
  await page.getByRole('button', { name: 'Withdraw from Graduation Gala' }).click()
  await page.getByRole('button', { name: 'Confirm withdrawal' }).click()
  await expect(page.getByText('Withdrawn').first()).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'organiser')
  await page.goto(`/#/events/${event.id}`)
  await expect(page.getByText('Casey Tan')).toBeVisible()
  await expect(page.getByText('Withdrawn').first()).toBeVisible()
})
