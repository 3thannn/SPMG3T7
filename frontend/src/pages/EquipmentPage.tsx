import { useEffect, useState } from 'react'
import '../equipment.css'
import type { Session } from '../api'
import {
  deleteEquipment, equipmentErrorMessage, getEquipment, listEquipment, saveEquipment,
  type Equipment, type EquipmentInput,
} from '../equipmentStore'
import { can } from '../permissions'
import { navigate } from '../router'

export function EquipmentPage({ session }: { session: Session }) {
  const [items, setItems] = useState<Equipment[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    listEquipment(session).then((loaded) => { if (!cancelled) setItems(loaded) })
      .catch((cause: unknown) => { if (!cancelled) setError(equipmentErrorMessage(cause, 'load equipment')) })
    return () => { cancelled = true }
  }, [session])
  return <div className="page"><div className="shell">
    <header className="page-head"><div><h1 className="page-title">Equipment catalogue</h1>
      <p className="page-subtitle">Open an item for its full details and usable stock.</p></div>
      {can(session, 'equipment:write') && <a className="btn btn-primary" href="#/equipment/new">Add equipment</a>}
    </header>
    {error && <p role="alert" className="form-error">{error}</p>}
    {items === null && !error && <p className="muted">Loading equipment…</p>}
    {items?.length === 0 && <div className="card empty"><h2>No equipment yet</h2>
      <p>{can(session, 'equipment:write') ? 'Add the first item to the catalogue.' : 'Equipment will appear here when Technical Support adds it.'}</p></div>}
    {items && items.length > 0 && <ul className="equipment-list" aria-label="Equipment catalogue">
      {items.map((item) => <li key={item.id}><a className="equipment-card" href={`#/equipment/${item.id}`}>
        <span className="equipment-stock"><strong>{item.usableQuantity}</strong><span>Usable of {item.totalQuantity}</span></span>
        <span className="equipment-card-content"><strong className="equipment-card-name">{item.name}</strong>
          <span className="equipment-card-meta">{item.type} · {item.location}</span></span>
        <span className="equipment-card-arrow" aria-hidden="true">›</span>
      </a></li>)}
    </ul>}
  </div></div>
}

export function EquipmentDetailPage({ session, id }: { session: Session; id: string }) {
  const [item, setItem] = useState<Equipment | null>(null)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let cancelled = false
    getEquipment(id, session).then((loaded) => { if (!cancelled) setItem(loaded) })
      .catch((cause: unknown) => { if (!cancelled) setError(equipmentErrorMessage(cause, 'load equipment')) })
    return () => { cancelled = true }
  }, [id, session])
  async function remove() {
    setBusy(true)
    setError('')
    try {
      await deleteEquipment(id, session)
      navigate('/equipment')
    } catch (cause) {
      setError(equipmentErrorMessage(cause, 'delete equipment'))
      setConfirming(false)
      setBusy(false)
    }
  }
  return <div className="page"><div className="shell">
    <a className="equipment-back" href="#/equipment">← Back to equipment</a>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!item && !error && <p className="muted">Loading equipment…</p>}
    {item && <><header className="equipment-detail-head"><div><h1 className="page-title">{item.name}</h1>
      <p className="page-subtitle">{item.type} · {item.location}</p></div>
      {!can(session, 'equipment:write') && <span className="equipment-readonly-tag">Read-only</span>}</header>
      <section className="card equipment-detail-card" aria-label="Equipment details">
        <h2 className="equipment-section-title">Equipment details</h2>
        <dl className="equipment-readonly">
          <dt>Type</dt><dd>{item.type}</dd>
          <dt>Location</dt><dd>{item.location}</dd>
          <dt>Description</dt><dd>{item.description || 'Not recorded'}</dd>
          <dt>Total quantity</dt><dd>{item.totalQuantity}</dd>
          <dt>Usable quantity</dt><dd>{item.usableQuantity}</dd>
          <dt>Out of service</dt><dd>{item.outOfServiceQuantity}</dd>
          <dt>Out-of-service reason</dt><dd>{item.outOfServiceQuantity === 0 ? 'Not applicable' : item.outOfServiceReason || 'Not recorded'}</dd>
        </dl>
      </section>
      {can(session, 'equipment:write') && <section className="card equipment-actions">
        <h2 className="equipment-section-title">Maintain this record</h2>
        {confirming ? <><p>Delete <strong>{item.name}</strong> from the catalogue? This cannot be undone.</p>
          <div className="equipment-action-row"><button className="btn btn-danger-solid" type="button" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Yes, delete it'}</button>
            <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => setConfirming(false)}>Keep it</button></div></> :
          <div className="equipment-action-row"><a className="btn btn-primary" href={`#/equipment/${id}/edit`}>Edit equipment</a>
            <button className="btn btn-danger" type="button" onClick={() => setConfirming(true)}>Delete equipment</button></div>}
      </section>}</>}
  </div></div>
}

