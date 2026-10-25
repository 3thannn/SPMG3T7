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
import type { EventNeeds } from './eventNeeds'

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
  /** US8.1: The assigned Event Coordinator's ID, or null if unassigned. */
  coordinatorId?: string | null
  /** US8.4: The assigned Event Coordinator's name, or empty if unassigned. */
  coordinatorName?: string
  history: StatusChange[]
  /**
   * US11.1: the "change requested" flag — set while the Organiser's proposed
   * changes await the Coordinator's review. Optional so older payloads and
   * fixtures still type-check; absent means no request.
   */
  changeRequested?: boolean
  changeRequestNote?: string
  /** US11.1: what the Organiser has asked for, in form order. */
  pendingChanges?: ProposedChange[]
  /** US11.1: the Coordinator's answer to the most recent request, if any. */
  lastChangeReview?: ChangeReview | null
} & Partial<EventNeeds>

/** US11.1: how a Coordinator answered a change request. */
export type ChangeReview = {
  outcome: 'approved' | 'rejected'
  at: string
  /** The rejection reason. Empty for an approval. */
  note: string
  /** The Organiser's note on the request that received this answer. */
  requestNote?: string
}

/** One field of a US11.1 change request, as the server describes it. */
export type ProposedChange = {
  /** The `events` column, e.g. `proposed_date`. */
  field: string
  /** The edit form's label for it, e.g. "Starts". */
  label: string
  /** Text as stored; empty means "not set". */
  oldValue: string
  newValue: string
  /** US5.2's rule: date/time, attendance, venue and equipment are important. */
  important: boolean
}

/**
 * US2.1 (Sprint 3): the needs are optional here so a caller that predates them
 * still type-checks; the forms always send all five.
 */
export type EventDraft = {
  title: string
  purpose: string
  description: string
  startsAt: string
  endsAt?: string | null
  expectedAttendance: number | null
} & Partial<EventNeeds>

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

