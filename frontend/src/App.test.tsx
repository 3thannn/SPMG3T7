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

it('renders the landing hero', () => {
  stubApi()

  render(<App />)

  expect(screen.getByRole('heading', { name: 'EventHub', level: 1 })).toBeInTheDocument()
})

it('reports the backend as connected when the health check succeeds', async () => {
  stubApi()

  render(<App />)

  expect(await screen.findByText('Backend connected')).toBeInTheDocument()
})

it('reports the backend as unreachable when the health check fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))

  render(<App />)

  expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
})

it('sends an anonymous visitor to sign in rather than the events list', () => {
  stubApi()
  window.location.hash = '/events'

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
})

/* ---------- US1.1: the session survives a reload ---------- */

it('restores a stored session and opens the guarded page', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'ok' })
  window.location.hash = '/events'

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Events' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
})

it('checks the stored token with the server rather than trusting it', async () => {
  signedInAs('Event Organiser')
  const { fetchMock } = stubApi({ me: 'ok' })

  render(<App />)

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith('/auth/me')),
    ).toBe(true),
  )
})

/* ---------- US1.2: a session that has ended stops working ---------- */

it('signs the user out when the stored token has been revoked', async () => {
  // What the user sees after signing out on another device: the token is still
  // in this browser, and it is worth nothing.
  signedInAs('Event Organiser')
  stubApi({ me: 'revoked' })
  window.location.hash = '/events'

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  expect(localStorage.getItem('spmg3t7.session.v1')).toBeNull()
})

it('explains an expired session instead of just showing the form again', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'expired' })
  window.location.hash = '/events'

  render(<App />)

  // Scoped by text: the footer's backend indicator is also a live region.
  const notice = await screen.findByText(/session expired/i)
  expect(notice).toHaveAttribute('role', 'status')
})

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

it('needs a fresh sign-in for a guarded page after signing out', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'ok' })
  window.location.hash = '/events'
  render(<App />)
  await screen.findByRole('heading', { name: 'Events' })
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: 'Sign out' }))
  window.location.hash = '/events'

  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
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

it('keeps the session alive while the user is still working', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  signedInAs('Event Organiser')
  stubApi({ me: 'ok' })
  window.location.hash = '/events'

  render(<App />)
  await screen.findByRole('heading', { name: 'Events' })

  // Twenty minutes of quiet, a keystroke, then twenty more: still signed in.
  await act(async () => {
    vi.advanceTimersByTime(20 * 60 * 1000)
  })
  await act(async () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    vi.advanceTimersByTime(20 * 60 * 1000)
  })

  expect(screen.getByRole('heading', { name: 'Events' })).toBeInTheDocument()
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

it('renders none of the guarded page when the role is refused', async () => {
  signedInAs('Event Coordinator')
  stubApi({ me: 'ok', role: 'Event Coordinator' })
  window.location.hash = '/events/new'

  render(<App />)

  await screen.findByText('Access denied')
  expect(screen.queryByRole('heading', { name: /New event/i })).not.toBeInTheDocument()
})

it('gives a blocked role somewhere to go', async () => {
  signedInAs('Event Coordinator')
  stubApi({ me: 'ok', role: 'Event Coordinator' })
  window.location.hash = '/events/new'
  render(<App />)
  await screen.findByText('Access denied')

  await userEvent.setup().click(screen.getByRole('button', { name: 'Go to my dashboard' }))

  expect(await screen.findByRole('heading', { name: 'Events' })).toBeInTheDocument()
})

it('lets an Organiser through to the page a Coordinator is refused', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'ok', role: 'Event Organiser' })
  window.location.hash = '/events/new'

  render(<App />)

  await waitFor(() => expect(screen.queryByText('Access denied')).not.toBeInTheDocument())
})

it('leaves the create link out of the header for a Coordinator', async () => {
  signedInAs('Event Coordinator')
  stubApi({ me: 'ok', role: 'Event Coordinator' })
  window.location.hash = '/events'

  render(<App />)

  await screen.findByRole('heading', { name: 'Events' })
  expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Create' })).not.toBeInTheDocument()
})

it('offers the create link to an Organiser', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'ok', role: 'Event Organiser' })
  window.location.hash = '/events'

  render(<App />)

  await screen.findByRole('heading', { name: 'Events' })
  expect(screen.getByRole('link', { name: 'Create' })).toBeInTheDocument()
})

it('offers the events link to a role that can open it', async () => {
  signedInAs('Event Organiser')
  stubApi({ me: 'ok', role: 'Event Organiser' })
  window.location.hash = '/events'

  render(<App />)

  await screen.findByRole('heading', { name: 'Events' })
  expect(screen.getByRole('link', { name: 'Events' })).toBeInTheDocument()
})
