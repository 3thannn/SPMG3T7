import { useEffect, useState } from 'react'
import '../equipment.css'
import { ApiError, type Session } from '../api'
import { RequestEditor } from '../components/EventEquipment'
import EquipmentReservation from '../components/EquipmentReservation'
import {
  equipmentErrorMessage, getEquipmentRequest, updateEquipmentRequest, valuesFor,
  type EquipmentRequestDetail,
} from '../equipmentStore'
import { formatEquipmentTimes } from '../equipmentStore'
import { formatRecordedAt } from '../status'

export default function EquipmentRequestDetailPage({ session, id }: { session: Session; id: string }) {
  const [request, setRequest] = useState<EquipmentRequestDetail | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState('')

  useEffect(() => {
    let cancelled = false
    getEquipmentRequest(id, session).then((loaded) => {
      if (!cancelled) setRequest(loaded)
    }).catch((cause: unknown) => {
      if (cancelled) return
      if (cause instanceof ApiError && cause.status === 404) setMissing(true)
      else setError(equipmentErrorMessage(cause, 'load this equipment request'))
    })
    return () => { cancelled = true }
  }, [id, session])

  return <div className="page shell equipment-request-detail">
    <a className="equipment-request-back" href="#/equipment-requests">← All equipment requests</a>
    {error && <p className="form-error" role="alert">{error}</p>}
    {missing && <div className="card empty"><h1>Request not found</h1><p>This equipment request is no longer available.</p></div>}
    {!request && !missing && !error && <p>Loading request…</p>}
    {request && <>
      <header className="equipment-request-detail-head">
        <div><h1 className="page-title">{request.equipmentName || request.equipmentType} request</h1>
          <p className="page-subtitle">{request.eventTitle || `Event ${request.eventId}`} · Requested {formatRecordedAt(request.createdAt)}</p></div>
        <span className={`equipment-request-status is-${request.status.toLowerCase()}`}>{request.status}</span>
      </header>
      {request.status === 'Removed' && <p className="equipment-removed-notice" role="status">
        {request.removedByName || 'The Coordinator'} removed this request.
      </p>}
      {saved && <p className="equipment-saved" role="status">{saved}</p>}
      <div className="equipment-request-detail-grid">
        <section className="card card-pad" aria-labelledby="equipment-request-details-title">
          <h2 className="detail-section-title" id="equipment-request-details-title">Request details</h2>
          <dl className="equipment-request-facts">
            <div><dt>Catalogue item</dt><dd>{request.equipmentName || `Legacy request - ${request.equipmentType} (specific item not recorded)`}</dd></div>
            <div><dt>Equipment type</dt><dd>{request.equipmentType}</dd></div>
            <div><dt>Quantity</dt><dd>{request.quantity}</dd></div>
            <div><dt>Needed</dt><dd>{formatEquipmentTimes(request.startsAt, request.endsAt)}</dd></div>
            <div><dt>Technical requirements</dt><dd>{request.technicalRequirements || 'None specified'}</dd></div>
            <div><dt>Arrangement notes</dt><dd>{request.supportNotes || 'Not recorded yet'}</dd></div>
            {request.equipmentId && <div><dt>Reserved catalogue item</dt><dd>#{request.equipmentId}</dd></div>}
            {request.unavailableReason && <div><dt>Unavailable reason</dt><dd>{request.unavailableReason}</dd></div>}
          </dl>
        </section>
        <aside className="card card-pad equipment-request-detail-action">
          <h2 className="detail-section-title">Technical Support</h2>
          {request.status !== 'Requested' ?
            <p className="muted">{request.status === 'Unavailable'
              ? 'The Coordinator can revise and resubmit this request or remove it while the event is Planning.'
              : 'This request can no longer be updated.'}</p> : editing ?
              <RequestEditor key={request.version} initial={valuesFor(request)} items={[]} support embedded
                onSave={async (changes) => {
                  await updateEquipmentRequest(request.id, { ...changes, version: request.version }, session)
                  setEditing(false)
                  setSaved('Request updated.')
                  try { setRequest(await getEquipmentRequest(id, session)); setError('') }
                  catch (cause) { setError(equipmentErrorMessage(cause, 'refresh this request')) }
                }}
                onCancel={() => setEditing(false)} /> : <>
                <p className="muted">Review the request and record how it will be arranged.</p>
                <button type="button" className="btn btn-secondary" onClick={() => { setEditing(true); setSaved('') }}>Update request</button>
              </>}
          {request.status === 'Requested' && !editing && <EquipmentReservation key={request.version}
            request={request} session={session}
            onRefresh={async () => { setRequest(await getEquipmentRequest(id, session)) }}
            onDecided={(updated) => {
              setRequest({ ...request, ...updated }); setSaved(`Equipment ${updated.status.toLowerCase()}.`)
            }} />}
        </aside>
      </div>
    </>}
  </div>
}
