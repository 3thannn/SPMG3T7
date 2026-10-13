import { useEffect, useState } from 'react'
import '../equipment.css'
import type { Session } from '../api'
import { equipmentErrorMessage, getEquipment, listEquipment, saveEquipment, type Equipment, type EquipmentInput } from '../equipmentStore'
import { can } from '../permissions'
import { navigate } from '../router'

export function EquipmentPage({ session }: { session: Session }) {
  const [items, setItems] = useState<Equipment[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    listEquipment(session).then(setItems).catch((e: unknown) => setError(equipmentErrorMessage(e, 'load equipment')))
  }, [session])
  return <div className="page shell">
    <header className="page-head"><div><h1 className="page-title">Equipment catalogue</h1>
      <p className="page-subtitle">Usable stock excludes damaged and maintenance units.</p></div>
      {can(session, 'equipment:write') && <a className="btn btn-primary" href="#/equipment/new">Add equipment</a>}
    </header>
    {error && <p role="alert" className="form-error">{error}</p>}
    {!error && items.length === 0 && <p className="muted">No equipment has been recorded yet.</p>}
    <ul className="equipment-list">
      {items.map((item) => <li className="card card-pad equipment-card" key={item.id}>
        <h2><a href={`#/equipment/${item.id}`}>{item.name}</a></h2><p>{item.type} · {item.location}</p>
        {item.description && <p>{item.description}</p>}
        <p>Usable: <strong>{item.usableQuantity}</strong> of {item.totalQuantity}</p>
        {item.outOfServiceQuantity > 0 && <p>{item.outOfServiceQuantity} out of service: {item.outOfServiceReason}</p>}
        {can(session, 'equipment:write') && <a href={`#/equipment/${item.id}/edit`}>Edit equipment</a>}
      </li>)}
    </ul>
  </div>
}

export function EquipmentDetailPage({ session, id }: { session: Session; id: string }) {
  const [item, setItem] = useState<Equipment | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    getEquipment(id, session).then(setItem)
      .catch((e: unknown) => setError(equipmentErrorMessage(e, 'load equipment')))
  }, [id, session])
  return <div className="page shell">
    <a href="#/equipment">← Equipment catalogue</a>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!item && !error && <p>Loading equipment…</p>}
    {item && <article className="card card-pad equipment-card">
      <h1 className="page-title">{item.name}</h1>
      <p>Type: {item.type}</p><p>Location: {item.location}</p>
      {item.description && <p>Description: {item.description}</p>}
      <p>Usable: <strong>{item.usableQuantity}</strong> of {item.totalQuantity}</p>
      <p>Out of service: {item.outOfServiceQuantity}</p>
      {item.outOfServiceQuantity > 0 && <p>Reason: {item.outOfServiceReason}</p>}
      {can(session, 'equipment:write') && <a href={`#/equipment/${id}/edit`}>Edit equipment</a>}
    </article>}
  </div>
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
  return <div className="page shell"><h1 className="page-title">{id ? 'Edit equipment' : 'Add equipment'}</h1>
    {error && <p role="alert" className="form-error">{error}</p>}
    <form className="card card-pad equipment-form" onSubmit={(e) => void submit(e)}>
      <label>Name<input required value={form.name} onChange={(e) => change('name', e.target.value)} /></label>
      <label>Type<input required value={form.type} onChange={(e) => change('type', e.target.value)} /></label>
      <label>Description<textarea value={form.description} onChange={(e) => change('description', e.target.value)} /></label>
      <label>Location<input required value={form.location} onChange={(e) => change('location', e.target.value)} /></label>
      <label>Total quantity<input required type="number" min="0" step="1" value={form.totalQuantity} onChange={(e) => change('totalQuantity', Number(e.target.value))} /></label>
      <label>Out-of-service quantity<input required type="number" min="0" step="1" value={form.outOfServiceQuantity} onChange={(e) => change('outOfServiceQuantity', Number(e.target.value))} /></label>
      <label>Out-of-service reason<textarea value={form.outOfServiceReason} onChange={(e) => change('outOfServiceReason', e.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy} type="submit">Save equipment</button>
    </form>
  </div>
}
