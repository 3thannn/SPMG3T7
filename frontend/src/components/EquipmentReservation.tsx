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
  const stock = items?.find((item) => item.equipmentId === request.requestedEquipmentId)
  async function decide(reserve: boolean) {
    // Not reachable from the card: both buttons are disabled while busy, and
    // Reserve is disabled without enough stock. Kept as the rule itself.
    /* v8 ignore next */
    if (busy) return
    if (!reserve && !reason.trim()) { setError('Give a reason for marking this request Unavailable.'); return }
    /* v8 ignore next */
    if (reserve && (!stock || stock.shortfall > 0)) return
    setBusy(true)
    setError('')
    try {
      const updated = await decideEquipmentRequest(request.id, request.version,
        reserve ? { equipmentId: Number(request.requestedEquipmentId) } : { reason: reason.trim() }, session)
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
  return <section className="equipment-reservation" aria-labelledby="equipment-reservation-title">
    <h3 id="equipment-reservation-title">Reserve equipment</h3>
    <p className="muted">Availability uses the saved needed-from/until times (SGT).</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    <button className="btn btn-secondary btn-sm" type="button" disabled={busy}
      onClick={() => { setItems(null); setError(''); setRefresh((value) => value + 1) }}>Refresh availability</button>
    {items === null && !error && <p role="status">Loading availability…</p>}
    {items?.length === 0 && <p>No item has been selected for this request. Ask the Coordinator to revise it and select a catalogue item.</p>}
    <fieldset className="equipment-fieldset" disabled={busy}>
      {stock && <div className="equipment-availability-summary" aria-live="polite">
        <dl className="equipment-availability-counts">
          <div className="equipment-availability-primary"><dt>Available</dt><dd>{stock.availableQuantity}<span> units</span></dd></div>
          <div><dt>Requested</dt><dd>{request.quantity}<span> units</span></dd></div>
        </dl>
        <dl className="equipment-availability-breakdown">
          <div><dt>Storage location</dt><dd>{stock.location}</dd></div>
          <div><dt>Total stock</dt><dd>{stock.totalQuantity}</dd></div>
          <div><dt>Out of service</dt><dd>{stock.outOfServiceQuantity}</dd></div>
          <div><dt>Already reserved</dt><dd>{stock.reservedQuantity}</dd></div>
        </dl>
        {stock.shortfall > 0 && <p className="equipment-availability-shortfall" role="status">Shortfall: {stock.shortfall}. Mark this line Unavailable so the Coordinator can revise the item or quantity.</p>}
      </div>}
      <button className="btn btn-primary" type="button" disabled={busy || !stock || stock.shortfall > 0}
        onClick={() => void decide(true)}>{busy ? 'Saving…' : 'Reserve'}</button>
      <div className="field"><label htmlFor="unavailable-reason">Reason for Unavailable</label>
        <textarea id="unavailable-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </div>
      <button className="btn btn-secondary" type="button" disabled={busy}
        onClick={() => void decide(false)}>Mark Unavailable</button>
    </fieldset>
  </section>
}
