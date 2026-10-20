import type { Role } from './status'

export type Health = { status: string }

/**
 * Base URL of the SPMG3T7 backend. Override with VITE_API_BASE_URL; the default
 * matches the uvicorn dev server documented in the backend README.
 */
export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  return (configured ?? 'http://localhost:8000').replace(/\/$/, '')
}

export type Credentials = { email: string; password: string }

/** One thing a role may do. The server owns the list; this mirrors its names. */
export type Permission =
  | 'events:create'
  | 'events:read:own'
  | 'events:read:submitted'
  | 'events:read:all'
  | 'events:submit'
  | 'events:review'
  | 'events:complete'
  | 'events:edit'
  | 'users:read'
  | 'venues:read'
  | 'venues:create'
  | 'venues:edit'
  | 'venues:delete'
  | 'notifications:read'
  | 'bookings:request'
  | 'queue:view:unassigned'
  | 'coordinators:assign'
  | 'safety:review'
  | 'safety:submit'
  | 'equipment:read'
  | 'equipment:write'
  | 'equipment:request'
  | 'equipment:queue'
  | 'holds:place'
  | 'bookings:decide'

/**
 * The signed-in user, exactly as the server issued it.
 *
 * Role and permissions belong to the account, so they are never chosen in the
 * browser and never defaulted here — a client that guessed a role would be
 * guessing what the user is allowed to do. `home` is where this role lands
 * after signing in (US1.1), and `idleMinutes` is the inactivity window, so the
 * browser and the server time out together rather than a few minutes apart.
 */
export type Session = {
  token: string
  id: string
  email: string
  name: string
  role: Role
  permissions: Permission[]
  home: string
  idleMinutes: number
}

/** Why a request was turned away, as sent by the API. */
export type ErrorCode =
  | 'invalid_credentials'
  | 'not_authenticated'
  | 'session_expired'
  | 'forbidden'
  | 'unknown'

export class ApiError extends Error {
  code: ErrorCode
  status: number

