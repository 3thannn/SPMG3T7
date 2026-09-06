import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import LoginForm from './LoginForm'

afterEach(() => {
  vi.unstubAllGlobals()
})

function sessionResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ token: 'test-token', email: 'ada@example.com' }),
  }
}

it('renders the email, password, and submit controls', () => {
  render(<LoginForm onSignedIn={vi.fn()} />)

  expect(screen.getByLabelText('Email')).toBeInTheDocument()
  expect(screen.getByLabelText('Password')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
})

it('rejects an empty submission without calling the API', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<LoginForm onSignedIn={vi.fn()} />)

  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
  expect(screen.getByText('Enter your password.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('rejects a malformed email without calling the API', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<LoginForm onSignedIn={vi.fn()} />)

  await userEvent.type(screen.getByLabelText('Email'), 'not-an-email')
  await userEvent.type(screen.getByLabelText('Password'), 'hunter2')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('marks an invalid field for assistive technology', async () => {
  vi.stubGlobal('fetch', vi.fn())
  render(<LoginForm onSignedIn={vi.fn()} />)

  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('Enter your email address.')
})

it('posts the credentials and hands the session back on success', async () => {
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse())
  vi.stubGlobal('fetch', fetchMock)
  const onSignedIn = vi.fn()
  render(<LoginForm onSignedIn={onSignedIn} />)

  await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'hunter2')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'ada@example.com', password: 'hunter2' }),
  })
  expect(onSignedIn).toHaveBeenCalledWith({ token: 'test-token', email: 'ada@example.com' })
})

it('shows a rejection message when the server returns 401', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
  const onSignedIn = vi.fn()
  render(<LoginForm onSignedIn={onSignedIn} />)

  await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  expect(onSignedIn).not.toHaveBeenCalled()
})

it('distinguishes an unreachable server from a rejection', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))
  render(<LoginForm onSignedIn={vi.fn()} />)

  await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'hunter2')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server')
})

it('disables the controls while the request is in flight', async () => {
  let release: (value: unknown) => void = () => {}
  const pending = new Promise((resolve) => {
    release = resolve
  })
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending))
  render(<LoginForm onSignedIn={vi.fn()} />)

  await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'hunter2')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  const submit = await screen.findByRole('button', { name: 'Signing in…' })
  expect(submit).toBeDisabled()
  expect(screen.getByLabelText('Email')).toBeDisabled()

  release(sessionResponse())
})
