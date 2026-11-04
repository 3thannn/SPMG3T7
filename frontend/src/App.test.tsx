import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { storeSession } from './session'
import { buildSession } from './test/sessions'
import type { Role } from './status'

beforeEach(() => {
  window.location.hash = ''
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

type MeOutcome = 'ok' | 'expired' | 'revoked'

/**
 * Stand in for the API, routing by URL, so a test can say what /auth/me should
 * answer without hand-stubbing every other call the page makes on load.
 */
function stubApi({ me = 'ok', role = 'Event Organiser' }: { me?: MeOutcome; role?: Role } = {}) {
  const session = buildSession({ role })

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)

    if (url.endsWith('/health')) {
      return { ok: true, status: 200, json: async () => ({ status: 'ok' }) }
    }

    if (url.endsWith('/auth/logout')) {
      return { ok: true, status: 204, json: async () => ({}) }
    }

    if (url.endsWith('/auth/me')) {
      if (me === 'ok') {
        return { ok: true, status: 200, json: async () => session }
      }
      const detail =
        me === 'expired'
          ? { code: 'session_expired', message: 'Your session expired after a period of inactivity.' }
          : { code: 'not_authenticated', message: 'Your session is no longer valid.' }
      return { ok: false, status: 401, json: async () => ({ detail }) }
    }

    // US8.2: unassigned events queue
    if (url.endsWith('/events/unassigned')) {
      return { ok: true, status: 200, json: async () => [] }
    }

    // Users list for coordinator assignment
    if (url.endsWith('/auth/users')) {
      return { ok: true, status: 200, json: async () => [] }
    }

    // US20.1: the Attendee's events open for registration; US20.2: their registrations
    if (url.endsWith('/attendee/events') || url.endsWith('/attendee/registrations')) {
      return { ok: true, status: 200, json: async () => [] }
    }

    throw new Error(`unexpected request to ${url}`)
  })

  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, session }
}

/** Put a session in storage, as a previous sign-in would have. */
function signedInAs(role: Role) {
  const session = buildSession({ role })
  storeSession(session)
  return session
}

it('ends the session on the server when the user signs out', async () => {
  signedInAs('Event Organiser')
  const { fetchMock } = stubApi({ me: 'ok' })
  window.location.hash = '/events'
  render(<App />)
  await screen.findByRole('heading', { name: 'Events' })

  await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }))

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith('/auth/logout')),
    ).toBe(true),
  )
  expect(localStorage.getItem('spmg3t7.session.v1')).toBeNull()
})

/* ---------- US1.1: inactivity ---------- */

it('signs the user out after the inactivity window and says why', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  signedInAs('Event Organiser')
  stubApi({ me: 'ok' })
  window.location.hash = '/events'

  render(<App />)
  await screen.findByRole('heading', { name: 'Events' })

  await act(async () => {
    vi.advanceTimersByTime(30 * 60 * 1000 + 1000)
  })

  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  const notice = screen.getByText(/30 minutes of inactivity/)
  expect(notice).toHaveAttribute('role', 'status')
})

/* ---------- US1.3: out-of-role pages ---------- */

/*
 * Both roles can read the events list, so the enforced boundary between them is
 * creating an event: an Organiser proposes, a Coordinator reviews. That is the
 * case these push against.
 */

it('blocks a Coordinator from creating an event and explains why', async () => {
  signedInAs('Event Coordinator')
  stubApi({ me: 'ok', role: 'Event Coordinator' })
  window.location.hash = '/events/new'

  render(<App />)

  expect(await screen.findByText('Access denied')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent(
    'The Event Coordinator role cannot open creating an event. That is available to Organisers.',
  )
})
