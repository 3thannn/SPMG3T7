import { useEffect, useState, type FormEvent } from 'react'
import './VenueUnavailability.css'
import {
  EMPTY_UNAVAILABILITY,
  REASON_MAX,
  UNAVAILABILITY_REASON_TYPES,
  VenueRuleError,
  formatDate,
  formatDateRange,
  formatUnavailabilityReason,
  listUnavailability,
  markUnavailable,
  rangeTiming,
  todayIso,
  validateUnavailability,
  type UnavailabilityInput,
  type UnavailabilityRecord,
  type UnavailabilityReasonType,
} from '../venuesStore'
import { unexpectedFailureMessage, type Session } from '../api'

type VenueUnavailabilityProps = {
  venueId: string
  session: Session
  /** Venue Staff: offer the form. Everyone else reads. */
  mayMark: boolean
  /** YYYY-MM-DD. Injected by tests; the viewer's own today otherwise. */
  today?: string
}

type Ranges =
  | { state: 'loading' }
  | { state: 'loaded'; ranges: UnavailabilityRecord[] }
  | { state: 'error'; message: string }

const TIMING_LABEL = { current: 'Now', upcoming: 'Upcoming', past: 'Past' } as const

/** Soonest first, the order the server sends — kept when a new range is added. */
function byDates(a: UnavailabilityRecord, b: UnavailabilityRecord): number {
  return a.startDate.localeCompare(b.startDate) || a.endDate.localeCompare(b.endDate)
}

/**
 * A venue's blackout periods — US12.1.
 *
 * Coordinators read it on the venue record, which is the story's "when viewing
 * the venue"; Venue Staff also get the form that records one. Its own card, and
 * its own request, so a failure to load the blackouts says so here and leaves
 * the venue details above it readable.
 *
 * Ranges that are over are folded away under "Past" rather than dropped. The
 * story asks for the record, but a Coordinator planning next month reads what
 * is current and coming first.
 */
