import { useEffect, useState } from 'react'
import '../equipment.css'
import type { Session } from '../api'
import {
  createEquipmentRequest, equipmentErrorMessage, listEquipment, listEventEquipmentRequests,
  removeEquipmentRequest, updateEquipmentRequest, valuesFor,
  type EquipmentRequest, type RequestChanges, type RequestFormValues,
} from '../equipmentStore'
import type { EventRecord } from '../eventsStore'

function localTime(value: string): string { return value.slice(0, 16) }

export function RequestEditor({ initial, types, support, onSave, onCancel }: {
  initial: RequestFormValues
  types: string[]
  support: boolean
  onSave: (value: RequestChanges) => Promise<void>
  onCancel: () => void
}) {
  const [value, setValue] = useState<RequestFormValues>(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const quantity = Number(value.quantity)
    if (!Number.isInteger(quantity) || quantity < 1) {
      setError('Quantity must be a whole number of at least one.')
      return
    }
    if (!value.startsAt || !value.endsAt || value.endsAt <= value.startsAt) {
      setError('The needed end time must be after the start time.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onSave({
        ...(support ? {} : { equipmentType: value.equipmentType, technicalRequirements: value.technicalRequirements }),
        ...(support ? { supportNotes: value.supportNotes } : {}),
        quantity, startsAt: value.startsAt, endsAt: value.endsAt,
      })
    } catch (e) { setError(equipmentErrorMessage(e, 'save the request')) }
    finally { setBusy(false) }
  }
  return <form className="card card-pad equipment-form" onSubmit={(e) => void submit(e)}>
    {error && <p role="alert" className="form-error">{error}</p>}
    {support ? <p><strong>Type:</strong> {value.equipmentType}</p> :
      <label>Equipment type<select required value={value.equipmentType} onChange={(e) => setValue({ ...value, equipmentType: e.target.value })}>
        <option value="">Choose a type</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}
      </select></label>}
    <label>Quantity<input required type="number" min="1" step="1" value={value.quantity} onChange={(e) => setValue({ ...value, quantity: e.target.value })} /></label>
    {support ? <p><strong>Technical requirements:</strong> {value.technicalRequirements || 'None'}</p> :
      <label>Technical requirements<textarea value={value.technicalRequirements} onChange={(e) => setValue({ ...value, technicalRequirements: e.target.value })} /></label>}
    {support && <label>Arrangement notes<textarea value={value.supportNotes} onChange={(e) => setValue({ ...value, supportNotes: e.target.value })} /></label>}
    <label>Needed from<input required type="datetime-local" value={value.startsAt} onChange={(e) => setValue({ ...value, startsAt: e.target.value })} /></label>
    <label>Needed until<input required type="datetime-local" value={value.endsAt} onChange={(e) => setValue({ ...value, endsAt: e.target.value })} /></label>
    <button className="btn btn-primary" type="submit" disabled={busy}>Save request</button>{' '}
    <button className="btn btn-secondary" type="button" onClick={onCancel}>Cancel</button>
  </form>
}

export default function EventEquipment({ event, session, onChanged }: {
  event: EventRecord; session: Session; onChanged?: () => void
}) {
  const [lines, setLines] = useState<EquipmentRequest[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [editing, setEditing] = useState<string | null>(null)
  const [error, setError] = useState('')
  const assigned = session.role === 'Event Coordinator' && event.coordinatorId === session.id
  const planning = event.status === 'Planning'
  useEffect(() => {
    if (!assigned) return
    Promise.all([listEventEquipmentRequests(event.id, session), listEquipment(session)])
      .then(([requests, catalogue]) => {
        setLines(requests)
        const distinct = new Map<string, string>()
        for (const item of catalogue) {
          if (!distinct.has(item.type.toLowerCase())) distinct.set(item.type.toLowerCase(), item.type)
        }
        setTypes([...distinct.values()].sort())
      }).catch((e: unknown) => setError(equipmentErrorMessage(e, 'load equipment requests')))
  }, [assigned, event.id, session])
  if (!assigned) return null
  async function reload() {
    setLines(await listEventEquipmentRequests(event.id, session))
    setEditing(null)
  }
  async function remove(line: EquipmentRequest) {
    setError('')
    try { await removeEquipmentRequest(line.id, line.version, session); onChanged?.(); await reload() }
    catch (e) { setError(equipmentErrorMessage(e, 'remove the request')); await reload() }
  }
  return <section className="card card-pad" aria-label="Equipment requests">
    <h2>Equipment requests</h2>
    {error && <p role="alert" className="form-error">{error}</p>}
    {lines.length === 0 && <p>No equipment requested yet.</p>}
    {lines.map((line) => <div key={line.id} className="card card-pad equipment-line">
      <h3>{line.equipmentType} · {line.quantity} · {line.status}</h3>
      <p>Needed {localTime(line.startsAt)} to {localTime(line.endsAt)}</p>
      <p>Technical requirements: {line.technicalRequirements || 'None'}</p>
      {line.supportNotes && <p>Tech Support: {line.supportNotes}</p>}
      {planning && editing === line.id ? <RequestEditor key={line.version} initial={valuesFor(line)} types={[...new Set([line.equipmentType, ...types])]} support={false}
        onSave={async (changes) => { await updateEquipmentRequest(line.id, { ...changes, version: line.version }, session); onChanged?.(); await reload() }}
        onCancel={() => setEditing(null)} /> : planning && <><button type="button" className="btn btn-secondary" onClick={() => setEditing(line.id)}>Edit</button>{' '}
        <button type="button" className="btn btn-secondary" onClick={() => void remove(line)}>Remove</button></>}
    </div>)}
    {planning && (editing === 'new' ? <RequestEditor initial={{ equipmentType: '', quantity: '1', technicalRequirements: '', supportNotes: '', startsAt: localTime(event.startsAt), endsAt: localTime(event.endsAt || '') }} types={types} support={false}
      onSave={async (changes) => { await createEquipmentRequest(event.id, changes, session); onChanged?.(); await reload() }} onCancel={() => setEditing(null)} /> :
      <button type="button" className="btn btn-primary" disabled={types.length === 0} onClick={() => setEditing('new')}>Add equipment request</button>)}
    {planning && types.length === 0 && <p>Add equipment to the catalogue before requesting it.</p>}
  </section>
}
