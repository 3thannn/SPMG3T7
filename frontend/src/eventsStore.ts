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
import { formatTimestamp, type EventStatus, type StatusChange } from './status'

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
 * US4.1: an Organiser gets their events; a Coordinator gets non-Draft requests.
 *
 * The role is not passed — the server reads it from the session. A client that
 * asked for "submitted events" could simply ask, which is the bug this avoids.
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

/**
 * US7.3: attach a message asking the Organiser for information or changes.
 *
 * Moves the event to Under Review and adds the message to its history, which is
 * where the Organiser reads it. Their reply is US11.1 and is not modelled here.
 */
export async function requestClarification(
  id: string,
  message: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/clarification`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US7.1: approve an assigned event that is currently Under Review. */
export async function approveEvent(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/approve`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US7.1: reject an assigned event and make the reason visible in its history. */
export async function rejectEvent(
  id: string,
  reason: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/reject`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * US14.1: one venue requested for an event. An event may have many, such as a
 * main hall and its breakout rooms, and each is its own record.
 */
export type BookingRecord = {
  id: string
  eventId: string
  venueId: string
  venueName: string
  /** Naive local times, "YYYY-MM-DDTHH:MM" or with seconds once stored. */
  startsAt: string
  endsAt: string
  /** Every new booking waits on Venue Staff; their approval is a later epic. */
  status: 'Requested'
  requestedAt: string
}

/** What the Coordinator's form sends — the values of its three inputs. */
export type BookingInput = {
  venueId: string
  startsAt: string
  endsAt: string
}

/**
 * US14.1: the first problem with a booking request as a sentence, or ''.
 *
 * The server checks again; this is so the form can say what is wrong without a
 * round trip. datetime-local values sort as text in time order, so they are
 * compared as strings, as the event form compares its own.
 */
export function validateBooking(input: BookingInput): string {
  if (!input.venueId.trim()) return 'Choose a venue.'
  if (!input.startsAt.trim()) return 'Give the booking a start time.'
  if (!input.endsAt.trim()) return 'Give the booking an end time.'
  if (input.endsAt <= input.startsAt) return 'The booking must end after it starts.'
  return ''
}

/**
 * "2 Nov 2027, 09:00 – 17:00" for a booking within one day; both ends in full
 * when it runs past midnight, so an overnight booking cannot be misread.
 */
export function formatBookingTimes(startsAt: string, endsAt: string): string {
  const start = formatTimestamp(startsAt)
  if (startsAt.slice(0, 10) !== endsAt.slice(0, 10)) {
    return `${start} – ${formatTimestamp(endsAt)}`
  }
  const end = new Date(endsAt)
  if (Number.isNaN(end.getTime())) return `${start} – ${endsAt}`
  return `${start} – ${end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`
}

/** US14.1: every venue booking for the event, soonest first — the server's order. */
export async function listBookings(eventId: string, session: Session): Promise<BookingRecord[]> {
  const response = await authorizedFetch(`/events/${eventId}/bookings`, session.token)
  return (await response.json()) as BookingRecord[]
}

/**
 * US14.1: request one venue for the event. Each call stands alone, so a refused
 * breakout room leaves the main hall already requested.
 */
export async function requestBooking(
  eventId: string,
  input: BookingInput,
  session: Session,
): Promise<BookingRecord> {
  try {
    const response = await authorizedFetch(`/events/${eventId}/bookings`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return (await response.json()) as BookingRecord
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
