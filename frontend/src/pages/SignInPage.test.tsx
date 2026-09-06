import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import SignInPage from './SignInPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderPage() {
  const onSignedIn = vi.fn()
  render(<SignInPage onSignedIn={onSignedIn} />)
  return { onSignedIn, user: userEvent.setup() }
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

it('surfaces a rejected credential distinctly from an outage', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
  const { user } = renderPage()

  await user.type(screen.getByLabelText('Email'), 'ada@example.com')
  await user.type(screen.getByLabelText('Password'), 'wrong')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
})

it('offers the Sprint 1 preview only when the server cannot be reached', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))
  const { user, onSignedIn } = renderPage()

  await user.type(screen.getByLabelText('Email'), 'ada@example.com')
  await user.type(screen.getByLabelText('Password'), 'hunter2')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  await user.click(await screen.findByRole('button', { name: 'Continue without signing in' }))

  expect(onSignedIn).toHaveBeenCalledWith(expect.objectContaining({ role: 'Organiser' }))
})

it('does not offer the preview when the credentials were simply wrong', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
  const { user } = renderPage()

  await user.type(screen.getByLabelText('Email'), 'ada@example.com')
  await user.type(screen.getByLabelText('Password'), 'wrong')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  await screen.findByRole('alert')
  expect(
    screen.queryByRole('button', { name: 'Continue without signing in' }),
  ).not.toBeInTheDocument()
})
