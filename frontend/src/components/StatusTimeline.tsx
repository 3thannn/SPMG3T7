import './StatusTimeline.css'
import StatusBadge from './StatusBadge'
import type { EquipmentHistoryEntry, RequestSnapshot } from '../equipmentStore'
import {
  formatTimestamp, statusNoteKind, statusNoteLabel, type StatusChange,
} from '../status'

type StatusTimelineProps = {
  history: readonly StatusChange[]
  equipmentHistory?: readonly EquipmentHistoryEntry[]
}

const fields: { key: keyof RequestSnapshot; label: string }[] = [
  { key: 'equipment_type', label: 'Type' },
  { key: 'quantity', label: 'Quantity' },
  { key: 'technical_requirements', label: 'Technical requirements' },
  { key: 'support_notes', label: 'Arrangement notes' },
  { key: 'start_at', label: 'Needed from' },
  { key: 'end_at', label: 'Needed until' },
]

function display(value: string | number | undefined): string {
  return value === '' || value === undefined ? 'None' : String(value)
}

function equipmentDetails(entry: EquipmentHistoryEntry): string[] {
  if (entry.action === 'Created' && entry.after) {
    return fields.map(({ key, label }) => `${label}: ${display(entry.after?.[key])}`)
  }
  if (entry.action === 'Removed') return []
  return fields.filter(({ key }) => entry.before?.[key] !== entry.after?.[key])
    .map(({ key, label }) => `${label}: ${display(entry.before?.[key])} → ${display(entry.after?.[key])}`)
}

type TimelineEntry =
  | { kind: 'status'; value: StatusChange; at: string; order: number }
  | { kind: 'equipment'; value: EquipmentHistoryEntry; at: string; order: number }

/** One event audit timeline, from Draft creation through later status and equipment changes. */
export default function StatusTimeline({ history, equipmentHistory = [] }: StatusTimelineProps) {
  const entries: TimelineEntry[] = [
    ...history.map((value, order): TimelineEntry => ({ kind: 'status', value, at: value.at, order })),
    ...equipmentHistory.map((value, order): TimelineEntry => ({
      kind: 'equipment', value, at: value.at, order: history.length + order,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at) || a.order - b.order)

  if (entries.length === 0) return <p className="muted">No history recorded yet.</p>

  return <ol className="timeline">
    {entries.map((entry) => {
      if (entry.kind === 'equipment') {
        const change = entry.value
        const snapshot = change.after ?? change.before
        const details = equipmentDetails(change)
        return <li className="timeline-item" key={`equipment-${change.id}`}>
          <span className="timeline-marker" aria-hidden="true" />
          <div className="timeline-body">
            <strong>{change.action} {snapshot?.equipment_type ?? 'equipment'} request</strong>
            <p className="timeline-meta">{change.byName} · <time dateTime={change.at}>{formatTimestamp(change.at)}</time></p>
            {details.length > 0 && <ul className="equipment-history-changes">
              {details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>}
          </div>
        </li>
      }
      const change = entry.value
      const noteKind = statusNoteKind(change)
      return <li className="timeline-item" key={`status-${entry.order}`}>
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
            {change.byName} · <time dateTime={change.at}>{formatTimestamp(change.at)}</time>
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
