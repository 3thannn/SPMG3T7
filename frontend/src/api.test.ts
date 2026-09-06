import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiBaseUrl, fetchHealth } from './api'

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
