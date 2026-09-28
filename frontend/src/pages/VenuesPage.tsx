import { useEffect, useState } from 'react'
import './VenuesPage.css'
import {
  NO_FILTERS,
  VenueRuleError,
  formatCapacity,
  describeDates,
  hasDates,
  hasFilters,
  listVenues,
  type VenueFilters,
  type VenueRecord,
} from '../venuesStore'
import { navigate } from '../router'
import { can } from '../permissions'
import { unexpectedFailureMessage, type Session } from '../api'

type VenuesPageProps = {
  session: Session
}

/**
 * A fetched list, tagged with the filters that produced it.
 *
 * Tagged rather than cleared, so "still loading" is derived during render from
 * whether the result on hand matches the filters now applied. Resetting the
 * list inside the effect would do the same job by starting another render, and
 * this way there is one source of truth for which list is on screen.
 */
type Result = {
  filters: VenueFilters
  venues: VenueRecord[]
  error: string
}

/**
 * The venue catalogue — US9.2 to look at, US9.3 to narrow, and US12.1 to leave
 * out the venues marked unavailable on the dates a Coordinator is planning for.
 *
 * The filters are a form with an Apply button rather than live-as-you-type.
 * Each apply is a request, and a debounce would have meant either a request per
 * keystroke or a delay the user cannot see; a submit says plainly when the list
 * is being asked for again. Clear resets to the unfiltered catalogue.
 *
 * Filtering happens on the server. That is US9.3's "just query params", and it
 * also means the narrowed list is the whole answer rather than a subset of
 * whatever this page happened to have already fetched.
 */
