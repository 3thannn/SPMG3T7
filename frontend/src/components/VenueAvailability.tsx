import { useEffect, useState, type FormEvent } from 'react'
import './VenueAvailability.css'
import {
  AVAILABILITY_KIND_LABELS,
  VenueRuleError,
  asSingaporeTime,
  defaultAvailabilityRange,
  formatMinutes,
  formatUnavailabilityReason,
  getAvailability,
  todayIso,
  validateAvailabilityRange,
  type AvailabilityEntry,
  type AvailabilityRange,
  type VenueAvailability as Availability,
} from '../venuesStore'
import { formatBookingTimes } from '../eventsStore'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

type VenueAvailabilityProps = {
  venueId: string
  session: Session
  /** YYYY-MM-DD. Injected by tests; the viewer's own today otherwise. */
  today?: string
}

type Loaded =
  | { state: 'loading' }
  | { state: 'loaded'; availability: Availability }
  | { state: 'error'; message: string }

/** "24 Nov 2026", the style the booking times on this card use. */
function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('en-SG', {
    timeZone: 'UTC',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function formatDays(first: string, last: string): string {
  return first === last ? formatDay(first) : `${formatDay(first)} – ${formatDay(last)}`
}

/**
 * What is taking up a venue over a date range — US12.3.
 *
 * Coordinators and Venue Staff pick a range (the next 14 days to start with)
 * and read one list, in time order, of the bookings, holds and closures that
 * stop the venue being requested. A booking shows the full window it holds
 * the room for, setup and turnaround included, because that is the time
 * nobody else can have. What no longer holds the venue (cancelled, rejected,
 * expired) is left out by the server.
 *
 * Its own card and its own request, like US12.1's, so a failure here leaves
 * the venue details readable.
 */
export default function VenueAvailability({
  venueId,
  session,
  today = todayIso(),
}: VenueAvailabilityProps) {
  const [fields, setFields] = useState<AvailabilityRange>(() => defaultAvailabilityRange(today))
  const [shown, setShown] = useState<AvailabilityRange>(fields)
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' })
  const [formError, setFormError] = useState('')

  useEffect(() => {
    let cancelled = false
    getAvailability(venueId, shown, session)
      .then((availability) => {
        if (!cancelled) setLoaded({ state: 'loaded', availability })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setLoaded({
          state: 'error',
          message:
            error instanceof VenueRuleError
              ? error.message
              : unexpectedFailureMessage(error, 'load what is taking up this venue'),
        })
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token, shown])

  function submit(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    const problem = validateAvailabilityRange(fields)
    setFormError(problem)
    if (problem) return
    setLoaded({ state: 'loading' })
    setShown({ ...fields })
  }

  return (
    <section className="card venue-availability" aria-labelledby="venue-availability-title">
      <h2 id="venue-availability-title" className="venue-section-title">
        Availability
      </h2>
      <p className="venue-availability-intro">
        Everything taking up this venue in the dates you pick. Any time not listed can be
        requested.
      </p>

      <form className="availability-range" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="availability-from">From</label>
          <input
            id="availability-from"
            type="date"
            value={fields.from}
            onChange={(changeEvent) => setFields({ ...fields, from: changeEvent.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="availability-to">To</label>
          <input
            id="availability-to"
            type="date"
            min={fields.from}
            value={fields.to}
            onChange={(changeEvent) => setFields({ ...fields, to: changeEvent.target.value })}
          />
        </div>
        <button type="submit" className="btn btn-secondary" disabled={loaded.state === 'loading'}>
          Show
        </button>
      </form>

      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}

      {renderList()}
    </section>
  )

  function renderList() {
    if (loaded.state === 'loading') {
      return <p className="muted availability-none">Loading availability…</p>
    }
    if (loaded.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {loaded.message}
        </p>
      )
    }

    const { availability } = loaded
    const range = formatDays(availability.from, availability.to)
    const hasBuffers = availability.setupMinutes > 0 || availability.turnaroundMinutes > 0

    return (
      <>
        <p className="availability-showing" role="status">
          Showing {range}.
          {hasBuffers &&
            ` Booking times include ${formatMinutes(availability.setupMinutes)} setup ` +
              `and ${formatMinutes(availability.turnaroundMinutes)} turnaround.`}
        </p>
        {availability.entries.length === 0 ? (
          <p className="muted availability-none">
            Nothing is booked, held or closed here from {formatDay(availability.from)} to{' '}
            {formatDay(availability.to)}.
          </p>
        ) : (
          <ul className="availability-list" aria-label={`What is taking up this venue, ${range}`}>
            {availability.entries.map((entry) => renderEntry(entry))}
          </ul>
        )}
      </>
    )
  }

  function renderEntry(entry: AvailabilityEntry) {
    const isPeriod = entry.kind === 'unavailable'
    return (
      <li
        key={isPeriod ? `period-${entry.periodId}` : `booking-${entry.bookingId}`}
        className={`availability-row is-${entry.kind}`}
      >
        <span className="availability-when">
          {isPeriod
            ? formatDays(entry.startDate, entry.endDate)
            : formatBookingTimes(asSingaporeTime(entry.startsAt), asSingaporeTime(entry.endsAt))}
        </span>
        <span className={`availability-tag is-${entry.kind}`}>
          {AVAILABILITY_KIND_LABELS[entry.kind]}
        </span>
        <span className="availability-detail">
          {isPeriod ? (
            entry.reasonType ? (
              formatUnavailabilityReason({
                reasonType: entry.reasonType,
                otherReason: entry.otherReason,
              })
            ) : (
              'No reason given'
            )
          ) : (
            <>
              <span className="availability-what">
                {entry.eventTitle || `Booking #${entry.bookingId} for another event`}
              </span>
              <span className="availability-sub">
                Event{' '}
                {formatBookingTimes(
                  asSingaporeTime(entry.eventStartsAt),
                  asSingaporeTime(entry.eventEndsAt),
                )}
              </span>
              {entry.kind === 'hold' && entry.holdExpiresAt && (
                <span className="availability-sub availability-expiry">
                  Hold expires {formatTimestamp(asSingaporeTime(entry.holdExpiresAt))}
                </span>
              )}
            </>
          )}
        </span>
      </li>
    )
  }
}
