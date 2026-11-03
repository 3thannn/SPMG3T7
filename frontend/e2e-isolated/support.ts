import { expect, type APIRequestContext, type Page } from '@playwright/test'

/**
 * Shared set-up for the isolated browser journeys.
 *
 * Every spec here runs against `backend/e2e_server.py` (the real API over
 * in-memory stores), never the shared Supabase project, and resets it before
 * each test. A journey drives the step it is about through the browser; the
 * set-up before that step goes straight to the API, so each test is about one
 * thing and does not depend on another test having run.
 */
export const API = 'http://127.0.0.1:8001'

export type Role =
  | 'Event Organiser'
  | 'Event Coordinator'
  | 'Event Coordinator Lead'
  | 'Venue Staff'
  | 'Safety Officer'
  | 'Technical Support'
  | 'Attendee'

/** The e2e_server accounts (tests/conftest.py users, @connectsphere.com, password "password"). */
export const ACCOUNT: Record<Role, { email: string; name: string; home: string }> = {
  'Event Organiser': { email: 'organiser@connectsphere.com', name: 'Dylan', home: '/events' },
  'Event Coordinator': { email: 'coordinator@connectsphere.com', name: 'Priya', home: '/events' },
  'Event Coordinator Lead': {
    email: 'coordinatorlead@connectsphere.com',
    name: 'Jordan',
    home: '/unassigned-queue',
  },
  'Venue Staff': { email: 'venuestaff@connectsphere.com', name: 'Sam', home: '/venues' },
  'Safety Officer': { email: 'safetyofficer@connectsphere.com', name: 'Alex', home: '/safety-review' },
  'Technical Support': {
    email: 'technicalsupport@connectsphere.com',
    name: 'Bryan',
    home: '/equipment-requests',
  },
  Attendee: { email: 'attendee@connectsphere.com', name: 'Casey', home: '/attend' },
}
export const PASSWORD = 'password'
export const COORDINATOR_ID = '2'

/** A complete event, in the shape the API and the form both accept. */
export function eventBody(title: string, overrides: Record<string, unknown> = {}) {
  const day = new Date(Date.now() + 40 * 86_400_000).toISOString().slice(0, 10)
  return {
    title,
    purpose: 'Welcome the new intake.',
    description: 'Talks and a reception.',
    startsAt: `${day}T10:00`,
    endsAt: `${day}T12:00`,
    expectedAttendance: 30,
    venueRequirements: 'Projector',
    preferredLayout: 'Theatre',
    accessibilityNeeds: 'Wheelchair access',
    equipmentNeeds: 'One microphone',
    registrationNeeds: 'None / Not required',
    ...overrides,
  }
}

export async function reset(request: APIRequestContext) {
  expect((await request.post(`${API}/__test__/reset`)).ok()).toBeTruthy()
}

/** The real API as `role`, with a session of its own. */
export async function apiAs(request: APIRequestContext, role: Role) {
  const login = await request.post(`${API}/auth/login`, {
    data: { email: ACCOUNT[role].email, password: PASSWORD },
  })
  expect(login.ok(), `sign in as ${role}`).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).token}` }
  async function send(method: 'get' | 'post' | 'put' | 'patch', path: string, data?: object) {
    const response = await request[method](`${API}${path}`, { headers, data })
    expect(response.ok(), `${method.toUpperCase()} ${path}: ${await response.text()}`).toBeTruthy()
    return response.status() === 204 ? null : response.json()
  }
  return {
    get: (path: string) => send('get', path),
    post: (path: string, data?: object) => send('post', path, data),
    put: (path: string, data?: object) => send('put', path, data),
    patch: (path: string, data?: object) => send('patch', path, data),
  }
}

/** Sign in through the real form; the role in the nav says it worked. */
export async function signInAs(page: Page, role: Role) {
  await page.goto('/#/signin')
  await page.getByLabel('Email').fill(ACCOUNT[role].email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('.topnav-role')).toHaveText(role, { timeout: 10_000 })
}

export async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('banner').getByRole('button', { name: 'Sign in' })).toBeVisible()
}

/** Sign out whoever is signed in, sign in as `role` and open `route`. */
export async function as(page: Page, role: Role, route: string) {
  if (await page.getByRole('button', { name: 'Sign out' }).isVisible().catch(() => false)) {
    await signOut(page)
  }
  await signInAs(page, role)
  await page.goto(`/#${route}`)
}

// -- Set-up through the API, one step of the workflow each ---------------------

export async function submittedEvent(request: APIRequestContext, title: string, overrides = {}) {
  const organiser = await apiAs(request, 'Event Organiser')
  const created = await organiser.post('/events', eventBody(title, overrides))
  await organiser.post(`/events/${created.id}/submit`)
  return created.id as string
}

export async function assignedEvent(request: APIRequestContext, title: string, overrides = {}) {
  const id = await submittedEvent(request, title, overrides)
  const lead = await apiAs(request, 'Event Coordinator Lead')
  await lead.post(`/events/${id}/assign`, { coordinatorId: COORDINATOR_ID })
  return id
}

export async function approvedEvent(request: APIRequestContext, title: string, overrides = {}) {
  const id = await assignedEvent(request, title, overrides)
  const coordinator = await apiAs(request, 'Event Coordinator')
  await coordinator.post(`/events/${id}/approve`)
  return id
}

/** No venue needs, so suitability turns on capacity and the slot alone. */
export const NO_NEEDS = {
  venueRequirements: 'None / Not required',
  preferredLayout: 'None / Not required',
  accessibilityNeeds: 'None / Not required',
}

/** Approved, then a Confirmed booking at Seminar Room 4, so the event is in Planning. */
export async function planningEvent(request: APIRequestContext, title: string, overrides = {}) {
  const body = eventBody(title, { ...NO_NEEDS, ...overrides })
  const id = await approvedEvent(request, title, { ...NO_NEEDS, ...overrides })
  const coordinator = await apiAs(request, 'Event Coordinator')
  const booking = await coordinator.post(`/events/${id}/bookings`, {
    venueId: '3',
    startsAt: body.startsAt,
    endsAt: body.endsAt,
  })
  const staff = await apiAs(request, 'Venue Staff')
  await staff.post(`/booking-requests/${booking.id}/approve`)
  return id
}

/** Through the safety check and the Coordinator's confirmation (US4.4, US17.2, US4.7). */
export async function confirmedEvent(request: APIRequestContext, title: string, overrides = {}) {
  const id = await planningEvent(request, title, overrides)
  const coordinator = await apiAs(request, 'Event Coordinator')
  await coordinator.post(`/events/${id}/safety-check`)
  const officer = await apiAs(request, 'Safety Officer')
  const review = await officer.get(`/events/${id}/safety-review`)
  await officer.post(`/events/${id}/safety-check/approve`, { checkStartedAt: review.waitingSince })
  await coordinator.post(`/events/${id}/confirm`)
  return id
}
