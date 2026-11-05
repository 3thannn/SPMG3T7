import { useEffect, useState, type FormEvent } from 'react'
import './VenueHolds.css'
import {
  listHolds,
  nowLocal,
  releaseHold,
  updateHold,
  validateExpiry,
  type HoldRecord,
} from '../holdsStore'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

type VenueHoldsProps = {
  venueId: string
  session: Session
  /** A datetime-local value. Injected by tests; the viewer's own clock otherwise. */
  now?: string
}

type Loaded =
  | { state: 'loading' }
  | { state: 'loaded'; items: HoldRecord[] }
  | { state: 'error'; message: string }

/** What a row's open form is doing: changing the expiry, or releasing the hold. */
type Editing = { holdId: string; mode: 'expiry' | 'release'; value: string }

/**
 * A venue's tentative holds — US14.3 and US14.6, for Venue Staff.
 *
 * A hold starts when Venue Staff approve a booking request as one (Booking
 * requests page), and keeps this venue's slot until it expires or the
 * Coordinator confirms it. Here Venue Staff change a live hold's expiry or
 * release it with a reason; the Coordinator is told either way. Its own card
 * and its own requests, like US12.1's, so a failure here leaves the venue
 * details readable. An expired hold stays listed, marked expired, because it
 * no longer keeps the slot but is still the record of what was offered.
 */
export default function VenueHolds({ venueId, session, now }: VenueHoldsProps) {
  const [holds, setHolds] = useState<Loaded>({ state: 'loading' })
  const [editing, setEditing] = useState<Editing | null>(null)
  const [formError, setFormError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    listHolds(venueId, session)
      .then((items) => {
        if (!cancelled) setHolds({ state: 'loaded', items })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHolds({ state: 'error', message: unexpectedFailureMessage(error, 'load the holds') })
        }
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token])

  function open(hold: HoldRecord, mode: Editing['mode']) {
    setEditing({
      holdId: hold.id,
      mode,
      value: mode === 'expiry' ? (hold.holdExpiresAt ?? '').slice(0, 16) : '',
    })
    setFormError('')
    setSaved('')
  }

  function swap(updated: HoldRecord) {
    setHolds((current) =>
      current.state === 'loaded'
        ? {
            state: 'loaded',
            items: current.items
              .map((item) => (item.id === updated.id ? updated : item))
              // A released hold is Cancelled: no longer a hold on this venue.
              .filter((item) => item.status === 'Held' || item.status === 'Expired'),
          }
        : current,
    )
  }

  function submit(submitEvent: FormEvent, hold: HoldRecord) {
    submitEvent.preventDefault()
    if (editing === null) return
    const value = editing.value.trim()
    const problem =
      editing.mode === 'expiry'
        ? validateExpiry(value, hold.startsAt, now ?? nowLocal())
        : value
          ? ''
          : 'Give the Coordinator a reason for releasing this hold.'
    if (problem) {
      setFormError(problem)
      return
    }
    setBusy(true)
    setFormError('')
    const action =
      editing.mode === 'expiry'
        ? updateHold(hold.id, value, session)
        : releaseHold(hold.id, value, session)
    action
      .then((updated) => {
        swap(updated)
        setEditing(null)
        setSaved(
          editing.mode === 'expiry'
            ? `The hold for ${displayEventTitle(updated.eventTitle)} now expires ` +
                `${formatTimestamp(updated.holdExpiresAt ?? '')}. Its Coordinator has been told.`
            : `Released the hold for ${displayEventTitle(updated.eventTitle)}. ` +
                'Its Coordinator has been told why.',
        )
      })
      .catch((error: unknown) => {
        setFormError(
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(
                error,
                editing.mode === 'expiry' ? 'change this hold' : 'release this hold',
              ),
        )
      })
      .finally(() => setBusy(false))
  }

  return (
    <section className="card venue-holds" aria-labelledby="venue-holds-title">
      <h2 className="venue-section-title" id="venue-holds-title">
        Tentative holds
      </h2>
      <p className="venue-holds-lede">
        A hold starts when you approve a booking request as one, and keeps the slot until the
        Coordinator confirms it or it expires. It is not a confirmed booking.
      </p>
      {saved && (
        <p className="hold-saved" role="status">
          {saved}
        </p>
      )}
      {renderHolds()}
    </section>
  )

  function renderHolds() {
    if (holds.state === 'loading') return <p className="muted">Loading holds…</p>
    if (holds.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {holds.message}
        </p>
      )
    }
    if (holds.items.length === 0) {
      return <p className="muted hold-none">No holds on this venue.</p>
    }
    return (
      <ul className="hold-list" aria-label="Holds on this venue">
        {holds.items.map((hold) => (
          <li key={hold.id} className={`hold-row${hold.holdExpired ? ' is-expired' : ''}`}>
            <span className="hold-event">{displayEventTitle(hold.eventTitle)}</span>
            <span className="hold-times">{formatBookingTimes(hold.startsAt, hold.endsAt)}</span>
            <span className={`hold-tag${hold.holdExpired ? ' is-expired' : ''}`}>
              {hold.holdExpired ? 'Expired' : 'Held'}
            </span>
            <span className="hold-expiry">
              {hold.holdExpired ? 'Expired' : 'Until'} {formatTimestamp(hold.holdExpiresAt ?? '')}
              {hold.heldByName && ` · approved by ${hold.heldByName}`}
            </span>
            {!hold.holdExpired && editing?.holdId !== hold.id && (
              <span className="hold-actions">
                <button
                  type="button"
                  className="btn btn-sm"
                  aria-label={`Change the expiry of the hold for ${displayEventTitle(hold.eventTitle)}`}
                  onClick={() => open(hold, 'expiry')}
                >
                  Change expiry
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  aria-label={`Release the hold for ${displayEventTitle(hold.eventTitle)}`}
                  onClick={() => open(hold, 'release')}
                >
                  Release
                </button>
              </span>
            )}
            {editing?.holdId === hold.id && renderForm(hold, editing)}
          </li>
        ))}
      </ul>
    )
  }

  function renderForm(hold: HoldRecord, current: Editing) {
    const isExpiry = current.mode === 'expiry'
    const inputId = `hold-${current.mode}-${hold.id}`
    return (
      <form className="hold-form" onSubmit={(submitEvent) => submit(submitEvent, hold)} noValidate>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <fieldset className="hold-fields" disabled={busy}>
          <div className="field">
            <label htmlFor={inputId}>{isExpiry ? 'New expiry' : 'Reason for releasing'}</label>
            <input
              id={inputId}
              type={isExpiry ? 'datetime-local' : 'text'}
              min={isExpiry ? (now ?? nowLocal()) : undefined}
              max={isExpiry ? hold.startsAt.slice(0, 16) : undefined}
              value={current.value}
              onChange={(changeEvent) => {
                setEditing({ ...current, value: changeEvent.target.value })
                setFormError('')
              }}
            />
          </div>
        </fieldset>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
          {busy ? 'Saving…' : isExpiry ? 'Save expiry' : 'Release hold'}
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={busy}
          onClick={() => {
            setEditing(null)
            setFormError('')
          }}
        >
          Keep as is
        </button>
      </form>
    )
  }
}
