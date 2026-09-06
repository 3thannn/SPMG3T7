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

/**
 * The signed-in user.
 *
 * `id` and `role` drive US4.1 visibility: an Organiser sees the events they
 * own, a Coordinator sees all of them. Role belongs to the account, so it comes
 * from the server — it is never something the user picks at sign-in. Until the
 * server issues one, sessions default to Organiser.
 */
export type Session = {
  token: string
  email: string
  id: string
  name: string
  role: Role
}

/** Thrown when the server rejects the credentials, as opposed to failing outright. */
export class AuthError extends Error {}

/** Organiser is the primary Sprint 1 actor, so it is the assumption until auth ships. */
const DEFAULT_ROLE: Role = 'Organiser'

type LoginResponse = { token: string; email: string; id?: string; name?: string; role?: Role }

/** Derives a display name from an email until the server sends a real one. */
function nameFromEmail(email: string): string {
  const local = email.split('@')[0] ?? email
  const cleaned = local.replace(/[._-]+/g, ' ').trim()
  return cleaned ? cleaned.replace(/\b\w/g, (c) => c.toUpperCase()) : email
}

export async function login({ email, password }: Credentials): Promise<Session> {
  const response = await fetch(`${apiBaseUrl()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (response.status === 401) {
    throw new AuthError('Incorrect email or password.')
  }
  if (!response.ok) {
    throw new Error(`Login failed with status ${response.status}`)
  }

  const body = (await response.json()) as LoginResponse
  return {
    token: body.token,
    email: body.email,
    id: body.id ?? `user_${body.email}`,
    name: body.name ?? nameFromEmail(body.email),
    role: body.role ?? DEFAULT_ROLE,
  }
}

/**
 * Sprint 1 stand-in for a signed-in session.
 *
 * The backend has no /auth/login route yet, so the sign-in page offers this as
 * an explicit, clearly-labelled choice when the real call cannot connect. It is
 * never used silently — the user has to pick it. Delete this once auth ships.
 */
export function previewSession(name = 'Dylan'): Session {
  // The seeded events in eventsStore are owned by this id, so the preview
  // session sees them as its own.
  return {
    token: 'preview',
    email: `${name.toLowerCase()}@example.edu`,
    id: 'user_organiser',
    name,
    role: DEFAULT_ROLE,
  }
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${apiBaseUrl()}/health`)
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return (await response.json()) as Health
}
