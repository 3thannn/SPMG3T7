import { useCallback, useEffect, useState } from 'react'
import './BookingRequestsPage.css'
import {
  DECISION_TEXT_MAX,
  approveBookingRequest,
  describePeriod,
  listBookingRequests,
  rejectBookingRequest,
  type BookingRequest,
} from '../bookingRequestsStore'
import { CONFLICT_LABEL, EventRuleError, formatBookingTimes } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

type BookingRequestsPageProps = {
  session: Session
}

type Queue =
  | { state: 'loading' }
  | { state: 'loaded'; requests: BookingRequest[] }
  | { state: 'error'; message: string }

type Rejecting = { bookingId: string; reason: string; suggestion: string }

/** US14.3: a request being approved as a tentative hold, and until when. */
type Holding = { bookingId: string; until: string }

function minutes(value: number): string {
  return value === 1 ? '1 minute' : `${value} minutes`
}

/**
 * Venue Staff decide booking requests — US16.1.
 *
 * Every Requested booking, oldest first, with what a decision needs: the event,
 * venue, booking time, the full occupied window including setup and turnaround,
 * headcount and layout. A request that already clashes with a booking taking
 * its slot says so and cannot be approved; the server checks again at approval
 * either way. US15.1: so does one that overlaps a venue unavailability period.
 * US15.2: a request flagged "Conflict – review needed" after a setup or
 * turnaround change says so, with the reason. Rejecting needs a reason and may suggest an alternative. A
 * decided request leaves the queue, and its Coordinator is notified.
 *
 * US14.3 (Week 9): approving can instead place a tentative hold, until an
 * expiry Venue Staff choose. The Coordinator confirms it before then, or the
 * venue is released.
 */
