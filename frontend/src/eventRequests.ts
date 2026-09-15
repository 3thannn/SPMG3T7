/**
 * Event requests — the client half of Event Request Creation.
 *
 * An *event request* is a complete proposal that is submitted in one step,
 * unlike the US4.2 draft in `eventsStore`, which is saved first and submitted
 * later. Both write to the same `events` table; they differ in how finished the
 * thing is when it gets there, which is why this lives beside `eventsStore`
 * rather than inside it — nothing in the draft flow changes.
 *
 * Every field is plain text, a date or a number. There are no Venue or
 * Equipment catalogue lookups: those arrive in Sprint 2 and 3.
 *
 * The rules below mirror `backend/app/event_request_rules.py` line for line, on
 * purpose and with the same caveat as `status.ts`: this is so the form can
 * complain in the field, next to the input, before anyone waits on a round
 * trip. It is not the enforcement point. The server re-checks every one of
 * these, and that check is the rule.
 */

import { ApiError, authorizedFetch, type Session } from './api'
import type { EventRecord } from './eventsStore'

/** Mirrors the limits in `event_request_rules.py`. See that module on why. */
export const NAME_MAX = 255
export const PURPOSE_MAX = 500
export const DESCRIPTION_MAX = 2000
export const ATTENDANCE_MIN = 1
export const ATTENDANCE_MAX = 1_000_000

/** The form, as the inputs hold it: all strings, because inputs are. */
export type RequestFields = {
  name: string
  purpose: string
  description: string
  /** `YYYY-MM-DD`, from <input type="date">. */
  proposedDate: string
  /** `HH:MM`, from <input type="time">. */
  startTime: string
  endTime: string
  expectedAttendance: string
}

export const EMPTY_REQUEST: RequestFields = {
  name: '',
  purpose: '',
  description: '',
  proposedDate: '',
  startTime: '',
  endTime: '',
  expectedAttendance: '',
}

export type RequestErrors = Partial<Record<keyof RequestFields, string>>

/** Raised when the server refuses a request the form thought was complete. */
export class EventRequestError extends Error {}

/**
 * Today, as `YYYY-MM-DD` in the browser's own timezone.
 *
 * Deliberately not `toISOString().slice(0, 10)`, which converts to UTC first —
 * east of Greenwich that reads as yesterday for the first hours of every day,
 * so an event proposed for this morning would be refused as being in the past.
 */
export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** Whether a string is a real calendar date in `YYYY-MM-DD`. */
export function isCalendarDate(raw: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw)
  if (!match) return false
  const [, year, month, day] = match
  const parsed = new Date(`${year}-${month}-${day}T00:00:00`)
  // Date rolls 2026-02-30 forward to 2026-03-02 rather than refusing it, so the
  // only way to know it was a real day is to ask what came back.
  return (
    parsed.getFullYear() === Number(year) &&
    parsed.getMonth() + 1 === Number(month) &&
    parsed.getDate() === Number(day)
  )
}

/** Minutes since midnight for `HH:MM`, or null when it is not a time. */
export function minutesOfDay(raw: string): number | null {
  const match = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(raw)
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 23 || minutes > 59) return null
  return hours * 60 + minutes
}

/**
 * The expected head count: a positive whole number, or why it is not one.
 *
 * Returns the number, or the sentence to show. A separate function because the
 * attendance rule is the one with more than one way to be wrong, and folding it
 * into `validate` would bury three branches in a chain of ifs.
 */
export function parseExpectedAttendance(raw: string): number | string {
  const trimmed = raw.trim()
  if (!trimmed) return 'Give the expected attendance.'
  if (!/^[+-]?\d+$/.test(trimmed)) return 'Expected attendance must be a whole number.'
  const value = Number(trimmed)
  if (value < ATTENDANCE_MIN) return `Expected attendance must be at least ${ATTENDANCE_MIN}.`
  if (value > ATTENDANCE_MAX) {
    return `Expected attendance cannot be more than ${ATTENDANCE_MAX.toLocaleString('en-GB')}.`
  }
  return value
}

/**
 * Everything wrong with the form, so the user sees it in one pass.
 *
 * The server reports the first failure only, because by the time a request
 * reaches it the realistic case is one bad field. A form is the other way
 * round: someone who left three fields blank should be told about three fields,
 * not made to submit three times.
 */
export function validate(fields: RequestFields, today: string = todayIso()): RequestErrors {
  const errors: RequestErrors = {}

  const name = fields.name.trim()
  if (!name) errors.name = 'Give the event a name.'
  else if (name.length > NAME_MAX) {
    errors.name = `Keep the name to ${NAME_MAX} characters or fewer.`
  }

  const purpose = fields.purpose.trim()
  if (!purpose) errors.purpose = 'Say what the event is for.'
  else if (purpose.length > PURPOSE_MAX) {
    errors.purpose = `Keep the purpose to ${PURPOSE_MAX} characters or fewer.`
  }

  if (fields.description.trim().length > DESCRIPTION_MAX) {
    errors.description = `Keep the description to ${DESCRIPTION_MAX} characters or fewer.`
  }

  const date = fields.proposedDate.trim()
  if (!date) errors.proposedDate = 'Give the event a proposed date.'
  else if (!isCalendarDate(date)) errors.proposedDate = 'Give the proposed date as YYYY-MM-DD.'
  // Both sides are `YYYY-MM-DD`, which sorts the same way it reads.
  else if (date < today) errors.proposedDate = 'The proposed date cannot be in the past.'

  const start = fields.startTime.trim()
  const end = fields.endTime.trim()
  const startMinutes = minutesOfDay(start)
  const endMinutes = minutesOfDay(end)

  if (!start) errors.startTime = 'Give the event a start time.'
  else if (startMinutes === null) errors.startTime = 'Give the start time as HH:MM.'

  if (!end) errors.endTime = 'Give the event an end time.'
  else if (endMinutes === null) errors.endTime = 'Give the end time as HH:MM.'
  else if (startMinutes !== null && endMinutes <= startMinutes) {
    errors.endTime = 'The end time must be after the start time.'
  }

  const attendance = parseExpectedAttendance(fields.expectedAttendance)
  if (typeof attendance === 'string') errors.expectedAttendance = attendance

  return errors
}

/** Whether `validate` found nothing to complain about. */
export function isComplete(errors: RequestErrors): boolean {
  return Object.values(errors).every((message) => !message)
}

/**
 * Submit the request. The event comes back already `Submitted`.
 *
 * A 400 is the server's own validation refusing something this form let
 * through — a rule the mirror above has drifted from, or a date that was in the
 * future when the page loaded and is not any more. It is raised as an
 * `EventRequestError` carrying the server's sentence, which the page shows
 * above the form: the server reports one field and `ApiError` does not carry
 * which, so pinning it to an input would mean guessing.
 */
export async function createEventRequest(
  fields: RequestFields,
  session: Session,
): Promise<EventRecord> {
  try {
    const response = await authorizedFetch('/event-requests', session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: fields.name.trim(),
        purpose: fields.purpose.trim(),
        description: fields.description.trim(),
        proposedDate: fields.proposedDate.trim(),
        startTime: fields.startTime.trim(),
        endTime: fields.endTime.trim(),
        expectedAttendance: fields.expectedAttendance.trim(),
      }),
    })
    return (await response.json()) as EventRecord
  } catch (error) {
    if (error instanceof ApiError && (error.status === 400 || error.status === 403)) {
      throw new EventRequestError(error.message)
    }
    // A 401 has to bubble: it ends the session, and is not this form's to show.
    throw error
  }
}
