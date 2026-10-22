import { useEffect, useState } from 'react'
import './VenueFormPage.css'
import {
  EMPTY_VENUE,
  MINUTES_MAX,
  VenueRuleError,
  capacityField,
  createVenue,
  getVenue,
  minutesField,
  parseCapacity,
  parseMinutes,
  saveVenue,
  validateVenue,
  type BookingWindow,
  type SavedVenue,
  type VenueInput,
  type VenueRecheck,
} from '../venuesStore'
import { formatTimestamp } from '../status'
import { navigate } from '../router'
import { unexpectedFailureMessage, type Session } from '../api'

type VenueFormPageProps = {
  /** The venue being edited (US9.1b), or null to create one (US9.1a). */
  venueId: string | null
  session: Session
}

type Fields = {
  name: string
  location: string
  capacity: string
  facilities: string
  accessibilityFeatures: string
  operatingHours: string
  supportedLayouts: string
  setupMinutes: string
  turnaroundMinutes: string
}

/** US9.4: setup and turnaround start at 0, the story's default. */
const EMPTY_FIELDS: Fields = {
  name: '',
  location: '',
  capacity: '',
  facilities: '',
  accessibilityFeatures: '',
  operatingHours: '',
  supportedLayouts: '',
  setupMinutes: '0',
  turnaroundMinutes: '0',
}

type Loading = { state: 'loading' }
type Ready = { state: 'ready' }
type Missing = { state: 'missing' }
type LoadFailed = { state: 'error' }
/** US9.4: saved, and the re-check found bookings that now clash. */
type Rechecked = { state: 'rechecked'; venueId: string; recheck: VenueRecheck }
type PageState = Loading | Ready | Missing | LoadFailed | Rechecked

/** "Booking 12 (event 34): 01 Mar 2027, 09:30 to 01 Mar 2027, 12:45". */
function describeWindow(window: BookingWindow): string {
  return `Booking ${window.bookingId} (event ${window.eventId}) occupies ${formatTimestamp(
    window.occupiedFrom,
  )} to ${formatTimestamp(window.occupiedTo)}`
}

/**
 * One form for US9.1a (create) and US9.1b (update).
 *
 * They are the same form because the acceptance criteria describe the same
 * fields: US9.1a names what is required and what is optional, and US9.1b says
 * every field is editable except the system-generated ones. Two pages would
 * have meant two places for that list to drift.
 *
 * `id` and `createdAt` have no input here and are not in `VenueInput`, so there
 * is nothing to disable and no request that could carry them. That is US9.1b's
 * rule about system-generated fields, kept by construction rather than by a
 * check that has to be remembered.
 */
