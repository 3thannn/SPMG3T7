/**
 * Event status model — US4.1 (SPMG3T7-28) and US4.2 (SPMG3T7-29).
 *
 * US4.1 fixes the label set, so it is declared once here and every surface that
 * shows a status reads from this module. Nothing else in the app should spell a
 * status label out by hand.
 */

export const EVENT_STATUSES = [
  'Draft',
  'Submitted',
  'Under Review',
  'Approved',
  'Planning',
  'Confirmed',
  'Completed',
  'Cancelled',
  'Rejected',
] as const

export type EventStatus = (typeof EVENT_STATUSES)[number]

/**
 * Statuses Sprint 1 can actually produce. US4.2 limits transitions to
 * Draft -> Submitted; the rest of the label set is displayable (US4.1) but not
 * yet reachable, and becomes reachable when the Review and Booking epics land.
 */
export const SPRINT_1_REACHABLE: readonly EventStatus[] = ['Draft', 'Submitted']

/**
 * The roles the system knows about.
 *
 * Scoped to the two that have features: an Organiser proposes events, a
 * Coordinator reviews them. Venue Staff, Technical Support and Attendee are
 * part of the wider plan and are deliberately not modelled yet — the server
 * agrees, and this type is what makes a stray role name a build error rather
 * than a runtime surprise.
 */
export type Role = 'Organiser' | 'Coordinator'

/**
 * US4.1: status is visible to the Organiser who owns the event, and to any
 * Event Coordinator. Sprint 2 narrows the Coordinator arm to only the assigned
 * Coordinator once Coordinator Assignment exists — that is the single line that
 * will need to change.
 */
export function canViewStatus(
  role: Role,
  viewerId: string,
  event: { organiserId: string },
): boolean {
  if (role === 'Coordinator') return true
  if (role === 'Organiser') return event.organiserId === viewerId
  // Unreachable for the roles above, and deliberately the safe answer for any
  // role added later that has not been considered here.
  return false
}

/** Why a submit was refused, so the UI can explain rather than just disable. */
export type SubmitRefusal = 'already-submitted' | 'not-owner' | 'not-draft'

export type SubmitCheck = { allowed: true } | { allowed: false; reason: SubmitRefusal }

/**
 * US4.2: an event may move Draft -> Submitted exactly once. A second submit on
 * an already-submitted event is refused, and only the owning Organiser may
 * submit.
 *
 * This mirrors the server rule so the UI can disable and explain the action.
 * It is not the enforcement point — the server must re-check, because a client
 * check is advisory only.
 */
export function checkSubmit(
  event: { status: EventStatus; organiserId: string },
  actorId: string,
): SubmitCheck {
  if (event.organiserId !== actorId) return { allowed: false, reason: 'not-owner' }
  if (event.status === 'Submitted') return { allowed: false, reason: 'already-submitted' }
  if (event.status !== 'Draft') return { allowed: false, reason: 'not-draft' }
  return { allowed: true }
}

export function submitRefusalMessage(reason: SubmitRefusal): string {
  switch (reason) {
    case 'already-submitted':
      return 'This event has already been submitted. An event can only be submitted once.'
    case 'not-owner':
      return 'Only the Organiser who owns this event can submit it.'
    case 'not-draft':
      return 'Only a Draft event can be submitted.'
  }
}

/** One entry in an event's audit trail — US4.2 requires who and when. */
export type StatusChange = {
  from: EventStatus | null
  to: EventStatus
  at: string // ISO-8601
  byId: string
  byName: string
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