export default function VenueUnavailability({
  venueId,
  session,
  mayMark,
  today = todayIso(),
}: VenueUnavailabilityProps) {
  const [ranges, setRanges] = useState<Ranges>({ state: 'loading' })
  const [fields, setFields] = useState<UnavailabilityInput>(EMPTY_UNAVAILABILITY)
  const [formError, setFormError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    listUnavailability(venueId, session)
      .then((loaded) => {
        if (!cancelled) setRanges({ state: 'loaded', ranges: loaded })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setRanges({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the unavailable dates'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token])

  function set<K extends keyof UnavailabilityInput>(field: K, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
    setSaved('')
  }

  function submit(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    const input = {
      ...fields,
      otherReason: fields.otherReason.trim(),
    }
    const problem = validateUnavailability(input)
    if (problem) {
      setFormError(problem)
      return
    }

    setBusy(true)
    setFormError('')
    markUnavailable(venueId, input, session)
      .then((created) => {
        setRanges((current) =>
          current.state === 'loaded'
            ? { state: 'loaded', ranges: [...current.ranges, created].sort(byDates) }
            : current,
        )
        setFields(EMPTY_UNAVAILABILITY)
        // US12.2: Include flagged bookings count in success message
        const flaggedCount = created.flaggedBookingsCount ?? 0
        let successMessage = `Marked unavailable: ${formatDateRange(created.startDate, created.endDate)}.`
        if (flaggedCount > 0) {
          successMessage += ` ${flaggedCount} booking${flaggedCount === 1 ? '' : 's'} flagged as needing replacement.`
        }
        setSaved(successMessage)
      })
      .catch((error: unknown) => {
        setFormError(
          error instanceof VenueRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'save these dates'),
        )
      })
      .finally(() => setBusy(false))
  }

  return (
    <section className="card venue-unavailability" aria-labelledby="venue-unavailability-title">
      <h2 className="venue-section-title" id="venue-unavailability-title">
        Unavailable dates
      </h2>
      {renderRanges()}
      {mayMark && renderForm()}
    </section>
  )

  function renderRanges() {
    if (ranges.state === 'loading') {
      return <p className="muted">Loading unavailable dates…</p>
    }
    if (ranges.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {ranges.message}
        </p>
      )
    }

    const ahead = ranges.ranges.filter((range) => rangeTiming(range, today) !== 'past')
    const past = ranges.ranges.filter((range) => rangeTiming(range, today) === 'past')
    const current = ahead.filter((range) => rangeTiming(range, today) === 'current')
    // With overlapping closures, the venue is back when the last of them ends.
    const reopens = current.reduce((last, range) => (range.endDate > last ? range.endDate : last), '')

    return (
      <>
        {current.length > 0 && (
          <p className="unavailability-banner" role="status">
            <strong>Unavailable today</strong> through {formatDate(reopens)}. Plan events here
            for later dates only.
          </p>
        )}

        {ahead.length === 0 ? (
          <p className="muted unavailability-none">
            No current or upcoming unavailable dates recorded.
          </p>
        ) : (
          <ul className="unavailability-list" aria-label="Current and upcoming unavailable dates">
            {ahead.map((range) => renderRange(range))}
          </ul>
        )}

        {past.length > 0 && (
          <details className="unavailability-past">
            <summary>Past ({past.length})</summary>
            <ul className="unavailability-list" aria-label="Past unavailable dates">
              {past.map((range) => renderRange(range))}
            </ul>
          </details>
        )}
      </>
    )
  }

  function renderRange(range: UnavailabilityRecord) {
    const timing = rangeTiming(range, today)
    return (
      <li key={range.id} className={`unavailability-row is-${timing}`}>
        <span className="unavailability-dates">
          {formatDateRange(range.startDate, range.endDate)}
        </span>
        <span className={`unavailability-tag is-${timing}`}>{TIMING_LABEL[timing]}</span>
        <span className="unavailability-reason">{formatUnavailabilityReason(range)}</span>
      </li>
    )
  }

  function renderForm() {
    return (
      <form className="unavailability-form" onSubmit={submit} noValidate>
        <h3 className="unavailability-form-title">Mark dates unavailable</h3>
        <p className="unavailability-form-hint">
          Both dates are included. For a single day, use the same date twice.
        </p>

        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        {saved && (
          <p className="unavailability-saved" role="status">
            {saved}
          </p>
        )}

        <fieldset className="unavailability-fields" disabled={busy}>
          <div className="field">
            <label htmlFor="unavailable-start">Start date</label>
            <input
              id="unavailable-start"
              type="date"
              min={today}
              value={fields.startDate}
              onChange={(changeEvent) => set('startDate', changeEvent.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="unavailable-end">End date</label>
            <input
              id="unavailable-end"
              type="date"
              min={fields.startDate || today}
              value={fields.endDate}
              onChange={(changeEvent) => set('endDate', changeEvent.target.value)}
            />
          </div>

          <div className="field unavailability-reason-field">
            <label htmlFor="unavailable-reason-type">Reason</label>
            <select
              id="unavailable-reason-type"
              value={fields.reasonType}
              onChange={(changeEvent) =>
                set('reasonType', changeEvent.target.value as UnavailabilityReasonType | '')
              }
            >
              <option value="">Select a reason…</option>
              {Object.entries(UNAVAILABILITY_REASON_TYPES).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {fields.reasonType === 'other' && (
            <div className="field unavailability-other-reason-field">
              <label htmlFor="unavailable-other-reason">Custom reason</label>
              <input
                id="unavailable-other-reason"
                type="text"
                maxLength={REASON_MAX}
                placeholder="Describe the reason…"
                value={fields.otherReason}
                onChange={(changeEvent) => set('otherReason', changeEvent.target.value)}
              />
            </div>
          )}
        </fieldset>

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Mark unavailable'}
        </button>
      </form>
    )
  }
}
