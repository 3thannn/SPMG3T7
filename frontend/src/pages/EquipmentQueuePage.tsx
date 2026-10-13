import { useEffect, useState } from 'react'
import type { Session } from '../api'
import { RequestEditor } from '../components/EventEquipment'
import { equipmentErrorMessage, listEquipmentQueue, updateEquipmentRequest, valuesFor, type EquipmentRequest } from '../equipmentStore'
import { formatTimestamp } from '../status'

export default function EquipmentQueuePage({ session, focusId }: { session: Session; focusId?: string }) {
  const [lines, setLines] = useState<EquipmentRequest[] | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [error, setError] = useState('')
  async function reload() { setLines(await listEquipmentQueue(session)); setEditing(null) }
  useEffect(() => {
    listEquipmentQueue(session).then(setLines)
      .catch((e: unknown) => setError(equipmentErrorMessage(e, 'load equipment requests')))
  }, [session])
  useEffect(() => {
    if (!lines || !focusId) return
    const target = document.getElementById(`request-${focusId}`)
    target?.scrollIntoView?.({ block: 'center' })
    target?.focus()
  }, [lines, focusId])
  return <div className="page shell">
    <header className="page-head"><div><h1 className="page-title">Equipment requests</h1>
      <p className="page-subtitle">Requested lines, oldest first.</p></div></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    {lines === null && !error && <p>Loading requests…</p>}
    {lines && focusId && !lines.some((line) => line.id === focusId) &&
      <p role="status">This request is no longer in the Requested queue.</p>}
    {lines?.length === 0 && <p>No equipment requests are waiting.</p>}
    {lines?.map((line) => <section className="card card-pad equipment-line" id={`request-${line.id}`} tabIndex={-1} key={line.id}>
      <h2>{line.equipmentType} · {line.quantity}</h2>
      <p>{line.eventTitle || `Event ${line.eventId}`} · Requested {formatTimestamp(line.createdAt)}</p>
      <p>Needed {line.startsAt.slice(0, 16)} to {line.endsAt.slice(0, 16)}</p>
      <p>Technical requirements: {line.technicalRequirements || 'None'}</p>
      {line.supportNotes && <p>Arrangement notes: {line.supportNotes}</p>}
      {editing === line.id ? <RequestEditor key={line.version} initial={valuesFor(line)} types={[]} support
        onSave={async (changes) => { await updateEquipmentRequest(line.id, { ...changes, version: line.version }, session); await reload() }}
        onCancel={() => setEditing(null)} /> :
        <button type="button" className="btn btn-secondary" onClick={() => setEditing(line.id)}>Update request</button>}
    </section>)}
  </div>
}
