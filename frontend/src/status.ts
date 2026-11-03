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
  // US4.4: between planning and preparation; only the Safety Officer's
  // sign-off moves an event on to Confirmed.
  'Pending Safety Check',
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
 * US19 adds Technical Support, and US20.1 Attendee.
 */
export type Role =
  | 'Event Organiser'
  | 'Event Coordinator'
  | 'Event Coordinator Lead'
  | 'Venue Staff'
  | 'Safety Officer'
  | 'Technical Support'
  | 'Attendee'

/**
 * US4.1: status is visible to the Organiser who owns the event. Coordinators
 * can see an event only after its Organiser submits it; later workflow statuses
 * remain visible because they still represent a submitted request.
 * US8.6: Coordinator Lead can view all non-Draft events (not just assigned ones).
 */
export function canViewStatus(
  role: Role,
  viewerId: string,
  event: { organiserId: string; status: EventStatus },
): boolean {
  if (role === 'Event Coordinator') return event.status !== 'Draft'
  if (role === 'Event Coordinator Lead') return event.status !== 'Draft'
  if (role === 'Event Organiser') return event.organiserId === viewerId
  // US4.4: the Safety Officer sees an event only while it waits for their check.
  if (role === 'Safety Officer') return event.status === 'Pending Safety Check'
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
  // D2: a Rejected event may be revised and submitted again.
  if (event.status !== 'Draft' && event.status !== 'Rejected') {
    return { allowed: false, reason: 'not-draft' }
  }
  return { allowed: true }
}

