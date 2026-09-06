import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthError, apiBaseUrl, fetchHealth, login } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiBaseUrl', () => {
  it('falls back to the local backend', () => {
    expect(apiBaseUrl()).toBe('http://localhost:8000')
  })
})

describe('fetchHealth', () => {
  it('returns the parsed payload when the API responds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }),
    )

    await expect(fetchHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/health')
  })

  it('throws when the API returns an error status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchHealth()).rejects.toThrow('Health check failed with status 503')
  })
})

describe('login', () => {
  const credentials = { email: 'ada@example.com', password: 'hunter2' }

  it('returns the session when the credentials are accepted', async () => {
    const body = { token: 'test-token', email: 'ada@example.com' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))

    await expect(login(credentials)).resolves.toMatchObject({
      token: 'test-token',
      email: 'ada@example.com',
    })
  })

  it('takes the role from the server', async () => {
    const body = { token: 't', email: 'ada@example.com', role: 'Coordinator' as const }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))

    await expect(login(credentials)).resolves.toMatchObject({ role: 'Coordinator' })
  })

  it('defaults to Organiser until the server issues a role', async () => {
    const body = { token: 't', email: 'ada@example.com' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))

    await expect(login(credentials)).resolves.toMatchObject({ role: 'Organiser' })
  })

  it('derives a display name from the email when the server sends none', async () => {
    const body = { token: 't', email: 'ada.lovelace@example.com' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body }))

    await expect(login(credentials)).resolves.toMatchObject({ name: 'Ada Lovelace' })
  })

  it('raises AuthError on 401 so the UI can distinguish a rejection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))

    await expect(login(credentials)).rejects.toBeInstanceOf(AuthError)
  })

  it('raises a plain error on a server fault, not AuthError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(login(credentials)).rejects.not.toBeInstanceOf(AuthError)
  })
})
