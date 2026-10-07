import { useEffect, useState, type FormEvent } from 'react'
import './EventBookings.css'
import {
  CANCELLATION_REASON_MAX,
  EventRuleError,
  cancelBooking,
  formatBookingTimes,
  listBookings,
  requestBooking,
  validateBooking,
  type BookingInput,
  type BookingRecord,
  type EventRecord,
} from '../eventsStore'
import { listVenues, type VenueRecord } from '../venuesStore'
import { bookingRefusalMessage, checkBooking, formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'

type EventBookingsProps = {
  event: EventRecord
  session: Session
}

type Bookings =
  | { state: 'loading' }
  | { state: 'loaded'; bookings: BookingRecord[] }
  | { state: 'error'; message: string }

type Venues =
  | { state: 'loading' }
  | { state: 'loaded'; venues: VenueRecord[] }
  | { state: 'error'; message: string }

/** Soonest first, then the earlier end — the server's order, kept when one is added. */
function bySchedule(a: BookingRecord, b: BookingRecord): number {
  return a.startsAt.localeCompare(b.startsAt) || a.endsAt.localeCompare(b.endsAt)
}

/** A datetime-local value from a stored time, which may carry seconds. */
function asInputValue(iso: string | undefined): string {
  return (iso ?? '').slice(0, 16)
}

/**
 * The venue bookings for an event — US14.1 and US14.2.
 *
 * Every booking shows here together, for the Organiser who owns the event and
 * the Coordinator assigned to it. The Coordinator also gets the form that
 * requests one, and uses it once per venue: a main hall and two breakout rooms
 * are three requests, and a refused one leaves the others where they are.
 *
 * The Coordinator can cancel any one Requested booking with a reason (US14.2).
 * The cancelled booking stays in the list with who, when and why, and nothing
 * else on the card or the event changes. Cancelling is offered whatever the
 * event's status, because giving back the hall for an event that will not run
 * is the point of it.
 *
 * Its own card and its own request, as US12.1's blackout card is, so a failure
 * to load the bookings says so here and leaves the event above it readable.
 */
export default function EventBookings({ event, session }: EventBookingsProps) {
  const mayRequest = can(session, 'bookings:request')
  const bookingCheck = checkBooking(event)
  const showForm = mayRequest && bookingCheck.allowed

  const [bookings, setBookings] = useState<Bookings>({ state: 'loading' })
  const [venues, setVenues] = useState<Venues>({ state: 'loading' })
  // The event's own times are the likeliest booking, so the form starts there.
  const [fields, setFields] = useState<BookingInput>({
    venueId: '',
    startsAt: asInputValue(event.startsAt),
    endsAt: asInputValue(event.endsAt),
  })
  const [formError, setFormError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)
  // US14.2: the one booking whose cancel box is open, and what has been typed.
  const [cancelling, setCancelling] = useState<{ bookingId: string; reason: string } | null>(
    null,
  )
  const [cancelError, setCancelError] = useState('')
  const [cancelBusy, setCancelBusy] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let cancelled = false
    listBookings(event.id, session)
      .then((loaded) => {
        if (!cancelled) setBookings({ state: 'loaded', bookings: loaded })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setBookings({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the venue bookings'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  useEffect(() => {
    if (!showForm) return
    let cancelled = false
    listVenues(session)
      .then((loaded) => {
        if (!cancelled) setVenues({ state: 'loaded', venues: loaded })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setVenues({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the venue catalogue'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [showForm, session])

  function set<K extends keyof BookingInput>(field: K, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
    setFormError('')
    setSaved('')
  }

  function submit(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    const problem = validateBooking(fields)
    if (problem) {
      setFormError(problem)
      return
    }

    setBusy(true)
    setFormError('')
    setSaved('')
    setNotice('')
    requestBooking(event.id, fields, session)
      .then((created) => {
        setBookings((current) =>
          current.state === 'loaded'
            ? { state: 'loaded', bookings: [...current.bookings, created].sort(bySchedule) }
            : current,
        )
        // The times stay: the next venue for the same event is usually wanted
        // for the same hours, and only the venue changes between requests.
        setFields((current) => ({ ...current, venueId: '' }))
        setSaved(
          `Requested ${created.venueName}. It is waiting for Venue Staff to approve it.`,
        )
      })
      .catch((error: unknown) => {
        setFormError(
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'request this venue'),
        )
      })
      .finally(() => setBusy(false))
  }

  function openCancel(bookingId: string) {
    setCancelling({ bookingId, reason: '' })
    setCancelError('')
    setNotice('')
  }

  function closeCancel() {
    setCancelling(null)
    setCancelError('')
  }

  /** US14.2: cancel this one booking, then swap it in place in the list. */
  function confirmCancel(booking: BookingRecord) {
    const reason = cancelling?.reason.trim() ?? ''
    if (!reason) {
      setCancelError('Give a reason for cancelling this booking.')
      return
    }
    setCancelBusy(true)
    setCancelError('')
    cancelBooking(event.id, booking.id, reason, session)
      .then((cancelled) => {
        setBookings((current) =>
          current.state === 'loaded'
            ? {
                state: 'loaded',
                bookings: current.bookings.map((item) =>
                  item.id === cancelled.id ? cancelled : item,
                ),
              }
            : current,
        )
        setCancelling(null)
        setNotice(
          `Cancelled ${cancelled.venueName}. The event and its other bookings are unchanged.`,
        )
      })
      .catch((error: unknown) => {
        // The box stays open with what was typed, so a retry is one click.
        setCancelError(
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'cancel this booking'),
        )
      })
      .finally(() => setCancelBusy(false))
  }

  return (
    <section className="card card-pad event-bookings" aria-labelledby="event-bookings-title">
      <h2 className="detail-section-title" id="event-bookings-title">
        Venue bookings
      </h2>
      <p className="event-bookings-lede">
        Each venue is requested on its own and waits for Venue Staff to approve it.
      </p>
      {renderBookings()}
      {mayRequest && !bookingCheck.allowed && (
        <p className="detail-note">{bookingRefusalMessage(bookingCheck.reason)}</p>
      )}
      {showForm && renderForm()}
    </section>
  )

  function renderBookings() {
    if (bookings.state === 'loading') {
      return <p className="muted">Loading venue bookings…</p>
    }
    if (bookings.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {bookings.message}
        </p>
      )
    }
    if (bookings.bookings.length === 0) {
      return <p className="muted booking-none">No venues have been requested for this event yet.</p>
    }
    return (
      <>
        {notice && (
          <p className="booking-saved booking-notice" role="status">
            {notice}
          </p>
        )}
        <ul className="booking-list" aria-label="Venue bookings for this event">
          {bookings.bookings.map((booking) => renderBooking(booking))}
        </ul>
      </>
    )
  }

  function renderBooking(booking: BookingRecord) {
    const isCancelled = booking.status === 'Cancelled'
    const venueName = booking.venueName || 'Unnamed venue'
    const cancelOpen = cancelling?.bookingId === booking.id
    return (
      <li key={booking.id} className={`booking-row${isCancelled ? ' is-cancelled' : ''}`}>
        <div className="booking-summary">
          <span className="booking-venue">{venueName}</span>
          <span className="booking-times">
            {formatBookingTimes(booking.startsAt, booking.endsAt)}
          </span>
          <span className={`booking-status is-${booking.status.toLowerCase()}`}>
            {booking.status}
          </span>
          {mayRequest && !isCancelled && !cancelOpen && (
            <button
              type="button"
              className="btn btn-secondary btn-sm booking-cancel"
              aria-label={`Cancel the ${venueName} booking`}
              onClick={() => openCancel(booking.id)}
              disabled={cancelBusy}
            >
              Cancel
            </button>
          )}
        </div>
        {booking.cancellation && (
          <p className="booking-cancellation">
            Cancelled by {booking.cancellation.byName || 'a former user'},{' '}
            {formatTimestamp(booking.cancellation.at)}: {booking.cancellation.reason}
          </p>
        )}
        {cancelOpen && renderCancelForm(booking)}
      </li>
    )
  }

  function renderCancelForm(booking: BookingRecord) {
    const reasonId = `booking-cancel-reason-${booking.id}`
    const reason = cancelling?.reason ?? ''
    return (
      <div className="booking-cancel-form">
        <div className="field">
          <label htmlFor={reasonId}>Why are you cancelling this booking?</label>
          <textarea
            id={reasonId}
            rows={3}
            maxLength={CANCELLATION_REASON_MAX}
            value={reason}
            disabled={cancelBusy}
            onChange={(changeEvent) => {
              setCancelling({ bookingId: booking.id, reason: changeEvent.target.value })
              setCancelError('')
            }}
          />
          <span className="field-hint">
            Only this booking is cancelled. The event and its other bookings stay as they are.
          </span>
        </div>
        {cancelError && (
          <p className="form-error" role="alert">
            {cancelError}
          </p>
        )}
        <div className="booking-cancel-actions">
          <button
            type="button"
            className="btn btn-danger-solid btn-sm"
            disabled={cancelBusy || !reason.trim()}
            onClick={() => confirmCancel(booking)}
          >
            {cancelBusy ? 'Cancelling…' : 'Cancel booking'}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={cancelBusy}
            onClick={closeCancel}
          >
            Keep booking
          </button>
        </div>
      </div>
    )
  }

  function renderForm() {
    const venuesReady = venues.state === 'loaded'
    return (
      <form className="booking-form" onSubmit={submit} noValidate>
        <h3 className="booking-form-title">Request a venue</h3>
        <p className="booking-form-hint">
          For several spaces at once, such as a main hall and breakout rooms, request each one
          in turn.
        </p>

        {venues.state === 'error' && (
          <p className="form-error" role="alert">
            {venues.message}
          </p>
        )}
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        {saved && (
          <p className="booking-saved" role="status">
            {saved}
          </p>
        )}

        <fieldset className="booking-fields" disabled={busy || !venuesReady}>
          <div className="field booking-venue-field">
            <label htmlFor="booking-venue">Venue</label>
            <select
              id="booking-venue"
              value={fields.venueId}
              onChange={(changeEvent) => set('venueId', changeEvent.target.value)}
            >
              <option value="">
                {venues.state === 'loading' ? 'Loading venues…' : 'Choose a venue'}
              </option>
              {venuesReady &&
                venues.venues.map((venue) => (
                  <option key={venue.id} value={venue.id}>
                    {venue.name} — holds {venue.capacity}
                  </option>
                ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="booking-start">Starts</label>
            <input
              id="booking-start"
              type="datetime-local"
              value={fields.startsAt}
              onChange={(changeEvent) => set('startsAt', changeEvent.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="booking-end">Ends</label>
            <input
              id="booking-end"
              type="datetime-local"
              min={fields.startsAt || undefined}
              value={fields.endsAt}
              onChange={(changeEvent) => set('endsAt', changeEvent.target.value)}
            />
          </div>
        </fieldset>

        <button type="submit" className="btn btn-primary" disabled={busy || !venuesReady}>
          {busy ? 'Requesting…' : 'Request venue'}
        </button>
      </form>
    )
  }
}
