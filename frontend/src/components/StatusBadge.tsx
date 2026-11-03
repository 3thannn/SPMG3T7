import './StatusBadge.css'
import { statusStage, type EventStatus } from '../status'

type StatusBadgeProps = {
  status: EventStatus
  size?: 'sm' | 'lg'
  /**
   * US17.2 (reopened): the Safety Officer approved the current stay, so a
   * Pending Safety Check event is waiting for its Coordinator to confirm it.
   * Ignored in any other status.
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
 * US4.1: the single way an event status is rendered anywhere in the app.
 *
 * The status is announced to assistive tech with its meaning spelled out, so it
 * does not depend on colour alone. The status label itself never changes: an
 * approved event is still Pending Safety Check, and says so, with what it is
 * waiting for named after it.
 */
export default function StatusBadge({ status, size = 'sm', safetyApproved = false }: StatusBadgeProps) {
  const stage = statusStage(status, safetyApproved)
  const classes = `status-badge status-badge-${MODIFIER[status]} status-badge-${size}`
  return (
    <span className={stage ? `${classes} status-badge-staged` : classes}>
      <span className="status-badge-dot" aria-hidden="true" />
      <span className="sr-only">Status: </span>
      {status}
      {stage && (
        <span className="status-badge-stage">
          <span aria-hidden="true">·</span>
          <span className="sr-only">, </span>
          {stage}
        </span>
      )}
    </span>
  )
}
