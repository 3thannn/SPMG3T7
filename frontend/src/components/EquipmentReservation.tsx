import { useEffect, useState } from 'react'
import type { Session } from '../api'
import {
  decideEquipmentRequest, equipmentErrorMessage, getEquipmentAvailability,
  type EquipmentAvailability, type EquipmentRequest,
} from '../equipmentStore'

export default function EquipmentReservation({ request, session, onDecided, onRefresh }: {
  request: EquipmentRequest; session: Session
  onDecided: (request: EquipmentRequest) => void
  onRefresh: () => Promise<void>
}) {
  const [items, setItems] = useState<EquipmentAvailability[] | null>(null)
  const [selected, setSelected] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let cancelled = false
    getEquipmentAvailability(request.id, session).then((result) => {
      if (!cancelled) { setItems(result); setError('') }
    }).catch((cause) => {
      if (!cancelled) setError(equipmentErrorMessage(cause, 'load availability'))
    })
    return () => { cancelled = true }
  }, [request.id, request.version, session, refresh])
  const stock = items?.find((item) => item.equipmentId === selected)
  async function decide(reserve: boolean) {
    if (busy) return
    if (!reserve && !reason.trim()) { setError('Give a reason for marking this request Unavailable.'); return }
    if (reserve && (!stock || stock.shortfall > 0)) return
    setBusy(true)
    setError('')
    try {
      const updated = await decideEquipmentRequest(request.id, request.version,
        reserve ? { equipmentId: Number(selected) } : { reason: reason.trim() }, session)
      onDecided(updated)
    } catch (cause) {
      setError(equipmentErrorMessage(cause, 'save this equipment decision'))
      setItems(null)
      try {
        const [latest] = await Promise.all([getEquipmentAvailability(request.id, session), onRefresh()])
        setItems(latest)
      } catch { /* Keep the decision error visible; explicit refresh can retry. */ }
    } finally { setBusy(false) }
  }
  return <section aria-labelledby="equipment-reservation-title">
    <h3 id="equipment-reservation-title">Reserve equipment</h3>
    <p className="muted">Availability uses the saved needed-from/until times (SGT).</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    <button className="btn btn-secondary btn-sm" type="button" disabled={busy}
      onClick={() => { setItems(null); setError(''); setRefresh((value) => value + 1) }}>Refresh availability</button>
    {items === null && !error && <p role="status">Loading availability…</p>}
    {items?.length === 0 && <p>No matching catalogue items are available.</p>}
    <fieldset className="equipment-fieldset" disabled={busy}>
      <div className="field"><label htmlFor="reservation-item">Catalogue item</label>
        <select id="reservation-item" value={selected} onChange={(event) => setSelected(event.target.value)}>
          <option value="">Choose an item</option>
          {items?.map((item) => <option key={item.equipmentId} value={item.equipmentId}>
            {item.name} — {item.location} ({item.availableQuantity} available)
          </option>)}
        </select>
      </div>
      {stock && <div aria-live="polite">
        <p>Total: {stock.totalQuantity} · Out of service: {stock.outOfServiceQuantity} · Already reserved: {stock.reservedQuantity}</p>
        <p>Available: {stock.availableQuantity} · Requested: {request.quantity}</p>
        {stock.shortfall > 0 && <p role="status">Shortfall: {stock.shortfall}. Choose another item or mark this line Unavailable.</p>}
      </div>}
      <button className="btn btn-primary" type="button" disabled={busy || !stock || stock.shortfall > 0}
        onClick={() => void decide(true)}>{busy ? 'Saving…' : 'Reserve'}</button>
      <div className="field"><label htmlFor="unavailable-reason">Reason for Unavailable</label>
        <textarea id="unavailable-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
        {stock && <button className="btn btn-secondary btn-sm" type="button" onClick={() => {
          const summary = `${stock.name}: ${request.quantity} requested, ${stock.availableQuantity} available, shortfall ${stock.shortfall} (at time of review).`
          setReason((current) => current.trim() ? `${current.trim()} ${summary}` : summary)
        }}>Add availability to reason</button>}
      </div>
      <button className="btn btn-secondary" type="button" disabled={busy}
        onClick={() => void decide(false)}>Mark Unavailable</button>
    </fieldset>
  </section>
}
