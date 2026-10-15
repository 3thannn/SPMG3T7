/** Rules shared by the create and edit draft forms. */

import { firstMissingNeed, type EventNeeds } from './eventNeeds'

export const DRAFT_CONTENT_ERROR =
  'Enter at least one letter or number in any field to save a draft.'

/** `events.expected_attendance` is INTEGER; the server refuses anything larger. */
export const ATTENDANCE_MAX = 2_147_483_647
export const ATTENDANCE_TOO_LARGE = 'Expected attendance must be 2,147,483,647 or fewer.'

type DraftContent = {
  title: string
  purpose: string
  description: string
  startsAt: string
  endsAt?: string | null
  expectedAttendance: string | number | null
} & Partial<EventNeeds>

const ALPHANUMERIC = /[\p{L}\p{N}]/u

/**
 * A draft is worth storing once any field contains a letter or number.
 * This only inspects values: it deliberately does not trim or otherwise
 * normalise details the Organiser typed.
 */
export function hasDraftContent(draft: DraftContent): boolean {
  return Object.values(draft).some(
    (value) => value !== null && ALPHANUMERIC.test(String(value)),
  )
}

/** A display fallback for drafts whose saved title has no meaningful text. */
export function displayEventTitle(title: string): string {
  return ALPHANUMERIC.test(title) ? title : 'Untitled event'
}

type SubmissionFields = {
  title: string
  purpose: string
  description: string
  startsAt: string
  endsAt: string
  expectedAttendance: string
} & EventNeeds

/**
 * What stops these form values being submitted, or null when nothing does.
 *
 * US4.2's submit and US11.1's change request apply the same rules: a change
 * request must leave a submitted event as complete as submitting it required.
 * `today` is `YYYY-MM-DD` in local time, passed in so the rule is testable.
 *
 * US2.1 (Sprint 3): the customer made the description and all five needs
 * mandatory too. They are checked last so the original messages stand.
 */
export function submissionError(draft: SubmissionFields, today: string): string | null {
  if (!draft.title.trim()) return 'Give the event a title.'
  if (!draft.startsAt.trim()) return 'Give the event a date.'
  if (!draft.endsAt.trim()) return 'Give the event an end date.'
  if (draft.endsAt <= draft.startsAt) return 'The end date must be after the start date.'
  if (!draft.purpose.trim()) return 'Give the event a purpose.'
  if (!draft.expectedAttendance.trim()) return 'Give the expected attendance.'
  const trimmed = draft.expectedAttendance.trim()
  if (!/^\d+$/.test(trimmed)) return 'Enter a whole number of people.'
  if (Number(trimmed) < 1) return 'Expected attendance must be at least 1.'
  if (Number(trimmed) > ATTENDANCE_MAX) return ATTENDANCE_TOO_LARGE
  if (draft.startsAt.slice(0, 10) < today) return 'The start date cannot be in the past.'
  if (!draft.description.trim()) return 'Give the event a description.'
  return firstMissingNeed(draft)
}
