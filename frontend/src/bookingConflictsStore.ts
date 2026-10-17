/**
 * Venue Staff review bookings flagged "Conflict – review needed" — US15.2.
 *
 * When a venue's setup or turnaround time changes, bookings that now clash are
 * flagged rather than cancelled, and their Coordinators are notified. This is
 * the list Venue Staff work from. Each flagged booking comes with what it
 * clashes with right now, under US15.1's rule, and the flag clears on its own
 * once the clash is resolved, so the list only ever holds live problems.
 */

import { authorizedFetch, type Session } from './api'
import type { BookingRequest } from './bookingRequestsStore'

/** A flagged booking as Venue Staff review it: the same facts as a request. */
export type FlaggedBooking = BookingRequest & {
  /** Always "Conflict – review needed". */
  label: string
}

export async function listBookingConflicts(session: Session): Promise<FlaggedBooking[]> {
  const response = await authorizedFetch('/booking-conflicts', session.token)
  return (await response.json()) as FlaggedBooking[]
}