export default function BookingRequestsPage({ session }: BookingRequestsPageProps) {
  const [queue, setQueue] = useState<Queue>({ state: 'loading' })
  const [busy, setBusy] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<Rejecting | null>(null)
  const [holding, setHolding] = useState<Holding | null>(null)
  const [rowError, setRowError] = useState<{ bookingId: string; message: string } | null>(null)
  const [notice, setNotice] = useState('')

  const load = useCallback(
    () =>
      listBookingRequests(session)
        .then((requests) => setQueue({ state: 'loaded', requests }))
        .catch((error: unknown) =>
          setQueue({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the booking requests'),
          }),
        ),
    [session],
  )

  useEffect(() => {
    void load()
  }, [load, session.token])

  function decided(request: BookingRequest, message: string) {
    setQueue((current) =>
      current.state === 'loaded'
        ? { state: 'loaded', requests: current.requests.filter((r) => r.id !== request.id) }
        : current,
    )
    setRejecting(null)
    setHolding(null)
    setNotice(message)
  }

  function failed(request: BookingRequest, error: unknown, what: string) {
    setRowError({
      bookingId: request.id,
      message:
        error instanceof EventRuleError ? error.message : unexpectedFailureMessage(error, what),
    })
    // A refusal may mean the slot was taken meanwhile: show the queue as it is now.
    if (error instanceof EventRuleError) void load()
  }

  function approve(request: BookingRequest) {
    setBusy(request.id)
    setRowError(null)
    setNotice('')
    approveBookingRequest(request.id, session)
      .then((confirmed) =>
        decided(
          request,
          `Confirmed ${confirmed.venueName} for ${displayEventTitle(confirmed.eventTitle)}. ` +
            'The Coordinator has been notified.',
        ),
      )
      .catch((error: unknown) => failed(request, error, 'approve this booking'))
      .finally(() => setBusy(null))
  }

  function approveAsHold(request: BookingRequest) {
    const until = holding?.until.trim() ?? ''
    if (!until) {
      setRowError({ bookingId: request.id, message: 'Give the hold an expiry date and time.' })
      return
    }
    setBusy(request.id)
    setRowError(null)
    setNotice('')
    approveBookingRequest(request.id, session, until)
      .then((held) =>
        decided(
          request,
          `Approved ${held.venueName} for ${displayEventTitle(held.eventTitle)} as a tentative ` +
            `hold until ${formatTimestamp(held.holdExpiresAt ?? until)}. The Coordinator has been ` +
            'told to confirm it before then.',
        ),
      )
      .catch((error: unknown) => failed(request, error, 'approve this booking as a hold'))
      .finally(() => setBusy(null))
  }

  function reject(request: BookingRequest) {
    const reason = rejecting?.reason.trim() ?? ''
    if (!reason) {
      setRowError({
        bookingId: request.id,
        message: 'Give the Coordinator a reason for rejecting this booking.',
      })
      return
    }
    setBusy(request.id)
    setRowError(null)
    setNotice('')
    rejectBookingRequest(request.id, reason, rejecting?.suggestion.trim() ?? '', session)
      .then((rejected) =>
        decided(
          request,
          `Rejected ${rejected.venueName} for ${displayEventTitle(rejected.eventTitle)}. ` +
            'The slot is free again and the Coordinator has been notified.',
        ),
      )
      .catch((error: unknown) => failed(request, error, 'reject this booking'))
      .finally(() => setBusy(null))
  }

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Booking requests</h1>
            <p className="page-subtitle">
              Venue requests waiting for a decision, oldest first. Only confirmed bookings are
              final.
            </p>
          </div>
        </header>

        {notice && (
          <p className="booking-request-notice" role="status">
            {notice}
          </p>
        )}
        {renderQueue()}
      </div>
    </div>
  )

  function renderQueue() {
    if (queue.state === 'loading') return <p className="muted">Loading booking requests…</p>
    if (queue.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {queue.message}
        </p>
      )
    }
    if (queue.requests.length === 0) {
      return (
        <div className="card empty">
          <h3>No booking requests waiting</h3>
          <p>When a Coordinator requests a venue, it shows up here for a decision.</p>
        </div>
      )
    }
    return (
      <ul className="booking-request-list" aria-label="Booking requests">
        {queue.requests.map((request) => renderRequest(request))}
      </ul>
    )
  }

  function renderRequest(request: BookingRequest) {
    const venueName = request.venueName || 'Unnamed venue'
    const title = displayEventTitle(request.eventTitle)
    const unavailable = request.unavailable ?? []
    const blocked = request.clashes.length > 0 || unavailable.length > 0
    const rejectOpen = rejecting?.bookingId === request.id
    const working = busy === request.id
    return (
      <li key={request.id} className={`card booking-request${blocked ? ' is-blocked' : ''}`}>
        <div className="booking-request-head">
          <h2 className="booking-request-title">{title}</h2>
          {request.coordinatorName && (
            <span className="booking-request-coordinator">
              Coordinator: {request.coordinatorName}
            </span>
          )}
        </div>

        <dl className="booking-request-facts">
          <div>
            <dt>Venue</dt>
            <dd>{venueName}</dd>
          </div>
          <div>
            <dt>Booking</dt>
            <dd>{formatBookingTimes(request.startsAt, request.endsAt)}</dd>
          </div>
          <div>
            <dt>Occupies the venue</dt>
            <dd>
              {formatBookingTimes(request.occupiedFrom, request.occupiedTo)}
              <span className="booking-request-buffers">
                {' '}
                ({minutes(request.setupMinutes)} setup, {minutes(request.turnaroundMinutes)}{' '}
                turnaround)
              </span>
            </dd>
          </div>
          <div>
            <dt>Headcount</dt>
            <dd>{request.headcount ?? 'Not given'}</dd>
          </div>
          <div>
            <dt>Layout</dt>
            <dd>{request.requiredLayout || 'Any'}</dd>
          </div>
        </dl>

        {request.conflict && (
          <p className="booking-request-flag" role="note">
            <span className="booking-request-flag-tag">{CONFLICT_LABEL}</span>
            {request.conflict.reason}
          </p>
        )}

        {blocked && (
          <div className="booking-request-clash" role="note">
            <strong>
              {request.clashes.length > 0
                ? 'Clashes with a booking that already takes this slot.'
                : 'The venue is unavailable for this slot.'}
            </strong>{' '}
            It cannot be approved while this remains:
            <ul>
              {request.clashes.map((clash) => (
                <li key={clash.bookingId}>
                  {displayEventTitle(clash.eventTitle)} ({clash.status}), occupying{' '}
                  {formatBookingTimes(clash.occupiedFrom, clash.occupiedTo)}
                </li>
              ))}
              {unavailable.map((period) => (
                <li key={`unavailable-${period.id}`}>Venue unavailable {describePeriod(period)}</li>
              ))}
            </ul>
          </div>
        )}

        {rowError?.bookingId === request.id && (
          <p className="form-error" role="alert">
            {rowError.message}
          </p>
        )}

        {rejectOpen ? (
          renderRejectForm(request)
        ) : holding?.bookingId === request.id ? (
          renderHoldForm(request, blocked)
        ) : (
          <div className="booking-request-actions">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              aria-label={`Approve ${venueName} for ${title}`}
              onClick={() => approve(request)}
              disabled={busy !== null || blocked}
            >
              {working ? 'Approving…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              aria-label={`Approve ${venueName} for ${title} as a tentative hold`}
              onClick={() => {
                setHolding({ bookingId: request.id, until: '' })
                setRejecting(null)
                setRowError(null)
              }}
              disabled={busy !== null || blocked}
            >
              Approve as hold
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              aria-label={`Reject ${venueName} for ${title}`}
              onClick={() => {
                setRejecting({ bookingId: request.id, reason: '', suggestion: '' })
                setRowError(null)
              }}
              disabled={busy !== null}
            >
              Reject
            </button>
          </div>
        )}
      </li>
    )
  }

  function renderHoldForm(request: BookingRequest, blocked: boolean) {
    const untilId = `hold-until-${request.id}`
    const working = busy === request.id
    return (
      <div className="booking-request-reject">
        <div className="field">
          <label htmlFor={untilId}>Hold until</label>
          <input
            id={untilId}
            type="datetime-local"
            max={request.startsAt.slice(0, 16)}
            value={holding?.until ?? ''}
            disabled={working}
            onChange={(changeEvent) =>
              setHolding((current) =>
                current ? { ...current, until: changeEvent.target.value } : current,
              )
            }
          />
        </div>
        <div className="booking-request-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => approveAsHold(request)}
            disabled={working || blocked}
          >
            {working ? 'Approving…' : 'Approve as tentative hold'}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setHolding(null)
              setRowError(null)
            }}
            disabled={working}
          >
            Back
          </button>
        </div>
      </div>
    )
  }

  function renderRejectForm(request: BookingRequest) {
    const reasonId = `reject-reason-${request.id}`
    const suggestionId = `reject-suggestion-${request.id}`
    const working = busy === request.id
    const update = (field: 'reason' | 'suggestion', value: string) =>
      setRejecting((current) => (current ? { ...current, [field]: value } : current))
    return (
      <div className="booking-request-reject">
        <div className="field">
          <label htmlFor={reasonId}>Why can't this booking be supported?</label>
          <textarea
            id={reasonId}
            rows={3}
            maxLength={DECISION_TEXT_MAX}
            value={rejecting?.reason ?? ''}
            disabled={working}
            onChange={(changeEvent) => update('reason', changeEvent.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={suggestionId}>Suggest another venue or time (optional)</label>
          <input
            id={suggestionId}
            type="text"
            maxLength={DECISION_TEXT_MAX}
            value={rejecting?.suggestion ?? ''}
            disabled={working}
            onChange={(changeEvent) => update('suggestion', changeEvent.target.value)}
          />
        </div>
        <div className="booking-request-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => reject(request)}
            disabled={working}
          >
            {working ? 'Rejecting…' : 'Reject booking'}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setRejecting(null)
              setRowError(null)
            }}
            disabled={working}
          >
            Keep it
          </button>
        </div>
      </div>
    )
  }
}
