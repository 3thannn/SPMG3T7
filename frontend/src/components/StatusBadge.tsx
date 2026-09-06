import './StatusBadge.css'
import type { EventStatus } from '../status'

type StatusBadgeProps = {
  status: EventStatus
  size?: 'sm' | 'lg'
}

/** Maps a status to its modifier class. Keeps the label set and its colours together. */
const MODIFIER: Record<EventStatus, string> = {
  Draft: 'draft',
  Submitted: 'submitted',
  'Under Review': 'review',
  Approved: 'approved',
  Planning: 'planning',
  Confirmed: 'confirmed',
  Completed: 'completed',
  Cancelled: 'cancelled',
  Rejected: 'rejected',
}

/**
 * US4.1: the single way an event status is rendered anywhere in the app.
 *
 * The status is announced to assistive tech with its meaning spelled out, so it
 * does not depend on colour alone.
 */
export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-badge-${MODIFIER[status]} status-badge-${size}`}>
      <span className="status-badge-dot" aria-hidden="true" />
      <span className="sr-only">Status: </span>
      {status}
    </span>
  )
}
