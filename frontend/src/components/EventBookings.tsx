import { useEffect, useState, type FormEvent } from 'react'
import './EventBookings.css'
import {
  CANCELLATION_REASON_MAX,
  EventRuleError,
  attendanceField,
  cancelBooking,
  checkSuitability,
  formatBookingTimes,
  listBookings,
  requestBooking,
  requestHeldBooking,
  validateBooking,
  type BookingInput,
  type BookingRecord,
  type EventRecord,
  type Suitability,
} from '../eventsStore'
import { listVenues, listedItems, type VenueRecord } from '../venuesStore'
import { bookingRefusalMessage, checkBooking, formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'

type EventBookingsProps = {
  event: EventRecord
  session: Session
  onBookingRequested?: () => void
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

/** US18.1: the verdict for one exact set of form values. */
type Check = { key: string } & (
  | { state: 'done'; result: Suitability }
  | { state: 'error'; message: string }
)

/**
 * How long the form waits after the last change before checking. Long enough
 * that typing a headcount of 120 is one check rather than three.
 */
const CHECK_DELAY_MS = 300

/** Every layout the catalogue lists, once each, for the layout box to suggest. */
function layoutSuggestions(venues: VenueRecord[]): string[] {
  const byKey = new Map<string, string>()
  for (const venue of venues) {
    for (const layout of listedItems(venue.supportedLayouts)) {
      const key = layout.toLowerCase()
      if (!byKey.has(key)) byKey.set(key, layout)
    }
  }
  return [...byKey.values()].sort((a, b) => a.localeCompare(b))
}

/** "For 120 people · Theatre layout · Needs projector · Access: hearing loop". */
function describeNeeds(booking: BookingRecord): string {
  const parts: string[] = []
  if (booking.headcount !== null) parts.push(`For ${booking.headcount} people`)
  if (booking.requiredLayout) parts.push(`${booking.requiredLayout} layout`)
  if (booking.requiredFacilities.length) {
    parts.push(`Needs ${booking.requiredFacilities.join(', ')}`)
  }
  if (booking.accessibilityNeeds.length) {
    parts.push(`Access: ${booking.accessibilityNeeds.join(', ')}`)
  }
  return parts.join(' · ')
}

/**
 * The venue bookings for an event — US14.1 and US14.2.
 *
 * Every booking shows here together, for the Organiser who owns the event and
 * the Coordinator assigned to it. The Coordinator also gets the form that
 * requests one, and uses it once per venue: a main hall and two breakout rooms
 * are three requests, and a refused one leaves the others where they are.
 *
 * Picking a venue shows whether it suits the booking (US18.1): Suitable, or
 * Not suitable with every reason, from the server's own check. The booking
 * carries its own headcount, starting from the event's attendance, so a
 * breakout room is judged on the people in it. A venue that is not suitable
 * cannot be requested; the button says so and the server refuses it anyway.
 *
 * The Coordinator can cancel any one Requested booking with a reason (US14.2).
 * The cancelled booking stays in the list with who, when and why, and nothing
 * else on the card or the event changes. Cancelling is offered whatever the
 * event's status, because giving back the hall for an event that will not run
 * is the point of it.
 *
 * US16.1: Venue Staff confirm or reject each request. A decision shows who
 * made it and when; a rejection shows the reason and any suggested
 * alternative. Only a Requested or still-active Held booking can be cancelled.
 *
 * US14.3: Venue Staff may hold a venue for the Coordinator. A hold shows as
 * Held with its expiry, never as Confirmed, and the Coordinator can request it
 * until it expires; after that it is marked expired and no longer keeps the
 * slot. A hold can be released with the same Cancel as a request.
 *
 * Its own card and its own request, as US12.1's blackout card is, so a failure
 * to load the bookings says so here and leaves the event above it readable.
 */
export default function EventBookings({ event, session, onBookingRequested }: EventBookingsProps) {
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
    headcount: attendanceField(event.expectedAttendance),
    layout: '',
    facilities: '',
    accessibilityNeeds: '',
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
  // US14.3: the hold being requested, and a refusal shown under its row.
  const [holdBusy, setHoldBusy] = useState<string | null>(null)
  const [holdError, setHoldError] = useState<{ bookingId: string; message: string } | null>(
    null,
  )
  const [notice, setNotice] = useState('')
  const [check, setCheck] = useState<Check | null>(null)

  // US18.1: check once a venue is picked and the form would pass, keyed on the
  // exact values so a verdict is never shown for inputs it was not given.
  const checkKey =
    showForm && fields.venueId && !validateBooking(fields) ? JSON.stringify(fields) : ''
  const verdict = check !== null && check.key === checkKey ? check : null
  const notSuitable = verdict?.state === 'done' && !verdict.result.suitable

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

  useEffect(() => {
    if (!checkKey) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      checkSuitability(event.id, JSON.parse(checkKey) as BookingInput, session)
        .then((result) => {
          if (!cancelled) setCheck({ key: checkKey, state: 'done', result })
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setCheck({
              key: checkKey,
              state: 'error',
              message:
                error instanceof EventRuleError
                  ? error.message
                  : unexpectedFailureMessage(error, 'check this venue'),
            })
          }
        })
    }, CHECK_DELAY_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [checkKey, event.id, session])

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
        onBookingRequested?.()
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

  /** Swap one booking in place in the list, keeping the server's order. */
  function replaceBooking(updated: BookingRecord) {
    setBookings((current) =>
      current.state === 'loaded'
        ? {
            state: 'loaded',
            bookings: current.bookings.map((item) => (item.id === updated.id ? updated : item)),
          }
        : current,
    )
  }

  /** US14.3: turn a hold into a request. The event may move to Planning. */
  function requestHold(booking: BookingRecord) {
    setHoldBusy(booking.id)
    setHoldError(null)
    setNotice('')
    requestHeldBooking(event.id, booking.id, session)
      .then((requested) => {
        replaceBooking(requested)
        setNotice(`Requested ${requested.venueName}. It now waits for Venue Staff to approve it.`)
        onBookingRequested?.()
      })
      .catch((error: unknown) => {
        setHoldError({
          bookingId: booking.id,
          message:
            error instanceof EventRuleError
              ? error.message
              : unexpectedFailureMessage(error, 'request this venue'),
        })
      })
      .finally(() => setHoldBusy(null))
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
        replaceBooking(cancelled)
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
    const isHeld = booking.status === 'Held'
    const holdExpired = isHeld && booking.holdExpired === true
    const venueName = booking.venueName || 'Unnamed venue'
    const cancelOpen = cancelling?.bookingId === booking.id
    const isRejected = booking.status === 'Rejected'
    const cancellable = booking.status === 'Requested' || (isHeld && !holdExpired)
    const rowClass =
      isCancelled || isRejected ? ' is-cancelled' : holdExpired ? ' is-expired' : ''
    return (
      <li key={booking.id} className={`booking-row${rowClass}`}>
        <div className="booking-summary">
          <span className="booking-venue">{venueName}</span>
          <span className="booking-times">
            {formatBookingTimes(booking.startsAt, booking.endsAt)}
          </span>
          <span
            className={`booking-status is-${booking.status.toLowerCase()}${
              holdExpired ? ' is-expired' : ''
            }`}
          >
            {holdExpired ? 'Hold expired' : booking.status}
          </span>
          {mayRequest && isHeld && !holdExpired && bookingCheck.allowed && !cancelOpen && (
            <button
              type="button"
              className="btn btn-primary btn-sm booking-request-hold"
              aria-label={`Request the held ${venueName}`}
              onClick={() => requestHold(booking)}
              disabled={holdBusy !== null || cancelBusy}
            >
              {holdBusy === booking.id ? 'Requesting…' : 'Request this venue'}
            </button>
          )}
          {mayRequest && cancellable && !cancelOpen && (
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
        {booking.holdExpiresAt && (isHeld || booking.status === 'Requested') && (
          <p className={`booking-hold${holdExpired ? ' is-expired' : ''}`}>
            {!isHeld
              ? `Requested from a hold${booking.heldByName ? ` by ${booking.heldByName}` : ''}.`
              : holdExpired
                ? `Hold expired ${formatTimestamp(booking.holdExpiresAt)}. The venue is no longer kept for this event.`
                : `Held${booking.heldByName ? ` by ${booking.heldByName}` : ''} until ${formatTimestamp(
                    booking.holdExpiresAt,
                  )}. Request it before then to keep the slot.`}
          </p>
        )}
        {booking.decision && booking.status === 'Confirmed' && (
          <p className="booking-decision">
            Confirmed by {booking.decision.byName || 'a former user'},{' '}
            {formatTimestamp(booking.decision.at)}.
          </p>
        )}
        {booking.decision && isRejected && (
          <p className="booking-decision is-rejected">
            Rejected by {booking.decision.byName || 'a former user'},{' '}
            {formatTimestamp(booking.decision.at)}: {booking.decision.reason}
            {booking.decision.suggestion && (
              <span className="booking-suggestion">
                {' '}
                Suggested instead: {booking.decision.suggestion}
              </span>
            )}
          </p>
        )}
        {holdError?.bookingId === booking.id && (
          <p className="form-error" role="alert">
            {holdError.message}
          </p>
        )}
        {describeNeeds(booking) && <p className="booking-needs">{describeNeeds(booking)}</p>}
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

          <div className="field">
            <label htmlFor="booking-headcount">Headcount</label>
            <input
              id="booking-headcount"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              value={fields.headcount}
              onChange={(changeEvent) => set('headcount', changeEvent.target.value)}
            />
            <span className="field-hint">People in this space. Starts at the event's total.</span>
          </div>

          <div className="field">
            <label htmlFor="booking-layout">Layout (optional)</label>
            <input
              id="booking-layout"
              list="booking-layouts"
              maxLength={100}
              placeholder="Theatre, classroom…"
              value={fields.layout}
              onChange={(changeEvent) => set('layout', changeEvent.target.value)}
            />
            <datalist id="booking-layouts">
              {venuesReady &&
                layoutSuggestions(venues.venues).map((layout) => (
                  <option key={layout} value={layout} />
                ))}
            </datalist>
          </div>

          <div className="field">
            <label htmlFor="booking-facilities">Facilities needed (optional)</label>
            <input
              id="booking-facilities"
              placeholder="projector, PA system"
              value={fields.facilities}
              onChange={(changeEvent) => set('facilities', changeEvent.target.value)}
            />
            <span className="field-hint">Separate with commas.</span>
          </div>

          <div className="field booking-access-field">
            <label htmlFor="booking-access">Accessibility needs (optional)</label>
            <input
              id="booking-access"
              placeholder="wheelchair access, hearing loop"
              value={fields.accessibilityNeeds}
              onChange={(changeEvent) => set('accessibilityNeeds', changeEvent.target.value)}
            />
            <span className="field-hint">Separate with commas.</span>
          </div>
        </fieldset>

        {renderVerdict()}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={busy || !venuesReady || notSuitable}
          title={notSuitable ? 'This venue is not suitable for this booking.' : undefined}
        >
          {busy ? 'Requesting…' : 'Request venue'}
        </button>
      </form>
    )
  }

  /** US18.1: Suitable or Not suitable, with the reasons, for the venue picked. */
  function renderVerdict() {
    if (!checkKey) return null
    if (verdict === null) {
      return (
        <p className="booking-verdict is-checking" role="status">
          Checking whether this venue suits the booking…
        </p>
      )
    }
    if (verdict.state === 'error') {
      return (
        <p className="booking-verdict is-error" role="status">
          {verdict.message}
        </p>
      )
    }
    const { suitable, reasons, notes } = verdict.result
    return (
      <div
        className={`booking-verdict ${suitable ? 'is-suitable' : 'is-unsuitable'}`}
        role="status"
      >
        <p className="booking-verdict-title">{suitable ? 'Suitable' : 'Not suitable'}</p>
        {reasons.length > 0 && (
          <ul className="booking-verdict-reasons">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        {notes.map((note) => (
          <p key={note} className="booking-verdict-note">
            {note}
          </p>
        ))}
      </div>
    )
  }
}
