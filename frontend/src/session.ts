/**
 * Where the signed-in session lives between page loads.
 *
 * Only the token is worth anything, and it is worth nothing on its own: the
 * server is asked who it belongs to on every load (`fetchMe`), so a stored
 * session that has been signed out or has lapsed comes back as no session at
 * all. The rest of the record is cached alongside it purely so the header can
 * render a name and role in the same frame rather than flashing empty.
 *
 * localStorage rather than a cookie because the API is on another origin in
 * development and is called with an explicit Authorization header, so there is
 * no cookie to send. Note this leaves the token readable by any script on the
 * page: the exchange that makes that safe is a same-origin, HttpOnly cookie,
 * and it is worth revisiting when the two halves are deployed together (US6.4).
 */

import type { Session } from './api'

const STORAGE_KEY = 'spmg3t7.session.v1'

/** The stored session, or null if there is none and if storage is unusable. */
export function loadStoredSession(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw) as Partial<Session> | null
    if (!parsed || typeof parsed.token !== 'string' || !parsed.token) return null
    if (typeof parsed.role !== 'string' || !Array.isArray(parsed.permissions)) return null

    return parsed as Session
  } catch {
    // A private window, cleared site data, or a half-written record. Signed out
    // is the correct reading of all three.
    return null
  }
}

export function storeSession(session: Session): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Non-fatal: the session works until the tab is closed, it just will not
    // survive a reload.
  }
}

export function clearStoredSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing useful to do — the session has already been dropped in memory.
  }
}
