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
 * The three that have features: an Organiser proposes events, a Coordinator
 * reviews them and reads the venue catalogue, and Venue Staff maintain that
 * catalogue (US9.1a-c). Technical Support and Attendee are still deliberately
 * absent — the server agrees, and this type is what makes a stray role name a
 * build error rather than a runtime surprise.
 */
export type Role = 'Event Organiser' | 'Event Coordinator' | 'Venue Staff'

/**
 * US4.1: status is visible to the Organiser who owns the event. Coordinators
 * can see an event only after its Organiser submits it; later workflow statuses
 * remain visible because they still represent a submitted request.
 */
export function canViewStatus(
  role: Role,
  viewerId: string,
  event: { organiserId: string; status: EventStatus },
): boolean {
  if (role === 'Event Coordinator') return event.status !== 'Draft'
  if (role === 'Event Organiser') return event.organiserId === viewerId
  // Venue Staff hold no event permission, so this is their answer, and it
  // stays the safe one for any role added later that has not been considered
  // here — which is how it already covered Venue Staff before US9.1a-c.
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
  /**
   * A Coordinator's clarification request (US7.3), or empty on an automatic
   * entry. Optional so fixtures and older payloads still type-check.
   */
  notes?: string
}

/**
 * US7.3: the statuses a Coordinator may ask for clarification on.
 *
 * Submitted is the case the story describes; Under Review is included because a
 * first answer often raises a second question. A Draft is not here — a
 * Coordinator cannot see one — and neither is a decided event.
 */
export const CLARIFIABLE: readonly EventStatus[] = ['Submitted', 'Under Review']

/** Why a clarification request was refused, so the UI can explain rather than deny. */
export type ClarificationRefusal = 'not-yet-submitted' | 'already-decided'

export type ClarificationCheck =
  | { allowed: true }
  | { allowed: false; reason: ClarificationRefusal }

/**
 * US7.3: a Coordinator may ask for clarification on an event under review.
 *
 * There is deliberately no check on *which* Coordinator: the story says any of
 * them can for now, and narrowing it to the assigned one waits for US8.1.
 *
 * This mirrors the server rule so the page can hide the form and say why. It is
 * not the enforcement point — the server re-checks, and that refusal is the rule.
 */
export function checkClarification(event: { status: EventStatus }): ClarificationCheck {
  if (event.status === 'Draft') return { allowed: false, reason: 'not-yet-submitted' }
  if (!CLARIFIABLE.includes(event.status)) {
    return { allowed: false, reason: 'already-decided' }
  }
  return { allowed: true }
}

export function clarificationRefusalMessage(reason: ClarificationRefusal): string {
  switch (reason) {
    case 'not-yet-submitted':
      return 'This event has not been submitted yet, so there is nothing to review.'
    case 'already-decided':
      return 'This event has already been decided, so it is no longer under review.'
  }
}

/** Whether an audit entry carries a message a person wrote, rather than being automatic. */
export function isClarificationRequest(change: StatusChange): boolean {
  return (change.notes ?? '').trim() !== ''
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
