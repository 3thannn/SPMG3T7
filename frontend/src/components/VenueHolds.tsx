import { useEffect, useState, type FormEvent } from 'react'
import './VenueHolds.css'
import {
  EMPTY_HOLD,
  listHoldableEvents,
  listHolds,
  nowLocal,
  placeHold,
  validateHold,
  type HoldableEvent,
  type HoldInput,
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

type Loaded<T> =
  | { state: 'loading' }
  | { state: 'loaded'; items: T[] }
  | { state: 'error'; message: string }

function bySchedule(a: HoldRecord, b: HoldRecord): number {
  return a.startsAt.localeCompare(b.startsAt) || a.endsAt.localeCompare(b.endsAt)
}

/** A datetime-local value from a stored time, which may carry seconds. */
function asInputValue(iso: string): string {
  return iso.slice(0, 16)
}

/**
 * A venue's tentative holds — US14.3, for Venue Staff.
 *
 * A hold keeps this venue's slot for an event's Coordinator until it expires;
 * the Coordinator turns it into a request from the event page. Its own card
 * and its own requests, like US12.1's, so a failure here leaves the venue
 * details readable. An expired hold stays listed, marked expired, because it
 * no longer keeps the slot but is still the record of what was offered.
 */
export default function VenueHolds({ venueId, session, now }: VenueHoldsProps) {
  const [holds, setHolds] = useState<Loaded<HoldRecord>>({ state: 'loading' })
  const [events, setEvents] = useState<Loaded<HoldableEvent>>({ state: 'loading' })
  const [fields, setFields] = useState<HoldInput>(EMPTY_HOLD)
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
    listHoldableEvents(session)
      .then((items) => {
        if (!cancelled) setEvents({ state: 'loaded', items })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setEvents({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the events you can hold for'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token])

  function set<K extends keyof HoldInput>(field: K, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
    setSaved('')
    setFormError('')
  }

  /** Picking an event starts the times at the event's own, the likeliest slot. */
  function chooseEvent(eventId: string) {
    const chosen = events.state === 'loaded' ? events.items.find((e) => e.id === eventId) : null
    setFields((current) => ({
      ...current,
      eventId,
      startsAt: chosen ? asInputValue(chosen.startsAt) : current.startsAt,
      endsAt: chosen ? asInputValue(chosen.endsAt) : current.endsAt,
    }))
    setSaved('')
    setFormError('')
  }

  function submit(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    const problem = validateHold(fields, now ?? nowLocal())
    if (problem) {
      setFormError(problem)
      return
    }
    setBusy(true)
    setFormError('')
    placeHold(venueId, fields, session)
      .then((created) => {
        setHolds((current) =>
          current.state === 'loaded'
            ? { state: 'loaded', items: [...current.items, created].sort(bySchedule) }
            : current,
        )
        setFields(EMPTY_HOLD)
        setSaved(
          `Held for ${displayEventTitle(created.eventTitle)} until ` +
            `${formatTimestamp(created.holdExpiresAt ?? '')}. Its Coordinator can now request it.`,
        )
      })
      .catch((error: unknown) => {
        setFormError(
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'place this hold'),
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
        A hold keeps a slot for an event's Coordinator until it expires. It is not a confirmed
        booking.
      </p>
      {renderHolds()}
      {renderForm()}
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
              {hold.heldByName && ` · by ${hold.heldByName}`}
            </span>
          </li>
        ))}
      </ul>
    )
  }

  function renderForm() {
    const noEvents = events.state === 'loaded' && events.items.length === 0
    return (
      <form className="hold-form" onSubmit={submit} noValidate>
        <h3 className="hold-form-title">Place a hold</h3>
        {events.state === 'error' && (
          <p className="form-error" role="alert">
            {events.message}
          </p>
        )}
        {noEvents && (
          <p className="muted">
            No events can take a hold right now. An event needs a Coordinator and to be Approved
            or in Planning.
          </p>
        )}
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        {saved && (
          <p className="hold-saved" role="status">
            {saved}
          </p>
        )}

        <fieldset className="hold-fields" disabled={busy || events.state !== 'loaded' || noEvents}>
          <div className="field hold-event-field">
            <label htmlFor="hold-event">Event</label>
            <select
              id="hold-event"
              value={fields.eventId}
              onChange={(changeEvent) => chooseEvent(changeEvent.target.value)}
            >
              <option value="">Choose an event…</option>
              {events.state === 'loaded' &&
                events.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {displayEventTitle(item.title)}
                    {item.coordinatorName ? ` — ${item.coordinatorName}` : ''}
                  </option>
                ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="hold-start">Starts</label>
            <input
              id="hold-start"
              type="datetime-local"
              value={fields.startsAt}
              onChange={(changeEvent) => set('startsAt', changeEvent.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="hold-end">Ends</label>
            <input
              id="hold-end"
              type="datetime-local"
              min={fields.startsAt || undefined}
              value={fields.endsAt}
              onChange={(changeEvent) => set('endsAt', changeEvent.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="hold-expiry">Hold expires</label>
            <input
              id="hold-expiry"
              type="datetime-local"
              min={now ?? nowLocal()}
              max={fields.startsAt || undefined}
              value={fields.expiresAt}
              onChange={(changeEvent) => set('expiresAt', changeEvent.target.value)}
            />
          </div>
        </fieldset>

        <button type="submit" className="btn btn-primary" disabled={busy || noEvents}>
          {busy ? 'Placing…' : 'Place hold'}
        </button>
      </form>
    )
  }
}
