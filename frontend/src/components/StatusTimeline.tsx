import './StatusTimeline.css'
import StatusBadge from './StatusBadge'
import {
  formatTimestamp,
  statusNoteKind,
  statusNoteLabel,
  type StatusChange,
} from '../status'

type StatusTimelineProps = {
  history: readonly StatusChange[]
}

/**
 * US4.2: "Every status change is timestamped and attributable (who/when) for
 * audit." This renders that trail, newest first, so the most recent change is
 * the one you read without scrolling.
 *
 * US7.3 clarification requests, US7.1 rejection reasons and US11.1 change
 * requests (and the Coordinator's answers to them) travel on the status change
 * that caused them. The trail is where the Organiser reads those
 * messages, so notes render as quoted prose rather than timestamp metadata.
 */
export default function StatusTimeline({ history }: StatusTimelineProps) {
  if (history.length === 0) {
    return <p className="muted">No status changes recorded yet.</p>
  }

  const newestFirst = [...history].reverse()

  return (
    <ol className="timeline">
      {newestFirst.map((change, index) => {
        const noteKind = statusNoteKind(change)
        return (
          <li className="timeline-item" key={`${change.at}-${index}`}>
          <span className="timeline-marker" aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-change">
              {change.from ? (
                <>
                  <StatusBadge status={change.from} />
                  <span className="timeline-arrow" aria-label="changed to">
                    →
                  </span>
                </>
              ) : (
                <span className="timeline-created">Created as</span>
              )}
              <StatusBadge status={change.to} />
            </div>
            <p className="timeline-meta">
              {change.byName} · <time dateTime={change.at}>{formatTimestamp(change.at)}</time>
            </p>
            {noteKind && (
              <blockquote className="timeline-note">
                <p className="timeline-note-label">{statusNoteLabel(noteKind)}</p>
                {change.notes}
              </blockquote>
            )}
          </div>
          </li>
        )
      })}
    </ol>
  )
}
