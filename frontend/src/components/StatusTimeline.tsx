import './StatusTimeline.css'
import StatusBadge from './StatusBadge'
import {
  formatRecordedAt, statusNoteKind, statusNoteLabel, type StatusChange,
} from '../status'

/** Event status transitions, with notes for requested event changes. */
export default function StatusTimeline({ history }: { history: readonly StatusChange[] }) {
  if (history.length === 0) return <p className="muted">No history recorded yet.</p>
  const entries = [...history].sort((a, b) => a.at.localeCompare(b.at))

  return <ol className="timeline">
    {entries.map((change, index) => {
      const noteKind = statusNoteKind(change)
      return <li className="timeline-item" key={`${change.at}-${index}`}>
        <span className="timeline-marker" aria-hidden="true" />
        <div className="timeline-body">
          <div className="timeline-change">
            {change.from ? <>
              <StatusBadge status={change.from} />
              <span className="timeline-arrow" aria-label="changed to">→</span>
            </> : <span className="timeline-created">Created as</span>}
            <StatusBadge status={change.to} />
          </div>
          <p className="timeline-meta">
            {change.byName} · <time dateTime={change.at}>{formatRecordedAt(change.at)}</time>
          </p>
          {noteKind && <blockquote className="timeline-note">
            <p className="timeline-note-label">{statusNoteLabel(noteKind)}</p>
            {change.notes}
          </blockquote>}
        </div>
      </li>
    })}
  </ol>
}