export default function VenueFormPage({ venueId, session }: VenueFormPageProps) {
  const editing = venueId !== null
  const [page, setPage] = useState<PageState>(
    editing ? { state: 'loading' } : { state: 'ready' },
  )
  const [fields, setFields] = useState<Fields>(EMPTY_FIELDS)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (venueId === null) return

    let cancelled = false
    getVenue(venueId, session)
      .then((venue) => {
        if (cancelled) return
        if (!venue) {
          setPage({ state: 'missing' })
          return
        }
        setFields({
          name: venue.name,
          location: venue.location,
          capacity: capacityField(venue.capacity),
          facilities: venue.facilities,
          accessibilityFeatures: venue.accessibilityFeatures,
          operatingHours: venue.operatingHours,
          supportedLayouts: venue.supportedLayouts,
          setupMinutes: minutesField(venue.setupMinutes),
          turnaroundMinutes: minutesField(venue.turnaroundMinutes),
        })
        setPage({ state: 'ready' })
      })
      .catch(() => {
        if (!cancelled) setPage({ state: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token])

  function set<K extends keyof Fields>(field: K, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
  }

  /** The form as the API takes it, or a sentence saying what is wrong. */
  function readForm(): VenueInput | string {
    const capacity = parseCapacity(fields.capacity)
    if (capacity === 'invalid') {
      return 'Capacity must be a positive whole number of people.'
    }
    const setupMinutes = parseMinutes(fields.setupMinutes, 'setup')
    if (typeof setupMinutes === 'string') return setupMinutes
    const turnaroundMinutes = parseMinutes(fields.turnaroundMinutes, 'turnaround')
    if (typeof turnaroundMinutes === 'string') return turnaroundMinutes

    const input: VenueInput = {
      ...EMPTY_VENUE,
      name: fields.name.trim(),
      location: fields.location.trim(),
      capacity,
      facilities: fields.facilities.trim(),
      accessibilityFeatures: fields.accessibilityFeatures.trim(),
      operatingHours: fields.operatingHours.trim(),
      supportedLayouts: fields.supportedLayouts.trim(),
      setupMinutes,
      turnaroundMinutes,
    }

    const complaint = validateVenue(input)
    return complaint === '' ? input : complaint
  }

  function submit(submitEvent: { preventDefault(): void }) {
    submitEvent.preventDefault()
    setError('')

    const input = readForm()
    if (typeof input === 'string') {
      setError(input)
      return
    }

    setBusy(true)
    const written: Promise<SavedVenue> = editing
      ? saveVenue(venueId as string, input, session)
      : createVenue(input, session)

    written
      .then((venue) => {
        // US9.4: a changed setup or turnaround time re-checks the venue's
        // bookings. Clashes it found are shown here before moving on, because
        // nothing else will have told Venue Staff — nothing was cancelled.
        const recheck = venue.recheck
        // US15.2: a booking pushed into an unavailability period is flagged
        // without being one of US9.4's pairs, so either one shows the result.
        if (
          recheck &&
          (recheck.conflicts.length > 0 || (recheck.flaggedBookingIds ?? []).length > 0)
        ) {
          setBusy(false)
          setPage({ state: 'rechecked', venueId: venue.id, recheck })
          return
        }
        // Straight to the record, so the change is visible rather than asserted.
        navigate(`/venues/${venue.id}`)
      })
      .catch((writeError: unknown) => {
        setBusy(false)
        if (writeError instanceof VenueRuleError) {
          // A name already taken, or a field the server reads differently.
          setError(writeError.message)
          return
        }
        setError(unexpectedFailureMessage(writeError, 'save this venue'))
      })
  }

  return (
    <div className="page">
      <div className="shell venue-form-shell">
        <a
          className="venue-back"
          href={editing ? `#/venues/${venueId}` : '#/venues'}
          onClick={(clickEvent) => {
            clickEvent.preventDefault()
            navigate(editing ? `/venues/${venueId}` : '/venues')
          }}
        >
          {editing ? '← Back to venue' : '← Back to venues'}
        </a>
        {renderBody()}
      </div>
    </div>
  )

  function renderBody() {
    if (page.state === 'loading') {
      return <p className="muted">Loading venue…</p>
    }

    if (page.state === 'error') {
      return (
        <p className="form-error" role="alert">
          Could not load this venue. Check the API is running and try again.
        </p>
      )
    }

    if (page.state === 'rechecked') {
      const { recheck } = page
      const count = recheck.conflicts.length
      const flagged = recheck.flaggedBookingIds ?? []
      return (
        <section className="card venue-recheck" aria-labelledby="venue-recheck-title">
          <h1 className="page-title" id="venue-recheck-title">
            {count > 0
              ? `Saved — ${count} booking ${count === 1 ? 'clash needs' : 'clashes need'} attention`
              : `Saved — ${flagged.length} ${flagged.length === 1 ? 'booking needs' : 'bookings need'} attention`}
          </h1>
          <p className="page-subtitle" role="status">
            With {recheck.setupMinutes} minutes' setup and {recheck.turnaroundMinutes}{' '}
            minutes' turnaround, {recheck.checkedBookings} active{' '}
            {recheck.checkedBookings === 1 ? 'booking was' : 'bookings were'} checked again.
            These now overlap. Nothing has been cancelled or removed.
          </p>
          <ul className="venue-recheck-list">
            {recheck.conflicts.map((conflict) => (
              <li key={`${conflict.first.bookingId}-${conflict.second.bookingId}`}>
                <span
                  className={
                    conflict.causedByChange
                      ? 'venue-recheck-tag venue-recheck-tag-new'
                      : 'venue-recheck-tag'
                  }
                >
                  {conflict.causedByChange ? 'New with this change' : 'Already overlapping'}
                </span>
                <span>{describeWindow(conflict.first)}</span>
                <span>{describeWindow(conflict.second)}</span>
              </li>
            ))}
          </ul>
          {flagged.length > 0 && (
            <p className="venue-recheck-flagged" role="status">
              {flagged.length === 1
                ? `Booking #${flagged[0]} is`
                : `Bookings ${flagged.map((id) => `#${id}`).join(', ')} are`}{' '}
              now marked “Conflict – review needed”, and{' '}
              {flagged.length === 1 ? 'its Coordinator has' : 'their Coordinators have'} been
              notified.
            </p>
          )}
          <div className="venue-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate(`/venues/${page.venueId}`)}
            >
              View venue
            </button>
            {flagged.length > 0 && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate('/booking-conflicts')}
              >
                Review booking conflicts
              </button>
            )}
          </div>
        </section>
      )
    }

    if (page.state === 'missing') {
      return (
        <div className="card empty">
          <h3>Venue not found</h3>
          <p>That venue is not in the catalogue, so there is nothing to edit.</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate('/venues')}
            style={{ marginTop: '1.25rem' }}
          >
            Back to venues
          </button>
        </div>
      )
    }

    return (
      <>
        <header className="page-head">
          <div>
            <h1 className="page-title">{editing ? 'Edit venue' : 'Add a venue'}</h1>
            <p className="page-subtitle">
              {editing
                ? 'Keep the catalogue accurate as the building changes.'
                : 'Add a venue so Coordinators have it to plan around.'}
            </p>
          </div>
        </header>

        <form className="card venue-form" onSubmit={submit} noValidate>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <fieldset className="venue-fieldset" disabled={busy}>
            <legend className="venue-form-legend">Required</legend>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-name">
                Name
              </label>
              <input
                id="venue-name"
                type="text"
                value={fields.name}
                maxLength={255}
                onChange={(changeEvent) => set('name', changeEvent.target.value)}
              />
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-location">
                Location
              </label>
              <input
                id="venue-location"
                type="text"
                value={fields.location}
                maxLength={500}
                onChange={(changeEvent) => set('location', changeEvent.target.value)}
              />
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-capacity">
                Capacity
              </label>
              <input
                id="venue-capacity"
                // `inputMode` rather than type=number: a number spinner lets a
                // browser hand back "" for a value the user can see, and the
                // rule here is a positive whole number of people.
                type="text"
                inputMode="numeric"
                aria-describedby="venue-capacity-hint"
                value={fields.capacity}
                onChange={(changeEvent) => set('capacity', changeEvent.target.value)}
              />
              {/* Described by, not labelled by: the hint belongs to the field
                  without becoming part of its name. */}
              <span className="venue-field-hint" id="venue-capacity-hint">
                A positive whole number of people.
              </span>
            </div>
          </fieldset>

          <fieldset className="venue-fieldset" disabled={busy}>
            <legend className="venue-form-legend">Setup and turnaround</legend>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-setup">
                Setup time (minutes)
              </label>
              <input
                id="venue-setup"
                type="text"
                inputMode="numeric"
                aria-describedby="venue-setup-hint"
                value={fields.setupMinutes}
                onChange={(changeEvent) => set('setupMinutes', changeEvent.target.value)}
              />
              <span className="venue-field-hint" id="venue-setup-hint">
                Time to prepare the room before each booking. Whole minutes, 0 to {MINUTES_MAX}.
              </span>
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-turnaround">
                Turnaround time (minutes)
              </label>
              <input
                id="venue-turnaround"
                type="text"
                inputMode="numeric"
                aria-describedby="venue-turnaround-hint"
                value={fields.turnaroundMinutes}
                onChange={(changeEvent) => set('turnaroundMinutes', changeEvent.target.value)}
              />
              <span className="venue-field-hint" id="venue-turnaround-hint">
                Time to reset the room after each booking. Whole minutes, 0 to {MINUTES_MAX}.
                {editing && ' Changing either time re-checks this venue’s bookings.'}
              </span>
            </div>
          </fieldset>

          <fieldset className="venue-fieldset" disabled={busy}>
            <legend className="venue-form-legend">Optional</legend>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-facilities">
                Facilities
              </label>
              <textarea
                id="venue-facilities"
                rows={2}
                value={fields.facilities}
                onChange={(changeEvent) => set('facilities', changeEvent.target.value)}
              />
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-accessibility">
                Accessibility features
              </label>
              <textarea
                id="venue-accessibility"
                rows={2}
                aria-describedby="venue-accessibility-hint"
                value={fields.accessibilityFeatures}
                onChange={(changeEvent) =>
                  set('accessibilityFeatures', changeEvent.target.value)
                }
              />
              <span className="venue-field-hint" id="venue-accessibility-hint">
                Coordinators filter on this, so name each feature you record.
              </span>
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-layouts">
                Supported layouts
              </label>
              <textarea
                id="venue-layouts"
                rows={2}
                value={fields.supportedLayouts}
                onChange={(changeEvent) =>
                  set('supportedLayouts', changeEvent.target.value)
                }
              />
            </div>

            <div className="venue-field">
              <label className="venue-field-label" htmlFor="venue-hours">
                Operating hours
              </label>
              <input
                id="venue-hours"
                type="text"
                value={fields.operatingHours}
                maxLength={255}
                onChange={(changeEvent) => set('operatingHours', changeEvent.target.value)}
              />
            </div>
          </fieldset>

          <div className="venue-form-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Saving…' : editing ? 'Save changes' : 'Add venue'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => navigate(editing ? `/venues/${venueId}` : '/venues')}
            >
              Cancel
            </button>
          </div>
        </form>
      </>
    )
  }
}
