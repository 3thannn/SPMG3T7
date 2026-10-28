import { useEffect, useState } from 'react'
import '../equipment.css'
import type { Session } from '../api'
import {
  createEquipmentRequest, equipmentErrorMessage, listEquipment, listEventEquipmentRequests,
  removeEquipmentRequest, updateEquipmentRequest, valuesFor,
  type EquipmentRequest, type RequestChanges, type RequestFormValues,
} from '../equipmentStore'
import type { EventRecord } from '../eventsStore'
import { formatEquipmentTimes } from '../equipmentStore'

function localTime(value: string): string { return value.slice(0, 16) }

export function RequestEditor({ initial, types, support, onSave, onCancel, embedded = false, idPrefix = 'request', resubmitting = false }: {
  initial: RequestFormValues
  types: string[]
  support: boolean
  onSave: (value: RequestChanges) => Promise<void>
  onCancel?: () => void
  embedded?: boolean
  idPrefix?: string
  resubmitting?: boolean
}) {
  const fieldId = (field: string) => `${idPrefix}-equipment-${field}`
  const [value, setValue] = useState<RequestFormValues>(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!support && !value.equipmentType.trim()) {
      setError('Choose an equipment type.')
      return
    }
    const quantity = Number(value.quantity)
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 2_147_483_647) {
      setError('Quantity must be a whole number between one and 2,147,483,647.')
      return
    }
    if (!value.startsAt || !value.endsAt || value.endsAt <= value.startsAt) {
      setError(value.endsAt ? 'The needed end time must be after the start time.' : 'Enter a needed end time for this equipment request.')
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
      if (embedded && !onCancel) {
        setValue((current) => ({ ...current, equipmentType: '', quantity: '1', technicalRequirements: '' }))
      }
    } catch (cause) { setError(equipmentErrorMessage(cause, 'save the request')) }
    finally { setBusy(false) }
  }
  return <form className={`equipment-form${embedded ? ' equipment-request-form' : ' card card-pad'}`} onSubmit={(event) => void submit(event)} noValidate>
    {embedded && <><h3 className="equipment-request-form-title">{resubmitting ? 'Revise and resubmit equipment request' : onCancel ? 'Edit equipment request' : 'Request equipment'}</h3>
      <p className="equipment-request-form-hint">{support
        ? 'Record arrangement notes and confirm the requested quantity and times.'
        : 'Request each equipment type separately. Technical Support will review the details.'}</p></>}
    {error && <p role="alert" className="form-error">{error}</p>}
    <fieldset className="equipment-fieldset" disabled={busy}>
      {support ? <div className="equipment-readonly-field"><span>Equipment type</span><strong>{value.equipmentType}</strong></div> :
        <div className="field"><label htmlFor={fieldId('type')}>Equipment type</label><select id={fieldId('type')} required value={value.equipmentType} onChange={(event) => setValue({ ...value, equipmentType: event.target.value })}>
          <option value="">Choose a type</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}
        </select></div>}
      <div className="field"><label htmlFor={fieldId('start')}>Needed from</label><input id={fieldId('start')} required type="datetime-local" value={value.startsAt} onChange={(event) => setValue({ ...value, startsAt: event.target.value })} /></div>
      <div className="field"><label htmlFor={fieldId('end')}>Needed until</label><input id={fieldId('end')} required type="datetime-local" min={value.startsAt || undefined} value={value.endsAt} onChange={(event) => setValue({ ...value, endsAt: event.target.value })} /></div>
      <div className="field"><label htmlFor={fieldId('quantity')}>Quantity</label><input id={fieldId('quantity')} required type="number" min="1" max="2147483647" step="1" inputMode="numeric" value={value.quantity} onChange={(event) => setValue({ ...value, quantity: event.target.value })} /><span className="field-hint">Units needed for this event.</span></div>
      {support ? <div className="equipment-readonly-field"><span>Technical requirements</span><strong>{value.technicalRequirements || 'None specified'}</strong></div> :
        <div className="field equipment-requirements"><label htmlFor={fieldId('requirements')}>Technical requirements (optional)</label><textarea id={fieldId('requirements')} value={value.technicalRequirements} onChange={(event) => setValue({ ...value, technicalRequirements: event.target.value })} /></div>}
      {support && <div className="field"><label htmlFor={fieldId('notes')}>Arrangement notes</label><textarea id={fieldId('notes')} value={value.supportNotes} onChange={(event) => setValue({ ...value, supportNotes: event.target.value })} /></div>}
    </fieldset>
    <div className="equipment-action-row"><button className="btn btn-primary" type="submit" disabled={busy || (!support && types.length === 0)}>{busy ? 'Saving…' : resubmitting ? 'Resubmit request' : onCancel ? 'Save request' : 'Request equipment'}</button>
      {onCancel && <button className="btn btn-secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button>}</div>
  </form>
}

