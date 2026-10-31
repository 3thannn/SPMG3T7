/**
 * Which page each route opens. Every page is a stand-in here: the pages have
 * their own tests, and this file is about the routing in App.tsx — that each
 * route reaches its page with the id from the path, that an unknown path says
 * so, and that a sign-in or a session check that lands after the app has gone
 * changes nothing.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { loadStoredSession, storeSession } from './session'
import { buildSession } from './test/sessions'
import type { Role } from './status'

function stand_in(name: string) {
  return (props: Record<string, unknown>) => {
    const id = props.id ?? props.eventId ?? props.venueId
    return <h1>{`${name}${id ? ` ${String(id)}` : ''}`}</h1>
  }
}

vi.mock('./pages/EventsPage', () => ({ default: stand_in('Events page') }))
vi.mock('./pages/NewEventPage', () => ({ default: stand_in('New event page') }))
vi.mock('./pages/NotificationsPage', () => ({ default: stand_in('Notifications page') }))
vi.mock('./pages/EquipmentPage', () => ({
  EquipmentPage: stand_in('Equipment page'),
  EquipmentFormPage: stand_in('Equipment form'),
  EquipmentDetailPage: stand_in('Equipment detail'),
}))
vi.mock('./pages/EquipmentQueuePage', () => ({ default: stand_in('Equipment queue') }))
vi.mock('./pages/EquipmentRequestDetailPage', () => ({ default: stand_in('Equipment request') }))
vi.mock('./pages/VenuesPage', () => ({ default: stand_in('Venues page') }))
vi.mock('./pages/BookingRequestsPage', () => ({ default: stand_in('Booking requests') }))
vi.mock('./pages/BookingConflictsPage', () => ({ default: stand_in('Booking conflicts') }))
vi.mock('./pages/VenueFormPage', () => ({ default: stand_in('Venue form') }))
vi.mock('./pages/UnassignedQueuePage', () => ({ default: stand_in('Unassigned queue') }))
vi.mock('./pages/TeamAssignmentsPage', () => ({ default: stand_in('Team assignments') }))
vi.mock('./pages/SafetyReviewPage', () => ({ default: stand_in('Safety review') }))
vi.mock('./pages/AttendPage', () => ({ default: stand_in('Attend page') }))
vi.mock('./pages/MyRegistrationsPage', () => ({ default: stand_in('My registrations') }))
vi.mock('./pages/EventDetailPage', () => ({ default: stand_in('Event detail') }))
vi.mock('./pages/VenueDetailPage', () => ({ default: stand_in('Venue detail') }))
vi.mock('./pages/SignInPage', () => ({
  default: ({ onSignedIn }: { onSignedIn: (session: unknown) => void }) => (
    <button
      type="button"
      onClick={() => onSignedIn(buildSession({ role: 'Event Organiser', name: 'Dylan' }))}
    >
      Stand-in: sign in
    </button>
  ),
}))

/** The API answers the session check with `me` and everything else with an empty list. */
function stubApi(me: Promise<unknown> | unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/auth/me')) {
        const session = await me
        return { ok: true, status: 200, json: async () => session }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

function signedInAs(role: Role) {
  const session = buildSession({ role })
  storeSession(session)
  stubApi(session)
  return session
}

beforeEach(() => {
  window.location.hash = ''
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it.each([
  ['/events', 'Event Organiser', 'Events page'],
  ['/events/new', 'Event Organiser', 'New event page'],
  ['/notifications', 'Event Organiser', 'Notifications page'],
  ['/events/7', 'Event Organiser', 'Event detail 7'],
  ['/equipment', 'Technical Support', 'Equipment page'],
  ['/equipment/new', 'Technical Support', 'Equipment form'],
  ['/equipment/5/edit', 'Technical Support', 'Equipment form 5'],
  ['/equipment/5', 'Technical Support', 'Equipment detail 5'],
  ['/equipment-requests', 'Technical Support', 'Equipment queue'],
  ['/equipment-requests/30', 'Technical Support', 'Equipment request 30'],
  ['/venues', 'Venue Staff', 'Venues page'],
  ['/venues/new', 'Venue Staff', 'Venue form'],
  ['/venues/3/edit', 'Venue Staff', 'Venue form 3'],
  ['/venues/3', 'Venue Staff', 'Venue detail 3'],
  ['/booking-requests', 'Venue Staff', 'Booking requests'],
  ['/team-assignments', 'Event Coordinator Lead', 'Team assignments'],
] as const)('%s opens for %s', async (route, role, heading) => {
  signedInAs(role)
  window.location.hash = route

  render(<App />)

  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
})

it('says nothing lives at an unknown path, and offers the way home', async () => {
  const user = userEvent.setup()
  signedInAs('Event Organiser')
  window.location.hash = '/nowhere'
  render(<App />)

  expect(await screen.findByText('Nothing lives at /nowhere.')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Back home' }))

  expect(window.location.hash).not.toBe('#/nowhere')
})

it('keeps the session from the sign-in form for the next visit', async () => {
  const user = userEvent.setup()
  stubApi(null)
  window.location.hash = '/sign-in'
  render(<App />)

  await user.click(await screen.findByRole('button', { name: 'Stand-in: sign in' }))

  expect(loadStoredSession()?.name).toBe('Dylan')
})

it('ignores a session check that answers after the app has gone', async () => {
  storeSession(buildSession({ role: 'Event Organiser' }))
  let answer!: (session: unknown) => void
  stubApi(new Promise((resolve) => (answer = resolve)))
  const { unmount } = render(<App />)

  unmount()
  answer(buildSession({ role: 'Event Organiser', name: 'Renamed' }))
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(loadStoredSession()?.name).not.toBe('Renamed')
})

it('ignores a failed session check that answers after the app has gone', async () => {
  const stored = buildSession({ role: 'Event Organiser' })
  storeSession(stored)
  let fail!: (error: Error) => void
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) =>
      String(input).endsWith('/auth/me')
        ? new Promise((_resolve, reject) => (fail = reject))
        : Promise.resolve({ ok: true, status: 200, json: async () => [] }),
    ),
  )
  const { unmount } = render(<App />)

  unmount()
  fail(new TypeError('Failed to fetch'))
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(loadStoredSession()?.token).toBe(stored.token)
})
