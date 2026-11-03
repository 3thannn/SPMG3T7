import './StatusBadge.css'
import type { EventStatus } from '../status'

type StatusBadgeProps = {
  status: EventStatus
  size?: 'sm' | 'lg'
  /**
   * US17.2: the Safety Officer approved the current safety check. Only an
   * event's current status passes it; a past one in the history does not.
   */
  safetyApproved?: boolean
}

/** Maps a status to its modifier class. Keeps the label set and its colours together. */
const MODIFIER: Record<EventStatus, string> = {
  Draft: 'draft',
  Submitted: 'submitted',
  'Under Review': 'review',
  Approved: 'approved',
  Planning: 'planning',
  'Pending Safety Check': 'safety',
  Confirmed: 'confirmed',
  Completed: 'completed',
  Cancelled: 'cancelled',
  Rejected: 'rejected',
}

/**
 * US17.2: an approved safety check leaves the event Pending Safety Check until
 * the Coordinator confirms it (US4.7), and it is shown as such.
 */
export const SAFETY_APPROVED_LABEL = 'Safety approved, awaiting Coordinator confirmation'

/**
 * US4.1: the single way an event status is rendered anywhere in the app.
 *
 * The status is announced to assistive tech with its meaning spelled out, so it
 * does not depend on colour alone.
 */
export default function StatusBadge({ status, size = 'sm', safetyApproved = false }: StatusBadgeProps) {
  const approved = safetyApproved && status === 'Pending Safety Check'
  const modifier = approved ? 'approved' : MODIFIER[status]
  return (
    <span className={`status-badge status-badge-${modifier} status-badge-${size}`}>
      <span className="status-badge-dot" aria-hidden="true" />
      <span className="sr-only">Status: </span>
      {approved ? SAFETY_APPROVED_LABEL : status}
    </span>
  )
}
