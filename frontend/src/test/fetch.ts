/**
 * A stand-in for `fetch`, for testing the API clients.
 *
 * Each store test used to define its own `ok`, `failure` and `stubFetch`; these
 * are the same three, shared. `stubFetch` returns the spy so a test can read the
 * URL and request it was called with.
 */

import { vi } from 'vitest'

export function ok(body: unknown = null, status = 200) {
  return { ok: true, status, json: async () => body }
}

export function failure(status: number, message = 'Refused.', code = 'refused') {
  return { ok: false, status, json: async () => ({ detail: { code, message } }) }
}

export function stubFetch(response: unknown) {
  const spy = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', spy)
  return spy
}

/** The path, method and parsed body of the one call the spy received. */
export function sent(spy: ReturnType<typeof stubFetch>) {
  const [url, init = {}] = spy.mock.calls[0] as [string, RequestInit | undefined]
  return {
    path: url.replace(/^https?:\/\/[^/]+/, ''),
    method: init.method ?? 'GET',
    body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
  }
}