/** US4.5: close an assigned Confirmed event after its end time. */
export async function completeEvent(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/complete`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** The server's cap on a reason for cancelling an event (US4.6). */
export const EVENT_CANCELLATION_REASON_MAX = 2000

/**
 * US4.6: cancel the event, with a reason. The server releases every venue
 * booking and hold that still keeps a slot and every equipment line, and tells
 * everyone it affects. The event comes back Cancelled and read-only.
 */
export async function cancelEvent(
  id: string,
  reason: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/cancel`, session.token, {
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
 * US4.4: whether the assigned Coordinator can send the event for its safety
 * check now, and if not, the server's sentence saying what is outstanding.
 */
export type SafetyReadiness = {
  ready: boolean
  /** A refusal code such as 'venue-not-confirmed', or empty when ready. */
  reason: string
  message: string
}

/** US4.4: the readiness the Send for safety check button depends on. */
export async function getSafetyReadiness(id: string, session: Session): Promise<SafetyReadiness> {
  const response = await authorizedFetch(`/events/${id}/safety-check`, session.token)
  return (await response.json()) as SafetyReadiness
}

/** US4.4: Planning -> Pending Safety Check, by the assigned Coordinator. */
export async function sendForSafetyCheck(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/safety-check`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US4.4: the events waiting for the Safety Officer, longest-waiting first. */
export async function listSafetyQueue(session: Session): Promise<EventRecord[]> {
  const response = await authorizedFetch('/events/safety-check', session.token)
  return (await response.json()) as EventRecord[]
}

/** US17.1: a venue unavailability period that has not ended yet (US12.1). */
export type VenueClosure = { startDate: string; endDate: string; reason: string }

/** US17.1: one booked venue — what the booking asks beside what the venue offers. */
export type ReviewedVenue = {
  bookingId: string
  venueId: string
  venueName: string
  location: string
  status: string
  startsAt: string
  endsAt: string
  /** Null only if the venue record has gone. */
  capacity: number | null
  headcount: number | null
  overCapacity: boolean
  requiredLayout: string
  supportedLayouts: string
  facilities: string
  accessibilityFeatures: string
  accessibilityNeeds: string[]
  operatingHours: string
  setupMinutes: number
  turnaroundMinutes: number
  closures: VenueClosure[]
}

export type ReviewedEquipment = {
  id: string
  type: string
  quantity: number
  technicalRequirements: string
  supportNotes: string
  startsAt: string
  endsAt: string
}

/** US17.1: everything the Safety Officer needs to assess one event. */
export type SafetyReview = {
  eventId: string
  title: string
  status: EventStatus
  startsAt: string
  endsAt: string
  expectedAttendance: number | null
  accessibilityNeeds: string
  preferredLayout: string
  venueRequirements: string
  waitingSince: string
  venues: ReviewedVenue[]
  equipment: ReviewedEquipment[]
}

/** US17.1: the read-only review behind the Safety Officer's queue. */
export async function getSafetyReview(id: string, session: Session): Promise<SafetyReview> {
  const response = await authorizedFetch(`/events/${id}/safety-review`, session.token)
  return (await response.json()) as SafetyReview
}

/** US4.4: the Safety Officer signs the event off. Pending Safety Check -> Confirmed. */
export async function approveSafetyCheck(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/safety-check/approve`, session.token, {
      method: 'POST',
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US4.4: back to Planning, with a note the Coordinator reads. */
export async function returnSafetyCheck(
  id: string,
  note: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/safety-check/return`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
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
  /**
   * Every new booking waits on Venue Staff, whose approval is a later epic. A
   * Coordinator may cancel one (US14.2), which is final. US14.3: Venue Staff
   * may hold a venue for the Coordinator, who turns it into a request before
   * it expires. A hold is never Confirmed. US16.1: Venue Staff approve a
   * request (Confirmed) or reject it with a reason (Rejected). US14.4: the
   * scheduled sweep marks a hold past its expiry Expired, which is final.
   * US12.2: A booking flagged by venue unavailability becomes 'Needs replacement'.
   */
  status: 'Requested' | 'Cancelled' | 'Held' | 'Confirmed' | 'Rejected' | 'Expired' | 'Needs replacement'
  requestedAt: string
  /**
   * US18.1: how many people this booking is for. null only on a booking made
   * before US18.1 for an event that had no attendance to copy.
   */
  headcount: number | null
  /** Empty when the booking asked for no particular layout. */
  requiredLayout: string
  requiredFacilities: string[]
  accessibilityNeeds: string[]
  /** US14.2: who cancelled, when and why. null unless the status is Cancelled. */
  cancellation: BookingCancellation | null
  /** US14.3: when the hold lapses. Empty for a booking that was never a hold. */
  holdExpiresAt?: string
  /**
   * US14.3: past its expiry, so the slot is no longer kept. US14.4: true for an
   * Expired hold, and for a Held one the sweep has not reached yet.
   */
  holdExpired?: boolean
  /** US14.3: the Venue Staff member who placed the hold. */
  heldByName?: string
  /** US16.1: who approved or rejected it, when, and why. null until decided. */
  decision?: BookingDecision | null
  /**
   * US15.2: set while the booking is flagged "Conflict – review needed" because
   * it clashes since its venue's setup or turnaround time changed. The status
   * is unchanged; nothing was cancelled. null once the clash is resolved.
   */
  conflict?: BookingConflictFlag | null
  /**
   * US12.2: why this booking was flagged as "Needs replacement" (from venue
   * unavailability or conflict). Empty unless status is 'Needs replacement'.
   */
  replacementReason?: string
  /**
   * US12.2: the venue_unavailability ID that flagged this booking. null unless
   * flagged by unavailability. Optional for backward compatibility.
   */
  flaggedByUnavailabilityId?: number | null
}

/** US15.2: why a booking clashes since its venue's setup or turnaround changed. */
export type BookingConflictFlag = {
  /** Always "Conflict – review needed". */
  label: string
  flaggedAt: string
  /** The window it occupies and what it overlaps, by booking number and times. */
  reason: string
}

/** The label US15.2's acceptance criteria give a flagged booking. */
export const CONFLICT_LABEL = 'Conflict – review needed'

/** US16.1: Venue Staff's decision on a booking request. */
export type BookingDecision = {
  at: string
  /** null once the user who decided has been removed; the record stays. */
  byId: string | null
  byName: string
  /** Empty for an approval. */
  reason: string
  /** An alternative venue or time Venue Staff suggest. Empty when none. */
  suggestion: string
}

export type BookingCancellation = {
  at: string
  /** null once the user who cancelled has been removed; the record stays. */
  byId: string | null
  byName: string
  reason: string
}

/** The server's cap on a cancellation reason, mirrored so the form can say so. */
export const CANCELLATION_REASON_MAX = 2000

/**
 * The Coordinator's booking form, as typed. `bookingPayload` turns it into what
 * the API takes, so the form never holds a half-parsed number or list.
 */
export type BookingInput = {
  venueId: string
  startsAt: string
  endsAt: string
  /** US18.1: starts as the event's expected attendance. */
  headcount: string
  layout: string
  /** Comma-separated, as typed. */
  facilities: string
  accessibilityNeeds: string
}

/** A comma-separated field as a list, blanks dropped. */
export function splitNeeds(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

/** The form as the API reads it: a number for the headcount, lists for needs. */
export function bookingPayload(input: BookingInput) {
  return {
    venueId: input.venueId,
    startsAt: input.startsAt,
    endsAt: input.endsAt,
    headcount: Number(input.headcount.trim()),
    layout: input.layout.trim(),
    facilities: splitNeeds(input.facilities),
    accessibilityNeeds: splitNeeds(input.accessibilityNeeds),
  }
}

/** US18.1: Suitable or Not suitable for one venue, with every reason. */
export type Suitability = {
  venueId: string
  suitable: boolean
  /** Why it is not suitable, one sentence each. Empty when it is. */
  reasons: string[]
  /** What could not be checked, such as hours nobody has recorded. */
  notes: string[]
  /**
   * US15.1: whether the slot is free at this venue, with setup and turnaround
   * counted. Optional so an older server's answer still reads as available.
   */
  available?: boolean
  /** US15.1: each booking or unavailability period it clashes with, as a phrase. */
  clashes?: string[]
  /** US15.1: the full window the booking would occupy. */
  occupiedFrom?: string
  occupiedTo?: string
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
  const headcount = parseAttendance(input.headcount)
  if (headcount === null) return 'Give the headcount for this booking.'
  if (headcount === 'invalid') return 'Give the headcount as a whole number of people.'
  if (headcount < 1) return 'The headcount must be at least 1.'
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
  return `${start} – ${end.toLocaleTimeString('en-SG', {
    timeZone: 'Asia/Singapore',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })}`
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
      body: JSON.stringify(bookingPayload(input)),
    })
    return (await response.json()) as BookingRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * US18.1: whether the chosen venue suits this booking. Stores nothing; the
 * request is refused by the server on the same verdict.
 */
export async function checkSuitability(
  eventId: string,
  input: BookingInput,
  session: Session,
): Promise<Suitability> {
  try {
    const response = await authorizedFetch(
      `/events/${eventId}/bookings/suitability`,
      session.token,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bookingPayload(input)),
      },
    )
    return (await response.json()) as Suitability
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * US14.2: cancel one booking, with a reason. Only that booking changes; the
 * event and its other bookings are left as they were.
 */
export async function cancelBooking(
  eventId: string,
  bookingId: string,
  reason: string,
  session: Session,
): Promise<BookingRecord> {
  try {
    const response = await authorizedFetch(
      `/events/${eventId}/bookings/${bookingId}/cancel`,
      session.token,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      },
    )
    return (await response.json()) as BookingRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * US14.3: turn a hold Venue Staff placed into a booking request, before it
 * expires. An expired or already-requested hold comes back as a refusal.
 */
export async function requestHeldBooking(
  eventId: string,
  bookingId: string,
  session: Session,
): Promise<BookingRecord> {
  try {
    const response = await authorizedFetch(
      `/events/${eventId}/bookings/${bookingId}/request`,
      session.token,
      { method: 'POST' },
    )
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

/**
 * US11.1: propose changes to a submitted event instead of saving them.
 *
 * Sends the edit form's values; the server works out which fields differ,
 * flags the event. Only an assigned Submitted event moves to Under Review;
 * the event's values do not change until a Coordinator approves.
 */
export async function requestEventChange(
  id: string,
  draft: EventDraft,
  note: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/change-request`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...draft, note }),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US11.1: apply the Organiser's proposed changes. The event stays Under Review. */
export async function approveEventChange(id: string, session: Session): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(
      `/events/${id}/change-request/approve`,
      session.token,
      { method: 'POST' },
    )
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US11.1: decline the proposed changes with a reason the Organiser can read. */
export async function rejectEventChange(
  id: string,
  reason: string,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch(`/events/${id}/change-request/reject`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    return asRuleError(error)
  }
}
