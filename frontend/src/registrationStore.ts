/**
 * Registration — US20.1.
 *
 * Two halves for two roles. The assigned Coordinator turns registration on for
 * an event and sets its capacity; an Attendee sees the Confirmed events taking
 * registrations and registers for one with a name and an email. The server
 * enforces every rule, the capacity under two people at once included; the
 * checks here only save a round trip.
 */

import { ApiError, authorizedFetch, type Session } from './api'
import { EventRuleError } from './eventsStore'

/** US20.1 AC1: whether the event takes registrations, how many, and how many it has. */
export type RegistrationSettings = {
  eventId: string
  open: boolean
  /** Null until a capacity was first set. */
  capacity: number | null
  registered: number
  placesLeft: number | null
  /** Where the capacity starts before one is set: the expected attendance. */
  defaultCapacity: number | null
}

/** US20.1 AC2: what an Attendee is shown of an event. Nothing of its planning. */
export type OpenEvent = {
  id: string
  title: string
  startsAt: string
  endsAt: string
  venues: string[]
  placesLeft: number
  /** The signed-in Attendee already has a place. */
  registered: boolean
}

export type RegistrationRecord = {
  id: string
  eventId: string
  name: string
  email: string
  status: 'Registered'
  createdAt: string
}

export type RegistrationForm = { name: string; email: string }

/** `events.registration_capacity` is INTEGER. */
export const REGISTRATION_CAPACITY_MAX = 2_147_483_647
/** `registrations.name` and `registrations.email` are VARCHAR(255). */
export const REGISTRATION_FIELD_MAX = 255

/** The server's sentence, so a refusal reads the same from either side. */
export const EVENT_FULL_MESSAGE = 'Event is full.'

/** Refusals the page shows where the user is: a 400, 403, 404 or 409. */
function asRuleError(error: unknown): never {
  if (error instanceof ApiError && [400, 403, 404, 409].includes(error.status)) {
    throw new EventRuleError(error.message)
  }
  throw error
}

export async function getRegistrationSettings(
  eventId: string,
  session: Session,
): Promise<RegistrationSettings> {
  const response = await authorizedFetch(`/events/${eventId}/registration`, session.token)
  return (await response.json()) as RegistrationSettings
}

/**
 * US20.1 AC1: turn registration on or off. Without a capacity, the server keeps
 * the stored one, or starts from the expected attendance the first time.
 */
export async function saveRegistrationSettings(
  eventId: string,
  settings: { open: boolean; capacity: number | null },
  session: Session,
): Promise<RegistrationSettings> {
  try {
    const response = await authorizedFetch(`/events/${eventId}/registration`, session.token, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    return (await response.json()) as RegistrationSettings
  } catch (error) {
    return asRuleError(error)
  }
}

/** US20.1 AC2: the Confirmed events taking registrations, soonest first. */
export async function listOpenEvents(session: Session): Promise<OpenEvent[]> {
  const response = await authorizedFetch('/attendee/events', session.token)
  return (await response.json()) as OpenEvent[]
}

/** US20.1 AC3/AC4: register. Full, already registered and closed come back as rule errors. */
export async function registerForEvent(
  eventId: string,
  form: RegistrationForm,
  session: Session,
): Promise<RegistrationRecord> {
  try {
    const response = await authorizedFetch(
      `/attendee/events/${eventId}/registrations`,
      session.token,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name.trim(), email: form.email.trim() }),
      },
    )
    return (await response.json()) as RegistrationRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * A capacity as typed: a whole number of places, at least 1. Null for an empty
 * box, which the server reads as "keep the stored one, or use the attendance".
 */
export function parseCapacity(text: string): number | null | 'invalid' {
  const trimmed = text.trim()
  if (trimmed === '') return null
  if (!/^\d+$/.test(trimmed)) return 'invalid'
  const value = Number(trimmed)
  return value >= 1 && value <= REGISTRATION_CAPACITY_MAX ? value : 'invalid'
}

/** Something, an @, and something with a dot in it — the server's own check. */
const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** US20.1 AC3: the form's problem, in the server's words, or null. One at a time. */
export function validateRegistration(form: RegistrationForm): string | null {
  const name = form.name.trim()
  const email = form.email.trim()
  if (!name) return 'Give your name.'
  if (name.length > REGISTRATION_FIELD_MAX) {
    return `Keep your name to ${REGISTRATION_FIELD_MAX} characters or fewer.`
  }
  if (!email) return 'Give your email address.'
  if (email.length > REGISTRATION_FIELD_MAX) {
    return `Keep your email address to ${REGISTRATION_FIELD_MAX} characters or fewer.`
  }
  if (!EMAIL_SHAPE.test(email)) return 'Give a valid email address, such as name@example.com.'
  return null
}

/** "1 place left", "12 places left", or the full message. */
export function describePlacesLeft(placesLeft: number): string {
  if (placesLeft <= 0) return EVENT_FULL_MESSAGE
  return placesLeft === 1 ? '1 place left' : `${placesLeft} places left`
}
