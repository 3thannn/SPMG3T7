/**
 * Tentative venue holds — US14.3 and US14.6.
 *
 * Week 9: a hold starts after venue approval. Venue Staff approve a booking
 * request as a hold with an expiry (`approveBookingRequest` with `holdUntil`
 * in bookingRequestsStore), and the Coordinator confirms it from the event
 * page (`confirmHeldBooking` in eventsStore) before it lapses. Here Venue
 * Staff list a venue's holds, change a hold's expiry, or release it early.
 */

import { ApiError, authorizedFetch, type Session } from './api'
import { EventRuleError, type BookingRecord } from './eventsStore'

/** A hold, with its event's title: Venue Staff cannot open events. */
export type HoldRecord = BookingRecord & { eventTitle: string }

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
 * The first problem with a hold's expiry as a sentence, or ''. The server
 * checks the same rules; this only saves a round trip. `startsAt` is the
 * booking's start and `now` a datetime-local value.
 */
export function validateExpiry(expiresAt: string, startsAt: string, now: string = nowLocal()): string {
  if (!expiresAt) return 'Give the hold an expiry date and time.'
  if (expiresAt <= now) return 'The hold must expire in the future.'
  if (expiresAt > startsAt.slice(0, 16)) {
    return 'The hold must expire no later than the booking starts.'
  }
  return ''
}

function asRuleError(error: unknown): never {
  if (error instanceof ApiError && [400, 403, 404, 409].includes(error.status)) {
    throw new EventRuleError(error.message)
  }
  throw error
}

/** The holds at one venue, soonest first, expired ones flagged. */
export async function listHolds(venueId: string, session: Session): Promise<HoldRecord[]> {
  const response = await authorizedFetch(
    `/holds?venueId=${encodeURIComponent(venueId)}`,
    session.token,
  )
  return (await response.json()) as HoldRecord[]
}

/** US14.6: give a hold a new expiry, longer or shorter. */
export async function updateHold(
  holdId: string,
  expiresAt: string,
  session: Session,
): Promise<HoldRecord> {
  try {
    const response = await authorizedFetch(`/holds/${holdId}`, session.token, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expiresAt }),
    })
    return (await response.json()) as HoldRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US14.6: release a hold before it expires, with a reason for the Coordinator. */
export async function releaseHold(
  holdId: string,
  reason: string,
  session: Session,
): Promise<HoldRecord> {
  try {
    const response = await authorizedFetch(`/holds/${holdId}/release`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    return (await response.json()) as HoldRecord
  } catch (error) {
    return asRuleError(error)
  }
}
