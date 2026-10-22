import { useCallback, useEffect, useState } from 'react'
import './BookingRequestsPage.css'
import './BookingConflictsPage.css'
import { listBookingConflicts, type FlaggedBooking } from '../bookingConflictsStore'
import { describePeriod } from '../bookingRequestsStore'
import { CONFLICT_LABEL, formatBookingTimes } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { formatTimestamp } from '../status'
import { navigate } from '../router'
import { unexpectedFailureMessage, type Session } from '../api'

type BookingConflictsPageProps = {
  session: Session
}

type Flagged =
  | { state: 'loading' }
  | { state: 'loaded'; bookings: FlaggedBooking[] }
  | { state: 'error'; message: string }

function minutes(value: number): string {
  return value === 1 ? '1 minute' : `${value} minutes`
}

/**
 * Venue Staff review bookings flagged "Conflict – review needed" — US15.2.
 *
 * A venue's setup or turnaround time changed and these bookings now clash,
 * with another booking or with a period the venue is unavailable. Nothing was
 * cancelled: each keeps its status, and its Coordinator has been notified.
 * Every card shows the booking, its full occupied window under the venue's
 * current times, why it was flagged and what it clashes with now. A clash is
 * resolved by rejecting a request (Booking Requests), or by the Coordinator
 * cancelling or replacing a booking; the flag then clears on its own, which is
 * why the list is read fresh each time.
 */
export default function BookingConflictsPage({ session }: BookingConflictsPageProps) {
  const [flagged, setFlagged] = useState<Flagged>({ state: 'loading' })

  const load = useCallback(
    () =>
      listBookingConflicts(session)
        .then((bookings) => setFlagged({ state: 'loaded', bookings }))
        .catch((error: unknown) =>
          setFlagged({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the flagged bookings'),
          }),
        ),
    [session],
  )

  useEffect(() => {
    void load()
  }, [load, session.token])

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Booking conflicts</h1>
            <p className="page-subtitle">
              Bookings that clash since a venue's setup or turnaround time changed. Nothing has
              been cancelled; each flag clears once its clash is resolved.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setFlagged({ state: 'loading' })
              void load()
            }}
            disabled={flagged.state === 'loading'}
          >
            Refresh
          </button>
        </header>
        {renderList()}
      </div>
    </div>
  )

  function renderList() {
    if (flagged.state === 'loading') return <p className="muted">Loading flagged bookings…</p>
    if (flagged.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {flagged.message}
        </p>
      )
    }
    if (flagged.bookings.length === 0) {
      return (
        <div className="card empty">
          <h3>No booking conflicts</h3>
          <p>
            When a setup or turnaround change makes bookings clash, they are flagged here for
            review.
          </p>
        </div>
      )
    }
    return (
      <ul className="booking-request-list" aria-label="Flagged bookings">
        {flagged.bookings.map((booking) => renderBooking(booking))}
      </ul>
    )
  }

  function renderBooking(booking: FlaggedBooking) {
    const venueName = booking.venueName || 'Unnamed venue'
    const unavailable = booking.unavailable ?? []
    return (
      <li key={booking.id} className="card booking-request booking-conflict-card">
        <div className="booking-request-head">
          <h2 className="booking-request-title">{displayEventTitle(booking.eventTitle)}</h2>
          <span className="booking-request-flag-tag">{booking.label || CONFLICT_LABEL}</span>
        </div>

        <dl className="booking-request-facts">
          <div>
            <dt>Venue</dt>
            <dd>{venueName}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{booking.status}</dd>
          </div>
          <div>
            <dt>Booking</dt>
            <dd>{formatBookingTimes(booking.startsAt, booking.endsAt)}</dd>
          </div>
          <div>
            <dt>Occupies the venue</dt>
            <dd>
              {formatBookingTimes(booking.occupiedFrom, booking.occupiedTo)}
              <span className="booking-request-buffers">
                {' '}
                ({minutes(booking.setupMinutes)} setup, {minutes(booking.turnaroundMinutes)}{' '}
                turnaround)
              </span>
            </dd>
          </div>
          <div>
            <dt>Coordinator</dt>
            <dd>{booking.coordinatorName || 'Not assigned'}</dd>
          </div>
        </dl>

        {booking.conflict && (
          <p className="booking-request-flag" role="note">
            Flagged {formatTimestamp(booking.conflict.flaggedAt)}: {booking.conflict.reason}
          </p>
        )}

        {booking.clashes.length > 0 || unavailable.length > 0 ? (
          <div className="booking-request-clash" role="note">
            <strong>Clashes now with:</strong>
            <ul>
              {booking.clashes.map((clash) => (
                <li key={clash.bookingId}>
                  Booking #{clash.bookingId}, {displayEventTitle(clash.eventTitle)} (
                  {clash.status}), occupying{' '}
                  {formatBookingTimes(clash.occupiedFrom, clash.occupiedTo)}
                </li>
              ))}
              {unavailable.map((period) => (
                <li key={`unavailable-${period.id}`}>Venue unavailable {describePeriod(period)}</li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted booking-conflict-resolved">
            Nothing clashes with it any more. Refresh to clear the flag.
          </p>
        )}

        {booking.status === 'Requested' && (
          <div className="booking-request-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => navigate('/booking-requests')}
            >
              Decide on Booking Requests
            </button>
          </div>
        )}
      </li>
    )
  }
}
