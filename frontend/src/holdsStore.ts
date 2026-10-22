/**
 * Tentative venue holds — US14.3.
 *
 * Venue Staff keep a venue's slot for an event's Coordinator until an expiry,
 * so it is kept while they finalise without blocking the venue forever. The
 * hold is a booking with status Held; the Coordinator turns it into a request
 * from the event page (`requestHeldBooking` in eventsStore).
 */

import { ApiError, authorizedFetch, type Session } from './api'
import { EventRuleError, type BookingRecord } from './eventsStore'
import type { EventStatus } from './status'

/** An event a hold can be placed for: assigned, and Approved or Planning. */
export type HoldableEvent = {
  id: string
  title: string
  status: EventStatus
  coordinatorName: string
  startsAt: string
  endsAt: string
}

/** A hold, with its event's title: Venue Staff cannot open events. */
export type HoldRecord = BookingRecord & { eventTitle: string }

/** The hold form, as typed. Times are datetime-local values. */
export type HoldInput = {
  eventId: string
  startsAt: string
  endsAt: string
  expiresAt: string
}

export const EMPTY_HOLD: HoldInput = { eventId: '', startsAt: '', endsAt: '', expiresAt: '' }

/** "YYYY-MM-DDTHH:MM" for now, in the viewer's own clock, as a datetime-local value. */
export function nowLocal(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}`
  )
}

/**
 * The first problem with a hold as a sentence, or ''. The server checks the
 * same rules; this only saves a round trip. `now` is a datetime-local value.
 */
export function validateHold(input: HoldInput, now: string = nowLocal()): string {
  if (!input.eventId) return 'Choose the event to hold this venue for.'
  if (!input.startsAt) return 'Give the booking a start time.'
  if (!input.endsAt) return 'Give the booking an end time.'
  if (input.endsAt <= input.startsAt) return 'The booking must end after it starts.'
  if (!input.expiresAt) return 'Give the hold an expiry date and time.'
  if (input.expiresAt <= now) return 'The hold must expire in the future.'
  if (input.expiresAt > input.startsAt) {
    return 'The hold must expire no later than the booking starts.'
  }
  return ''
}

function asRuleError(error: unknown): never {
  if (error instanceof ApiError && [400, 403, 409].includes(error.status)) {
    throw new EventRuleError(error.message)
  }
  throw error
}

export async function listHoldableEvents(session: Session): Promise<HoldableEvent[]> {
  const response = await authorizedFetch('/holds/events', session.token)
  return (await response.json()) as HoldableEvent[]
}

/** The holds at one venue, soonest first, expired ones flagged. */
export async function listHolds(venueId: string, session: Session): Promise<HoldRecord[]> {
  const response = await authorizedFetch(
    `/holds?venueId=${encodeURIComponent(venueId)}`,
    session.token,
  )
  return (await response.json()) as HoldRecord[]
}

export async function placeHold(
  venueId: string,
  input: HoldInput,
  session: Session,
): Promise<HoldRecord> {
  try {
    const response = await authorizedFetch('/holds', session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ venueId, ...input }),
    })
    return (await response.json()) as HoldRecord
  } catch (error) {
    return asRuleError(error)
  }
}
