export type Health = { status: string }

/**
 * Base URL of the SPMG3T7 backend. Override with VITE_API_BASE_URL; the default
 * matches the uvicorn dev server documented in the backend README.
 */
export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  return (configured ?? 'http://localhost:8000').replace(/\/$/, '')
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${apiBaseUrl()}/health`)
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return (await response.json()) as Health
}
