import './ProposedChanges.css'
import type { ProposedChange } from '../eventsStore'
import { formatTimestamp } from '../status'

type ProposedChangesProps = {
  changes: readonly ProposedChange[]
}

const DATE_FIELDS = new Set(['proposed_date', 'end_date'])

/** A stored value as the edit form would show it, so both sides read alike. */
function displayValue(field: string, value: string): string {
  if (!value) return 'Not set'
  if (DATE_FIELDS.has(field)) return formatTimestamp(value)
  if (field === 'expected_attendance') return `${value} people`
  return value
}

/**
 * US11.1: what the Organiser has asked to change, current value beside the
 * proposed one.
 *
 * Important changes (date/time, attendance, venue, equipment — US5.2's rule)
 * are listed first and tagged, so a Coordinator reviewing a long request reads
 * the ones that affect bookings before the wording edits.
 */
export default function ProposedChanges({ changes }: ProposedChangesProps) {
  const important = changes.filter((change) => change.important)
  const routine = changes.filter((change) => !change.important)

  return (
    <ul className="proposed-list" aria-label="Proposed changes">
      {[...important, ...routine].map((change) => (
        <li
          key={change.field}
          className={`proposed-item${change.important ? ' is-important' : ''}`}
        >
          <div className="proposed-head">
            <span className="proposed-label">{change.label}</span>
            {change.important && <span className="proposed-tag">Important</span>}
          </div>
          <div className="proposed-values">
            <span className="proposed-old">
              <span className="sr-only">Current: </span>
              {displayValue(change.field, change.oldValue)}
            </span>
            <span className="proposed-arrow" aria-hidden="true">
              →
            </span>
            <span className="proposed-new">
              <span className="sr-only">Proposed: </span>
              {displayValue(change.field, change.newValue)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}
