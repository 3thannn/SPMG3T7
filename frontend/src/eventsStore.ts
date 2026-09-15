/**
 * Event data access.
 *
 * This used to be a localStorage stand-in for endpoints that did not exist. The
 * endpoints exist now (`/events`), backed by Supabase, so every function here is
 * a thin call over `authorizedFetch` — the shape the module was always written
 * towards, which is why the pages above it did not have to move.
 *
 * The US4.2 rules are no longer enforced here. The server owns them: it decides
 * what you may see, refuses a second submit, and writes the timestamps. What is
 * left in the browser is `status.ts`, which mirrors the rules so the UI can
 * disable a button and say why — a courtesy, and no longer the only thing
 * standing between a user and a rule they can break.
 */

import { ApiError, authorizedFetch, type Session } from './api'
import type { EventStatus, StatusChange } from './status'

export type EventRecord = {
  id: string
  title: string
  /** `events.purpose`, nullable in the database — empty string when unset. */
  purpose: string
  description: string
  /** ISO-8601 when set; drafts may leave `events.proposed_date` null. */
  startsAt: string
  /**
  * `events.end_date`, optional for drafts. Empty for older drafts that predate
  * the end-date field; optional so fixtures and callers still type-check.
   */
  endsAt?: string
  /**
   * `events.expected_attendance`, nullable. null means nobody has estimated
   * yet, which the column keeps distinct from an estimate of zero.
   */
  expectedAttendance: number | null
  status: EventStatus
  organiserId: string
  organiserName: string
  createdAt: string
  updatedAt: string
  history: StatusChange[]
}

export type EventDraft = {
  title: string
  purpose: string
  description: string
  startsAt: string
  endsAt?: string | null
  expectedAttendance: number | null
}

/**
 * Read an attendance field: the number the database will hold, or null for
 * "not estimated yet". The column is nullable, so an empty field means unknown
 * rather than nobody, and 'invalid' is anything that is not a whole number.
 */
export function parseAttendance(raw: string): number | null | 'invalid' {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (!/^\d+$/.test(trimmed)) return 'invalid'
  return Number(trimmed)
}

/** An attendance value as the form shows it — null becomes an empty field. */
export function attendanceField(value: number | null): string {
  return value === null ? '' : String(value)
}

/** Raised when a write is refused by a business rule, e.g. a second submit. */
export class EventRuleError extends Error {}

/**
 * Turn the API's refusals into the one error the pages already handle.
 *
 * A 409 is a rule saying no (submitted twice, not a Draft) and a 400 is the
 * request being incomplete. Both are things to show the user in the page they
 * are already on, unlike a 401, which has to bubble up and end the session.
 */
function asRuleError(error: unknown): never {
  if (error instanceof ApiError && (error.status === 409 || error.status === 400)) {
    throw new EventRuleError(error.message)
  }
  if (error instanceof ApiError && error.status === 403) {
    throw new EventRuleError(error.message)
  }
  throw error
}

/**
 * US4.1: an Organiser gets the events they own, a Coordinator gets all of them.
 *
 * The role is not passed — the server reads it from the session. A client that
 * asked for "all events" could simply ask, which is the bug this avoids.
 */
export async function listEvents(session: Session): Promise<EventRecord[]> {
  const response = await authorizedFetch('/events', session.token)
  return (await response.json()) as EventRecord[]
}

/** The event, or null when it does not exist or is not this caller's to see. */
export async function getEvent(id: string, session: Session): Promise<EventRecord | null> {
  try {
    const response = await authorizedFetch(`/events/${id}`, session.token)
    return (await response.json()) as EventRecord
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

/** US4.2: a new event always begins as a Draft. */
export async function createEvent(
  draft: EventDraft,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch('/events', session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US4.2: saving edits content and never moves the status. */
export async function saveEvent(
  id: string,
  draft: EventDraft,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}`, session.token, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US4.2: Draft -> Submitted, once. A second submit comes back as a refusal. */
export async function submitEvent(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/submit`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}
