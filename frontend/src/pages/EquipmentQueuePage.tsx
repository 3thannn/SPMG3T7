import { useEffect, useState } from 'react'
import '../equipment.css'
import type { Session } from '../api'
import { equipmentErrorMessage, listEquipmentQueue, type EquipmentRequest } from '../equipmentStore'
import { formatBookingTimes } from '../eventsStore'
import { formatRecordedAt } from '../status'

export default function EquipmentQueuePage({ session }: { session: Session }) {
  const [lines, setLines] = useState<EquipmentRequest[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    listEquipmentQueue(session).then((loaded) => {
      if (!cancelled) setLines(loaded)
    }).catch((cause: unknown) => {
      if (!cancelled) setError(equipmentErrorMessage(cause, 'load equipment requests'))
    })
    return () => { cancelled = true }
  }, [session])

  return <div className="page shell">
    <header className="page-head"><div><h1 className="page-title">Equipment requests</h1>
      <p className="page-subtitle">Requested lines, oldest first.</p></div></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    {lines === null && !error && <p>Loading requests…</p>}
    {lines?.length === 0 && <div className="card empty"><h2>No equipment requests are waiting</h2></div>}
    {lines && lines.length > 0 && <ul className="equipment-queue-list" aria-label="Equipment request queue">
      {lines.map((line) => <li key={line.id}><a className="equipment-queue-card" href={`#/equipment-requests/${line.id}`}>
        <span className="equipment-queue-count"><strong>{line.quantity}</strong><span>{line.quantity === 1 ? 'unit' : 'units'}</span></span>
        <span className="equipment-queue-content">
          <strong className="equipment-queue-name">{line.equipmentName || line.equipmentType}</strong>
          <span>{line.eventTitle || `Event ${line.eventId}`} · Requested {formatRecordedAt(line.createdAt)}</span>
          <span>Needed {formatBookingTimes(line.startsAt, line.endsAt)}</span>
          {line.technicalRequirements && <span>Technical requirements: {line.technicalRequirements}</span>}
        </span>
        <span className={`equipment-request-status is-${line.status.toLowerCase()}`}>{line.status}</span>
        <span className="equipment-queue-arrow" aria-hidden="true">›</span>
      </a></li>)}
    </ul>}
  </div>
}
