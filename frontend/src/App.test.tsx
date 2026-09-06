import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('renders the app heading', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }))

  render(<App />)

  expect(screen.getByRole('heading', { name: 'SPMG3T7' })).toBeInTheDocument()
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