export default function VenuesPage({ session }: VenuesPageProps) {
  const [result, setResult] = useState<Result | null>(null)
  //: What the boxes hold, and separately what the current list was fetched
  //: with — so the heading describes the list on screen, not the half-typed
  //: filter above it.
  const [fields, setFields] = useState<VenueFilters>(NO_FILTERS)
  const [applied, setApplied] = useState<VenueFilters>(NO_FILTERS)

  const mayAdd = can(session, 'venues:create')
  const narrowed = hasFilters(applied)
  const datesApplied = hasDates(applied)
  const loading = result === null || result.filters !== applied
  const venues = loading ? null : result.venues
  const loadError = loading ? '' : result.error

  useEffect(() => {
    let cancelled = false
    listVenues(session, applied)
      .then((loaded) => {
        if (!cancelled) setResult({ filters: applied, venues: loaded, error: '' })
      })
      .catch((error: unknown) => {
        // An empty catalogue and a failed request look identical if both show
        // "no venues", and they call for opposite responses from the reader.
        // So do the failures from each other: a filter the server would not
        // read is fixed in the box above, and says so, while everything else
        // sends the reader to the API or the backend log.
        if (cancelled) return
        setResult({
          filters: applied,
          venues: [],
          error:
            error instanceof VenueRuleError
              ? error.message
              : unexpectedFailureMessage(error, 'load the venue catalogue'),
        })
      })
    return () => {
      cancelled = true
    }
  }, [session, session.token, applied])

  function set<K extends keyof VenueFilters>(field: K, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
  }

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Venues</h1>
            <p className="page-subtitle">
              The ConnectSphere venue catalogue. Open a venue for its full details.
            </p>
          </div>
          {mayAdd && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate('/venues/new')}
            >
              Add venue
            </button>
          )}
        </header>

        <form
          className="card venue-filters"
          onSubmit={(submitEvent) => {
            submitEvent.preventDefault()
            setApplied(fields)
          }}
        >
          <h2 className="venue-filters-title">Narrow the catalogue</h2>
          <div className="venue-filter-row">
            <label className="venue-filter">
              <span className="venue-filter-label">Minimum capacity</span>
              <input
                type="text"
                inputMode="numeric"
                placeholder="Any"
                value={fields.minCapacity}
                onChange={(changeEvent) => set('minCapacity', changeEvent.target.value)}
              />
            </label>

            <label className="venue-filter">
              <span className="venue-filter-label">Location</span>
              <input
                type="text"
                placeholder="Anywhere"
                value={fields.location}
                onChange={(changeEvent) => set('location', changeEvent.target.value)}
              />
            </label>

            <label className="venue-filter">
              <span className="venue-filter-label">Accessibility</span>
              <input
                type="text"
                placeholder="Any feature"
                value={fields.accessibility}
                onChange={(changeEvent) => set('accessibility', changeEvent.target.value)}
              />
            </label>
          </div>

          {/* US12.1: a venue closed on any of these days is left out, so it is
              not considered for them. One date alone means that one day. */}
          <fieldset className="venue-filter-dates">
            <legend className="venue-filter-label">Dates you are planning for</legend>
            <div className="venue-filter-row venue-filter-row-dates">
              <label className="venue-filter">
                <span className="venue-filter-label">Available from</span>
                <input
                  type="date"
                  value={fields.availableFrom}
                  onChange={(changeEvent) => set('availableFrom', changeEvent.target.value)}
                />
              </label>

              <label className="venue-filter">
                <span className="venue-filter-label">Available to</span>
                <input
                  type="date"
                  min={fields.availableFrom || undefined}
                  value={fields.availableTo}
                  onChange={(changeEvent) => set('availableTo', changeEvent.target.value)}
                />
              </label>
            </div>
            <p className="venue-filter-note venue-filter-dates-note">
              Venues marked unavailable on any of these dates are left out. One date alone
              means that day.
            </p>
          </fieldset>

          <div className="venue-filter-actions">
            <button type="submit" className="btn btn-primary btn-sm">
              Apply filters
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={!narrowed && !hasFilters(fields)}
              onClick={() => {
                setFields(NO_FILTERS)
                setApplied(NO_FILTERS)
              }}
            >
              Clear
            </button>
            {/* A venue has to satisfy every filter, not any one of them. Said
                here because "capacity 200, location Library" reads ambiguously
                to anyone who has used a search that ORs its terms. */}
            <span className="venue-filter-note">All filters must match.</span>
          </div>
        </form>

        {loadError && (
          <p className="form-error" role="alert">
            {loadError}
          </p>
        )}

        {venues !== null && !loadError && (
          <p className="venue-summary" role="status">
            {venues.length} {venues.length === 1 ? 'venue' : 'venues'}
            {narrowed && ' matching your filters'}
            {datesApplied && `, available ${describeDates(applied)}`}
          </p>
        )}

        {venues === null ? (
          <p className="muted">Loading venues…</p>
        ) : loadError ? null : venues.length === 0 ? (
          <div className="card empty">
            <h3>{narrowed ? 'Nothing matches those filters' : 'No venues yet'}</h3>
            <p>
              {narrowed
                ? datesApplied
                  ? 'Every filter has to match, and venues unavailable on any of those dates are left out. Try other dates or fewer criteria.'
                  : 'Every filter has to match. Try a lower capacity or fewer criteria.'
                : mayAdd
                  ? 'Add the first venue and Coordinators can start planning around it.'
                  : 'Once venues are added to ConnectSphere, they appear here.'}
            </p>
            {narrowed ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setFields(NO_FILTERS)
                  setApplied(NO_FILTERS)
                }}
                style={{ marginTop: '1.25rem' }}
              >
                Clear filters
              </button>
            ) : (
              mayAdd && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => navigate('/venues/new')}
                  style={{ marginTop: '1.25rem' }}
                >
                  Add venue
                </button>
              )
            )}
          </div>
        ) : (
          <ul className="venue-list">
            {venues.map((venue) => (
              <li key={venue.id}>
                <a
                  className="venue-row card"
                  href={`#/venues/${venue.id}`}
                  onClick={(clickEvent) => {
                    clickEvent.preventDefault()
                    navigate(`/venues/${venue.id}`)
                  }}
                >
                  <div className="venue-row-main">
                    <h3 className="venue-row-title">{venue.name}</h3>
                    <p className="venue-row-meta">{venue.location}</p>
                  </div>
                  <div className="venue-row-end">
                    <span className="venue-capacity">{formatCapacity(venue.capacity)}</span>
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
