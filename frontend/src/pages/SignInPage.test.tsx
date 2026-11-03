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
  role: 'Event Organiser',
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

it('sends the user to the view the server picked for their role', async () => {
  // A route this page knows nothing about, so the only way it can land there is
  // by following the server rather than choosing a destination itself.
  const body = {
    ...SESSION_BODY,
    role: 'Event Coordinator',
    home: '/review',
    permissions: ['events:read:submitted', 'events:review'],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))
  const { user } = renderPage()

  await submit(user)

  expect(window.location.hash).toBe('#/review')
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
