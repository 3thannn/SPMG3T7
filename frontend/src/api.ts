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
export type Session = { token: string; email: string }

/** Thrown when the server rejects the credentials, as opposed to failing outright. */
export class AuthError extends Error {}

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
  return (await response.json()) as Session
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${apiBaseUrl()}/health`)
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return (await response.json()) as Health
}