export function submitRefusalMessage(reason: SubmitRefusal): string {
  switch (reason) {
    case 'already-submitted':
      return 'This event has already been submitted. An event can only be submitted once.'
    case 'not-owner':
      return 'Only the Organiser who owns this event can submit it.'
    case 'not-draft':
      return 'Only a Draft or Rejected event can be submitted.'
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
   * A Coordinator's clarification request (US7.3) or rejection reason
   * (US7.1), and empty on an automatic entry. Optional so older payloads and
   * fixtures still type-check.
   */
  notes?: string
  /**
   * US11.1: 'change-request' on the entry an Organiser's change request wrote,
   * so its note is labelled as theirs. US4.4: 'safety-return' on the entry the
   * Safety Officer wrote sending an event back to Planning. US4.6:
   * 'cancellation' on the entry that cancelled the event. Empty otherwise.
   */
  kind?: '' | 'change-request' | 'safety-return' | 'cancellation'
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
 * Assignment is enforced by the API before this page receives an event. This
 * client-side check mirrors only the status rule.
 *
 * This mirrors the server rule so the page can hide the form and say why. It is
 * not the enforcement point — the server re-checks, and that refusal is the rule.
 */
export function checkClarification(event: { status: EventStatus; changeRequested?: boolean }): ClarificationCheck {
  if (event.status === 'Draft') return { allowed: false, reason: 'not-yet-submitted' }
  if (!CLARIFIABLE.includes(event.status) && !(event.changeRequested && REQUESTABLE.includes(event.status))) {
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

export type StatusNoteKind =
  | 'clarification'
  | 'rejection'
  | 'change-request'
  | 'safety-return'
  | 'cancellation'
  /** US8.4: a Lead moved the event to a different Coordinator. */
  | 'reassignment'
/**
 * US14.1: the statuses an event may have venues requested for.
 *
 * Every status a Coordinator can see except the ones that end an event. A
 * booking is only a request until Venue Staff approve it, so asking while the
 * event is under review costs nothing.
 */
export const BOOKABLE: readonly EventStatus[] = [
  'Approved',
  'Planning',
]

/** Why venues cannot be requested, so the UI can explain rather than deny. */
export type BookingRefusal = 'not-yet-submitted' | 'not-approved' | 'past-planning' | 'event-closed'

export type BookingCheck = { allowed: true } | { allowed: false; reason: BookingRefusal }

/**
 * US14.1: whether venues may be requested for an event at this status.
 *
 * Mirrors the server so the page can hide the form and say why. Assignment
 * (US8.6) is enforced by the API before this page receives an event; the server
 * re-checks both, and that refusal is the rule.
 */
export function checkBooking(event: { status: EventStatus }): BookingCheck {
  if (event.status === 'Draft') return { allowed: false, reason: 'not-yet-submitted' }
  if (event.status === 'Submitted' || event.status === 'Under Review') {
    return { allowed: false, reason: 'not-approved' }
  }
  // Past planning but still going ahead: not closed. A booking that falls
  // through can still be replaced (US14.5/US12.4).
  if (event.status === 'Pending Safety Check' || event.status === 'Confirmed') {
    return { allowed: false, reason: 'past-planning' }
  }
  if (!BOOKABLE.includes(event.status)) return { allowed: false, reason: 'event-closed' }
  return { allowed: true }
}

export function bookingRefusalMessage(reason: BookingRefusal): string {
  switch (reason) {
    case 'not-yet-submitted':
      return 'This event has not been submitted yet, so no venues can be requested for it.'
    case 'not-approved':
      return 'Approve this event before requesting a venue.'
    case 'past-planning':
      return (
        'Venues are requested while an event is in Planning, so no new ones can be requested ' +
        'now. A booking that needs replacing can still be replaced.'
      )
    case 'event-closed':
      return 'This event is closed, so no more venues can be requested for it.'
  }
}

/**
 * US4.6: why an event cannot be cancelled. "Any event that isn't Completed,
 * Cancelled or Rejected" may be, so there is one refusal for each of those.
 */
export type CancelRefusal = 'already-cancelled' | 'event-completed' | 'event-rejected'

export type CancelCheck = { allowed: true } | { allowed: false; reason: CancelRefusal }

/**
 * US4.6: may an event at this status be cancelled?
 *
 * Mirrors the server's `check_cancel`. Who may cancel (the owner, or the
 * assigned Coordinator) is the page's to decide from the session; the server
 * re-checks both, and that refusal is the rule.
 */
export function checkCancel(event: { status: EventStatus }): CancelCheck {
  if (event.status === 'Cancelled') return { allowed: false, reason: 'already-cancelled' }
  if (event.status === 'Completed') return { allowed: false, reason: 'event-completed' }
  if (event.status === 'Rejected') return { allowed: false, reason: 'event-rejected' }
  return { allowed: true }
}

export function cancelRefusalMessage(reason: CancelRefusal): string {
  switch (reason) {
    case 'already-cancelled':
      return 'This event has already been cancelled.'
    case 'event-completed':
      return 'This event has already been completed, so it cannot be cancelled.'
    case 'event-rejected':
      return 'This event was rejected, so there is nothing to cancel.'
  }
}

/** What kind of person-written note an audit entry carries. */
export function statusNoteKind(change: StatusChange): StatusNoteKind | null {
  if (!(change.notes ?? '').trim()) return null
  if (change.kind) return change.kind
  if (change.to === 'Rejected') return 'rejection'
  return 'clarification'
}

/** The heading the history shows above each kind of note. */
export function statusNoteLabel(kind: StatusNoteKind): string {
  switch (kind) {
    case 'clarification':
      return 'Requested by Coordinator'
    case 'rejection':
      return 'Rejection reason'
    case 'change-request':
      return 'Change requested by Organiser'
    case 'safety-return':
      return 'Sent back by Safety Officer'
    case 'cancellation':
      return 'Cancellation reason'
    case 'reassignment':
      return 'Coordinator reassigned by Lead'
  }
}

/**
 * US11.1: where an Organiser may request changes. A Draft is still theirs to
 * edit directly; a decided event is no longer under review.
 */
export const REQUESTABLE: readonly EventStatus[] = [
  'Submitted', 'Approved', 'Planning', 'Pending Safety Check', 'Confirmed',
]

/** Why a change request is not available, so the page can say rather than hide. */
export type ChangeRequestRefusal =
  | 'not-owner'
  | 'not-submitted'
  | 'already-decided'
  | 'already-pending'

export type ChangeRequestCheck =
  | { allowed: true }
  | { allowed: false; reason: ChangeRequestRefusal }

/** US5.3: a Confirmed event's details are locked; the server says the same. */
export const CONFIRMED_LOCKED_MESSAGE =
  'This event is confirmed. Changes need to go through a change request.'

/**
 * US11.1: may this Organiser propose changes to this event now?
 *
 * Mirrors the server's `check_change_request`, in the same order, so the page
 * explains the same refusal the server would give. The server re-checks.
 */
export function checkChangeRequest(
  event: { status: EventStatus; organiserId: string; changeRequested?: boolean; awaitingReply?: boolean },
  actorId: string,
): ChangeRequestCheck {
  if (event.organiserId !== actorId) return { allowed: false, reason: 'not-owner' }
  if (event.status === 'Draft') return { allowed: false, reason: 'not-submitted' }
  if (event.changeRequested && !event.awaitingReply) return { allowed: false, reason: 'already-pending' }
  if (!REQUESTABLE.includes(event.status) && !(event.status === 'Under Review' && event.awaitingReply)) return { allowed: false, reason: 'already-decided' }
  return { allowed: true }
}

export function changeRequestRefusalMessage(reason: ChangeRequestRefusal): string {
  switch (reason) {
    case 'not-owner':
      return 'Only the Organiser who owns this event can request changes to it.'
    case 'not-submitted':
      return 'This event is still a Draft. Edit it directly, then submit it.'
    case 'already-decided':
      return 'This event has already been decided, so changes can no longer be requested.'
    case 'already-pending':
      return "A change request for this event is already awaiting the Coordinator's review."
  }
}

/** Whether an entry specifically contains a US7.3 clarification request. */
export function isClarificationRequest(change: StatusChange): boolean {
  return statusNoteKind(change) === 'clarification'
}

export function formatTimestamp(iso: string): string {
  const planned = iso && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? `${iso}+08:00` : iso
  const date = new Date(planned)
  if (Number.isNaN(date.getTime())) return iso
  // Display in Singapore timezone (UTC+8)
  return date.toLocaleString('en-SG', {
    timeZone: 'Asia/Singapore',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** A trailing UTC offset: `Z`, `+08:00` or `+0800`. */
const HAS_OFFSET = /(?:Z|[+-]\d{2}:?\d{2})$/i

/**
 * When something was recorded (created, updated, changed, cancelled), in
 * Singapore time. The database keeps these as naive UTC, and `new Date` reads a
 * naive time as the viewer's own, which in Singapore shows it 8 hours early. So
 * a time without an offset is read as UTC here. Planned times, an event's or a
 * booking's start and end, are naive Singapore times and stay with
 * `formatTimestamp`.
 */
export function formatRecordedAt(iso: string): string {
  if (!iso || HAS_OFFSET.test(iso)) return formatTimestamp(iso)
  const utc = `${iso}Z`
  return Number.isNaN(new Date(utc).getTime()) ? iso : formatTimestamp(utc)
}
