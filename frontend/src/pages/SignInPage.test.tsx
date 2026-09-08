/** US1.1 — the sign-in form. */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import SignInPage from './SignInPage'

beforeEach(() => {
  window.location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const SESSION_BODY = {
  token: 'test-token',
  id: 'user_organiser',
  email: 'organiser@spmg3t7.edu',
  name: 'Dylan',
  role: 'Organiser',
  permissions: ['events:create', 'events:read:own', 'events:submit'],
  home: '/events',
  idleMinutes: 30,
}

function renderPage(notice?: string) {
  const onSignedIn = vi.fn()
  render(<SignInPage onSignedIn={onSignedIn} notice={notice} />)
  return { onSignedIn, user: userEvent.setup() }
}

async function submit(user: ReturnType<typeof userEvent.setup>, password = 'Sprint1!demo') {
  await user.type(screen.getByLabelText('Email'), 'organiser@spmg3t7.edu')
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}

it('asks for an email before calling the server', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const { user } = renderPage()

  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByText('Enter your email address.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('rejects a malformed email', async () => {
  vi.stubGlobal('fetch', vi.fn())
  const { user } = renderPage()

  await user.type(screen.getByLabelText('Email'), 'not-an-email')
  await user.type(screen.getByLabelText('Password'), 'hunter2')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
})

it('hands the session up when the credentials are accepted', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SESSION_BODY }),
  )
  const { user, onSignedIn } = renderPage()

  await submit(user)

  expect(onSignedIn).toHaveBeenCalledWith(expect.objectContaining({ role: 'Organiser' }))
})

it('sends the user to the view the server picked for their role', async () => {
  // A route this page knows nothing about, so the only way it can land there is
  // by following the server rather than choosing a destination itself.
  const body = {
    ...SESSION_BODY,
    role: 'Coordinator',
    home: '/review',
    permissions: ['events:read:all', 'events:review'],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))
  const { user } = renderPage()

  await submit(user)

  expect(window.location.hash).toBe('#/review')
})

it('sends an Organiser to the events list', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SESSION_BODY }),
  )
  const { user } = renderPage()

  await submit(user)

  expect(window.location.hash).toBe('#/events')
})

it('surfaces a rejected credential clearly', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        detail: { code: 'invalid_credentials', message: 'Incorrect email or password.' },
      }),
    }),
  )
  const { user, onSignedIn } = renderPage()

  await submit(user, 'wrong')

  expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  expect(onSignedIn).not.toHaveBeenCalled()
})

it('says the server is unreachable rather than blaming the password', async () => {
  // Telling someone their password is wrong when the API is down sends them off
  // to reset a password that was fine.
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  const { user } = renderPage()

  await submit(user)

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Could not reach the server.')
  expect(alert).not.toHaveTextContent('password')
})

it('offers no way past the form when the server cannot be reached', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  const { user, onSignedIn } = renderPage()

  await submit(user)

  await screen.findByRole('alert')
  expect(onSignedIn).not.toHaveBeenCalled()
  expect(window.location.hash).toBe('')
})

it('shows why the user was sent back to the form', async () => {
  renderPage('You were signed out after 30 minutes of inactivity.')

  expect(await screen.findByRole('status')).toHaveTextContent(
    'You were signed out after 30 minutes of inactivity.',
  )
})

it('shows no notice when the user came to the form themselves', () => {
  renderPage()

  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

it('disables the form while the request is in flight', async () => {
  let release = (_value: unknown) => {}
  vi.stubGlobal(
    'fetch',
    vi.fn().mockReturnValue(new Promise((resolve) => (release = resolve))),
  )
  const { user } = renderPage()

  await submit(user)

  expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled()
  expect(screen.getByLabelText('Email')).toBeDisabled()

  release({ ok: true, status: 200, json: async () => SESSION_BODY })
})
