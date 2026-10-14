import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  AuthError,
  ForbiddenError,
  SessionExpiredError,
  apiBaseUrl,
  authorizedFetch,
  fetchHealth,
  fetchMe,
  login,
  logout,
  unexpectedFailureMessage,
} from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

/** What POST /auth/login answers with for the development Organiser. */
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

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body }
}

function failure(status: number, code?: string, message?: string) {
  return {
    ok: false,
    status,
    json: async () => (code ? { detail: { code, message } } : {}),
  }
}

describe('apiBaseUrl', () => {
  it('falls back to the local backend', () => {
    expect(apiBaseUrl()).toBe('http://localhost:8000')
  })
})

describe('fetchHealth', () => {
  it('returns the parsed payload when the API responds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ status: 'ok' })))

    await expect(fetchHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/health')
  })

  it('throws when the API returns an error status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchHealth()).rejects.toThrow('Health check failed with status 503')
  })
})

describe('login', () => {
  const credentials = { email: 'organiser@spmg3t7.edu', password: 'Sprint1!demo' }

  it('posts the credentials to the sign-in route', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok(SESSION_BODY))
    vi.stubGlobal('fetch', fetchMock)

    await login(credentials)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(credentials)
  })

  it('returns the session the server issued', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(SESSION_BODY)))

    await expect(login(credentials)).resolves.toEqual({
      token: 'test-token',
      id: 'user_organiser',
      email: 'organiser@spmg3t7.edu',
      name: 'Dylan',
      role: 'Event Organiser',
      permissions: ['events:create', 'events:read:own', 'events:submit'],
      home: '/events',
      idleMinutes: 30,
    })
  })

  it('takes the role from the server rather than anywhere else', async () => {
    const body = { ...SESSION_BODY, role: 'Event Coordinator', permissions: ['events:review'] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(body)))

    await expect(login(credentials)).resolves.toMatchObject({
      role: 'Event Coordinator',
      permissions: ['events:review'],
    })
  })

  it('uses whatever landing route the server sends, without deciding for itself', async () => {
    // Deliberately a route the client does not know about: the point is that
    // the destination travels with the session rather than being hardcoded, so
    // a role with its own workspace needs no change here.
    const body = { ...SESSION_BODY, role: 'Event Coordinator', home: '/review' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(body)))

    await expect(login(credentials)).resolves.toMatchObject({ home: '/review' })
  })

  it('refuses a response with no role instead of assuming one', async () => {
    // Guessing here would be the client deciding what its user may do.
    const { role: _role, ...withoutRole } = SESSION_BODY
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(withoutRole)))

    await expect(login(credentials)).rejects.toThrow(/does not recognise/)
  })

  it('refuses a response with no permissions', async () => {
    const { permissions: _permissions, ...withoutPermissions } = SESSION_BODY
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(withoutPermissions)))

    await expect(login(credentials)).rejects.toThrow(/does not recognise/)
  })

  it('refuses a response with no token', async () => {
    const { token: _token, ...withoutToken } = SESSION_BODY
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(withoutToken)))

    await expect(login(credentials)).rejects.toThrow(/does not recognise/)
  })

  it('raises AuthError on 401 so the form can name the real problem', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(failure(401, 'invalid_credentials', 'Incorrect email or password.')),
    )

    const error = await login(credentials).catch((thrown: unknown) => thrown)
    expect(error).toBeInstanceOf(AuthError)
    expect((error as AuthError).message).toBe('Incorrect email or password.')
  })

  it('raises a plain error on a server fault, not AuthError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(500)))

    await expect(login(credentials)).rejects.not.toBeInstanceOf(AuthError)
  })

  it('lets a connection failure through as itself', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(login(credentials)).rejects.toBeInstanceOf(TypeError)
  })
})

describe('logout', () => {
  it('sends the token so the server can end that session', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 })
    vi.stubGlobal('fetch', fetchMock)

    await logout('test-token')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/auth/logout')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer test-token')
  })

  it('never throws, so a sign-out is not blocked by an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(logout('test-token')).resolves.toBeUndefined()
  })
})

describe('fetchMe', () => {
  it('returns the session the token belongs to', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(SESSION_BODY)))

    await expect(fetchMe('test-token')).resolves.toMatchObject({
      id: 'user_organiser',
      role: 'Event Organiser',
      token: 'test-token',
    })
  })

  it('reports an expired session distinctly from a rejected one', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(failure(401, 'session_expired', 'Your session expired.')),
    )

    const error = await fetchMe('stale').catch((thrown: unknown) => thrown)
    expect(error).toBeInstanceOf(SessionExpiredError)
    expect(error).not.toBeInstanceOf(AuthError)
  })

  it('reports a revoked token as simply not authenticated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(failure(401, 'not_authenticated', 'Your session is no longer valid.')),
    )

    const error = await fetchMe('revoked').catch((thrown: unknown) => thrown)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).not.toBeInstanceOf(SessionExpiredError)
    expect((error as ApiError).code).toBe('not_authenticated')
  })
})

describe('authorizedFetch', () => {
  it('shows the field named by a validation error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 422,
      json: async () => ({ detail: [{ loc: ['body', 'totalQuantity'], msg: 'Input should be a valid integer' }] }),
    }))
    await expect(authorizedFetch('/equipment', 'test-token')).rejects.toThrow(
      'totalQuantity: Input should be a valid integer.',
    )
  })
  it('carries the session token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({}))
    vi.stubGlobal('fetch', fetchMock)

    await authorizedFetch('/auth/users', 'test-token')

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer test-token')
  })

  it('turns a 403 into a ForbiddenError carrying the server explanation', async () => {
    const message = 'The Organiser role cannot view the user directory.'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(failure(403, 'forbidden', message)))

    const error = await authorizedFetch('/auth/users', 'test-token').catch(
      (thrown: unknown) => thrown,
    )
    expect(error).toBeInstanceOf(ForbiddenError)
    expect((error as ForbiddenError).message).toBe(message)
  })

  it('still classifies a refusal when the body is not the expected shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => 'nope' }))

    await expect(authorizedFetch('/auth/users', 'test-token')).rejects.toBeInstanceOf(
      ForbiddenError,
    )
  })

  it('survives a response that is not JSON at all', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError('Unexpected token <')
        },
      }),
    )

    await expect(authorizedFetch('/auth/me', 'test-token')).rejects.toThrow(
      'Request failed with status 502.',
    )
  })
})

describe('unexpectedFailureMessage', () => {
  it('points at the backend log when the API answered and failed', () => {
    // The case that sent a real person looking in the wrong place: the API was
    // running and answering 500, and the message told them to check it was
    // running. The status is what makes the difference legible.
    const message = unexpectedFailureMessage(
      new ApiError('Request failed with status 500.', 'unknown', 500),
      'save this venue',
    )

    expect(message).toContain('HTTP 500')
    expect(message).toContain('backend log')
    expect(message).not.toContain('could not be reached')
  })

  it('says the API is unreachable when the request never landed', () => {
    const message = unexpectedFailureMessage(new TypeError('fetch failed'), 'save this venue')

    expect(message).toContain('could not be reached')
    expect(message).not.toContain('HTTP')
  })

  it('completes the sentence with what was being attempted', () => {
    expect(unexpectedFailureMessage(new Error('x'), 'delete this venue')).toContain(
      'Could not delete this venue',
    )
  })

  it('reports a 403 as an answer rather than as unreachable', () => {
    const message = unexpectedFailureMessage(
      new ForbiddenError('Not your role.'),
      'send the request',
    )

    expect(message).toContain('HTTP 403')
  })
})
