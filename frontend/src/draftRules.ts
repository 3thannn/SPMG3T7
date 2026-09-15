/** Rules shared by the create and edit draft forms. */

export const DRAFT_CONTENT_ERROR =
  'Enter at least one letter or number in any field to save a draft.'

type DraftContent = {
  title: string
  purpose: string
  description: string
  startsAt: string
  endsAt?: string | null
  expectedAttendance: string | number | null
}

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
