import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

beforeEach(() => {
  window.location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('renders the landing hero', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }))

  render(<App />)

  expect(screen.getByRole('heading', { name: 'EventHub', level: 1 })).toBeInTheDocument()
})

it('reports the backend as connected when the health check succeeds', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }))

  render(<App />)

  expect(await screen.findByText('Backend connected')).toBeInTheDocument()
})

it('reports the backend as unreachable when the health check fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))

  render(<App />)

  expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
})

it('sends an anonymous visitor to sign in rather than the events list', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }))
  window.location.hash = '/events'

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
})
