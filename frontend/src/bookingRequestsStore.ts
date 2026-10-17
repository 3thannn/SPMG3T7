/**
 * Venue Staff decide venue booking requests — US16.1.
 *
 * The queue is every Requested booking, oldest first, with the full occupied
 * window including setup and turnaround (US9.4) and anything it already
 * clashes with. Approving confirms it unless the slot is taken by then;
 * rejecting needs a reason and may suggest an alternative.
 */

import { ApiError, authorizedFetch, type Session } from './api'
import { EventRuleError, type BookingRecord } from './eventsStore'

/** A booking already taking a slot that overlaps this one. */
export type BookingClash = {
  bookingId: string
  eventTitle: string
  status: BookingRecord['status']
  startsAt: string
  endsAt: string
  occupiedFrom: string
  occupiedTo: string
}

/** US15.1: a venue unavailability period (US12.1) a booking overlaps. */
export type UnavailablePeriod = {
  id: string
  /** "YYYY-MM-DD", inclusive at both ends. */
  startDate: string
  endDate: string
  reason: string
}

/** "2027-11-02" for one day, "2027-11-01 to 2027-11-03" for several, with any reason. */
export function describePeriod(period: UnavailablePeriod): string {
  const span =
    period.startDate === period.endDate
      ? period.startDate
      : `${period.startDate} to ${period.endDate}`
  return period.reason ? `${span} (${period.reason})` : span
}

/** A booking as Venue Staff decide it: they cannot open the event itself. */
export type BookingRequest = BookingRecord & {
  eventTitle: string
  coordinatorName: string
  /** The full occupied window: start minus setup, end plus turnaround. */
  occupiedFrom: string
  occupiedTo: string
  setupMinutes: number
  turnaroundMinutes: number
  /** Approval is blocked while any remain. */
  clashes: BookingClash[]
  /**
   * US15.1: unavailability periods it overlaps. Approval is blocked by these
   * too. Optional so an older server's answer reads as none.
   */
  unavailable?: UnavailablePeriod[]
}

/** The server's cap on a reason or suggestion, mirrored so the form can say so. */
export const DECISION_TEXT_MAX = 2000

function asRuleError(error: unknown): never {
  if (error instanceof ApiError && [400, 403, 409].includes(error.status)) {
    throw new EventRuleError(error.message)
  }
  throw error
}

export async function listBookingRequests(session: Session): Promise<BookingRequest[]> {
  const response = await authorizedFetch('/booking-requests', session.token)
  return (await response.json()) as BookingRequest[]
}

export async function approveBookingRequest(
  bookingId: string,
  session: Session,
): Promise<BookingRequest> {
  try {
    const response = await authorizedFetch(`/booking-requests/${bookingId}/approve`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as BookingRequest
  } catch (error) {
    return asRuleError(error)
  }
}

export async function rejectBookingRequest(
  bookingId: string,
  reason: string,
  suggestion: string,
  session: Session,
): Promise<BookingRequest> {
  try {
    const response = await authorizedFetch(`/booking-requests/${bookingId}/reject`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason, suggestion }),
    })
    return (await response.json()) as BookingRequest
  } catch (error) {
    return asRuleError(error)
  }
}