  constructor(message: string, code: ErrorCode, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** The credentials were wrong — distinct from every other way a request fails. */
export class AuthError extends ApiError {
  constructor(message = 'Incorrect email or password.', status = 401) {
    super(message, 'invalid_credentials', status)
    this.name = 'AuthError'
  }
}

/** The session lapsed through inactivity: the user was signed in, and now is not. */
export class SessionExpiredError extends ApiError {
  constructor(message: string, status = 401) {
    super(message, 'session_expired', status)
    this.name = 'SessionExpiredError'
  }
}

/** Signed in, but this role may not do it. Signing in again will not help (US1.3). */
export class ForbiddenError extends ApiError {
  constructor(message: string, status = 403) {
    super(message, 'forbidden', status)
    this.name = 'ForbiddenError'
  }
}

type ValidationIssue = { loc?: Array<string | number>; msg?: string }
type ErrorBody = { detail?: { code?: string; message?: string } | string | ValidationIssue[] }

/** Pull the API's {detail: {code, message}} out of a response, whatever it sent. */
async function readError(response: Response): Promise<{ code: ErrorCode; message: string }> {
  let code: ErrorCode = 'unknown'
  let message = ''

  try {
    const body = (await response.json()) as ErrorBody
    if (typeof body.detail === 'string') {
      message = body.detail
    } else if (Array.isArray(body.detail)) {
      const first = body.detail[0]
      if (first) message = `${String(first.loc?.at(-1) ?? 'Field')}: ${first.msg ?? 'invalid value'}.`
    } else if (body.detail) {
      code = (body.detail.code as ErrorCode) ?? 'unknown'
      message = body.detail.message ?? ''
    }
  } catch {
    // A proxy or a crash can answer with HTML; fall through to a generic message.
  }

  if (code === 'unknown' && response.status === 401) code = 'not_authenticated'
  if (code === 'unknown' && response.status === 403) code = 'forbidden'

  return { code, message: message || `Request failed with status ${response.status}.` }
}

function toApiError(status: number, code: ErrorCode, message: string): ApiError {
  if (code === 'invalid_credentials') return new AuthError(message, status)
  if (code === 'session_expired') return new SessionExpiredError(message, status)
  if (code === 'forbidden') return new ForbiddenError(message, status)
  return new ApiError(message, code, status)
}

const MALFORMED = 'The server sent a sign-in response this app does not recognise.'

/**
 * Turn a payload into a Session, or refuse it.
 *
 * There is deliberately no default role here. Filling in a missing role would
 * be the client deciding what its user is allowed to do, and the safe-looking
 * default is still a guess — so a payload without one is a fault, not a session.
 */
function toSession(body: unknown, token: string): Session {
  const identity = body as Partial<Session> | null
  if (
    !identity ||
    typeof identity.id !== 'string' ||
    typeof identity.email !== 'string' ||
    typeof identity.name !== 'string' ||
    typeof identity.role !== 'string' ||
    !Array.isArray(identity.permissions)
  ) {
    throw new Error(MALFORMED)
  }

  return {
    token,
    id: identity.id,
    email: identity.email,
    name: identity.name,
    role: identity.role,
    permissions: identity.permissions,
    home: identity.home ?? '/events',
    idleMinutes: identity.idleMinutes ?? 30,
  }
}

/** US1.1: exchange credentials for a session. */
export async function login({ email, password }: Credentials): Promise<Session> {
  const response = await fetch(`${apiBaseUrl()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    const { code, message } = await readError(response)
    // A 401 from the sign-in form is always a rejected credential, whatever the
    // body says, so the form can be certain of what to tell the user.
    if (response.status === 401) throw new AuthError(message)
    throw toApiError(response.status, code, message)
  }

  const body = (await response.json()) as { token?: string }
  if (typeof body.token !== 'string' || !body.token) throw new Error(MALFORMED)
  return toSession(body, body.token)
}

/**
 * US1.2: end the session on the server so the token stops working at once.
 *
 * Never throws. A sign-out that failed because the network was down must still
 * clear the session in the browser — staying signed in because the server could
 * not be told is the wrong way to fail.
 */
export async function logout(token: string): Promise<void> {
  try {
    await fetch(`${apiBaseUrl()}/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    // Swallowed deliberately; the caller clears the session either way.
  }
}

/**
 * Who the server says this token belongs to.
 *
 * Called on load to revive a stored session. A token revoked by a sign-out, or
 * one that lapsed while the tab was closed, fails here — which is what
 * "subsequent requests require re-authentication" amounts to in practice.
 */
export async function fetchMe(token: string): Promise<Session> {
  const response = await authorizedFetch('/auth/me', token)
  return toSession(await response.json(), token)
}

/**
 * A fetch that carries the session and turns the API's refusals into the error
 * types the UI reacts to differently. Every authenticated call should go
 * through here rather than reaching for `fetch` directly.
 */
export async function authorizedFetch(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    const { code, message } = await readError(response)
    throw toApiError(response.status, code, message)
  }
  return response
}

/**
 * A message for a failure the page could not handle as a business rule.
 *
 * Distinguishes the two cases that call for opposite responses from whoever
 * reads it: the API answered and failed (a server fault — the status and the
 * backend log are where the cause is), versus the API could not be reached at
 * all. Telling someone to check the API is running when it is running and
 * answering 500 sends them looking in exactly the wrong place.
 *
 * `doing` completes the sentence "Could not ..." — e.g. "save this venue".
 */
export function unexpectedFailureMessage(error: unknown, doing: string): string {
  if (error instanceof ApiError) {
    return `Could not ${doing}. The API answered HTTP ${error.status} — check the backend log for the cause.`
  }
  return `Could not ${doing}. The API could not be reached; check it is running and try again.`
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${apiBaseUrl()}/health`)
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return (await response.json()) as Health
}