const blank: EquipmentInput = {
  name: '', type: '', description: '', location: '', totalQuantity: 0,
  outOfServiceQuantity: 0, outOfServiceReason: '',
}

export function EquipmentFormPage({ session, id }: { session: Session; id?: string }) {
  const [form, setForm] = useState<EquipmentInput>(blank)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (id) getEquipment(id, session).then((item) => setForm({
      name: item.name, type: item.type, description: item.description,
      location: item.location, totalQuantity: item.totalQuantity,
      outOfServiceQuantity: item.outOfServiceQuantity,
      outOfServiceReason: item.outOfServiceReason,
    })).catch((e: unknown) => setError(equipmentErrorMessage(e, 'load equipment')))
  }, [id, session])
  function change<K extends keyof EquipmentInput>(key: K, value: EquipmentInput[K]) {
    setForm((old) => ({ ...old, [key]: value }))
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    if (!Number.isInteger(form.totalQuantity) || !Number.isInteger(form.outOfServiceQuantity)
      || form.totalQuantity < 0 || form.outOfServiceQuantity < 0
      || form.outOfServiceQuantity > form.totalQuantity) {
      setError('Enter whole-number quantities with out-of-service units no greater than the total.')
      return
    }
    if (form.outOfServiceQuantity > 0 && !form.outOfServiceReason.trim()) {
      setError('Give a reason for out-of-service units.')
      return
    }
    setBusy(true)
    try {
      await saveEquipment(form, session, id)
      navigate('/equipment')
    } catch (e) {
      setError(equipmentErrorMessage(e, 'save equipment'))
    } finally { setBusy(false) }
  }
  return <div className="page"><div className="shell equipment-form-shell">
    <a className="equipment-back" href={id ? `#/equipment/${id}` : '#/equipment'}>← Back to equipment</a>
    <h1 className="page-title">{id ? 'Edit equipment' : 'Add equipment'}</h1>
    {error && <p role="alert" className="form-error">{error}</p>}
    <form className="card equipment-form" onSubmit={(e) => void submit(e)}>
      <fieldset className="equipment-fieldset" disabled={busy}>
        <legend className="equipment-section-title">Equipment details</legend>
        <div className="field"><label htmlFor="equipment-name">Name</label><input id="equipment-name" required maxLength={255} value={form.name} onChange={(e) => change('name', e.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-type">Type</label><input id="equipment-type" required maxLength={100} value={form.type} onChange={(e) => change('type', e.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-description">Description</label><textarea id="equipment-description" value={form.description} onChange={(e) => change('description', e.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-location">Location</label><input id="equipment-location" required value={form.location} onChange={(e) => change('location', e.target.value)} /></div>
        <div className="field"><label htmlFor="equipment-total">Total quantity</label><input id="equipment-total" required type="number" min="0" step="1" value={form.totalQuantity} onChange={(e) => change('totalQuantity', Number(e.target.value))} /></div>
        <div className="field"><label htmlFor="equipment-out">Out-of-service quantity</label><input id="equipment-out" required type="number" min="0" step="1" value={form.outOfServiceQuantity} onChange={(e) => change('outOfServiceQuantity', Number(e.target.value))} /></div>
        <div className="field"><label htmlFor="equipment-reason">Out-of-service reason</label><textarea id="equipment-reason" value={form.outOfServiceReason} onChange={(e) => change('outOfServiceReason', e.target.value)} /></div>
      </fieldset>
      <div className="equipment-action-row"><button className="btn btn-primary" disabled={busy} type="submit">{busy ? 'Saving…' : 'Save equipment'}</button>
        <a className="btn btn-secondary" href={id ? `#/equipment/${id}` : '#/equipment'}>Cancel</a></div>
    </form>
  </div></div>
}