export default function EventEquipment({ event, session }: {
  event: EventRecord; session: Session
}) {
  const [lines, setLines] = useState<EquipmentRequest[] | null>(null)
  const [types, setTypes] = useState<string[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [catalogueError, setCatalogueError] = useState('')
  const [actionError, setActionError] = useState('')
  const [saved, setSaved] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const mayRequest = session.role === 'Event Coordinator' && event.coordinatorId === session.id
  const planning = event.status === 'Planning'
  useEffect(() => {
    if (event.status === 'Draft') return
    let cancelled = false
    listEventEquipmentRequests(event.id, session).then((loaded) => { if (!cancelled) setLines(loaded) })
      .catch((cause: unknown) => { if (!cancelled) setLoadError(equipmentErrorMessage(cause, 'load equipment requests')) })
    return () => { cancelled = true }
  }, [event.id, event.status, session])
  useEffect(() => {
    if (!mayRequest || !planning) return
    let cancelled = false
    listEquipment(session).then((catalogue) => {
      if (cancelled) return
      const distinct = new Map<string, string>()
      for (const item of catalogue) {
        if (!distinct.has(item.type.toLowerCase())) distinct.set(item.type.toLowerCase(), item.type)
      }
      setTypes([...distinct.values()].sort())
    }).catch((cause: unknown) => {
      if (!cancelled) setCatalogueError(equipmentErrorMessage(cause, 'load the equipment catalogue'))
    })
    return () => { cancelled = true }
  }, [mayRequest, planning, session])
  async function reload() {
    setEditing(null)
    try {
      setLines(await listEventEquipmentRequests(event.id, session))
      setLoadError('')
    } catch (cause) {
      setLoadError(equipmentErrorMessage(cause, 'refresh equipment requests'))
    }
  }
  async function remove(line: EquipmentRequest) {
    setActionError('')
    try {
      await removeEquipmentRequest(line.id, line.version, session)
      await reload()
      setSaved(`Removed ${line.equipmentType} request.`)
    } catch (cause) { setActionError(equipmentErrorMessage(cause, 'remove the request')) }
  }
  if (event.status === 'Draft') return null
  return <section className="card card-pad event-equipment" aria-labelledby="event-equipment-title">
    <h2 className="detail-section-title" id="event-equipment-title">Equipment requests</h2>
    <p className="event-equipment-lede">Each equipment type is requested separately for Technical Support to review.</p>
    {loadError && <><p role="alert" className="form-error">{loadError}</p>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => void reload()}>Retry equipment requests</button></>}
    {actionError && <p role="alert" className="form-error">{actionError}</p>}
    {saved && <p role="status" className="equipment-saved">{saved}</p>}
    {lines === null && !loadError && <p className="muted">Loading equipment requests…</p>}
    {lines?.length === 0 && <p className="muted equipment-none">No equipment has been requested for this event yet.</p>}
    {lines && lines.length > 0 && <ul className="equipment-request-list" aria-label="Equipment requests for this event">
      {lines.map((line) => <li key={line.id} className="equipment-request-row">
        <div className="equipment-request-summary"><span className="equipment-request-name">{line.equipmentType}</span>
          <span className="equipment-request-times">{formatEquipmentTimes(line.startsAt, line.endsAt)}</span>
          <span className="equipment-request-status">{line.status}</span>
          {mayRequest && planning && (line.status === 'Requested' || line.status === 'Unavailable') && !loadError && <span className="equipment-request-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(line.id)}>{line.status === 'Unavailable' ? 'Revise and resubmit' : 'Edit'}</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void remove(line)}>Remove</button></span>}</div>
        <p className="equipment-request-note">Quantity: {line.quantity}</p>
        {line.equipmentId && <p className="equipment-request-note">Reserved catalogue item: #{line.equipmentId}</p>}
        {line.unavailableReason && <p className="equipment-request-note">Unavailable reason: {line.unavailableReason}</p>}
        {mayRequest && planning && line.status === 'Unavailable' && <p className="equipment-request-note">Revise and resubmit for Technical Support to review again, or remove this line if it is no longer needed.</p>}
        {line.technicalRequirements && <p className="equipment-request-note">Technical requirements: {line.technicalRequirements}</p>}
        {line.supportNotes && <p className="equipment-request-note">Technical Support: {line.supportNotes}</p>}
        {mayRequest && planning && !loadError && editing === line.id && <RequestEditor key={line.version} initial={valuesFor(line)} types={[...new Set([line.equipmentType, ...(types || [])])]} support={false} embedded idPrefix={line.id} resubmitting={line.status === 'Unavailable'}
          onSave={async (changes) => { await updateEquipmentRequest(line.id, { ...changes, version: line.version }, session); await reload(); setSaved(`${line.status === 'Unavailable' ? 'Resubmitted' : 'Updated'} ${line.equipmentType} request.`) }}
          onCancel={() => setEditing(null)} />}
      </li>)}
    </ul>}
    {mayRequest && planning && lines !== null && !loadError && <>
      {catalogueError && <p role="alert" className="form-error">{catalogueError}</p>}
      {types === null && !catalogueError && <p className="muted">Loading equipment catalogue…</p>}
      {types?.length === 0 && <p className="detail-note">Add equipment to the catalogue before requesting it.</p>}
      {!catalogueError && <RequestEditor initial={{ equipmentType: '', quantity: '1', technicalRequirements: '', supportNotes: '', startsAt: localTime(event.startsAt), endsAt: localTime(event.endsAt || '') }} types={types || []} support={false} embedded idPrefix="new"
        onSave={async (changes) => { await createEquipmentRequest(event.id, changes, session); await reload(); setSaved('Equipment request sent to Technical Support.') }} />
      }
    </>}
    {mayRequest && event.status === 'Approved' && <p className="detail-note">Request the first venue to move this event to Planning, then request equipment here.</p>}
  </section>
}
