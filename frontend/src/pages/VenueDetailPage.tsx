import { useEffect, useState } from 'react'
import './VenueDetailPage.css'
import {
  VenueRuleError,
  deleteVenue,
  detailOrNotRecorded,
  formatCapacity,
  getVenue,
  type VenueRecord,
} from '../venuesStore'
import { navigate } from '../router'
import { formatTimestamp } from '../status'
import { can } from '../permissions'
import { unexpectedFailureMessage, type Session } from '../api'

type VenueDetailPageProps = {
  venueId: string
  session: Session
}

type PageState =
  | { state: 'loading' }
  | { state: 'loaded'; venue: VenueRecord }
  | { state: 'missing' }
  | { state: 'error' }

/**
 * One venue record — US9.2 to read, US9.1b and US9.1c to act on.
 *
 * A description list rather than a form, even for Venue Staff: editing happens
 * on its own page, so this one never has inputs and a Coordinator's view of it
 * is read-only by construction rather than by disabling things. What the two
 * roles see differs only in whether the actions are offered.
 *
 * Every field is shown even when the column is empty, because "no accessibility
 * features recorded" is information a Coordinator needs when weighing a venue,
 * and a row that disappeared when unfilled would hide it.
 */
export default function VenueDetailPage({ venueId, session }: VenueDetailPageProps) {
  const [page, setPage] = useState<PageState>({ state: 'loading' })
  //: US9.1c is a hard delete with no undo, so it is confirmed in the page
  //: rather than fired by the first click.
  const [confirming, setConfirming] = useState(false)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)

  const mayEdit = can(session, 'venues:edit')
  const mayDelete = can(session, 'venues:delete')

  useEffect(() => {
    let cancelled = false
    getVenue(venueId, session)
      .then((venue) => {
        if (cancelled) return
        setPage(venue ? { state: 'loaded', venue } : { state: 'missing' })
      })
      .catch(() => {
        if (!cancelled) setPage({ state: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [venueId, session, session.token])

  function remove() {
    setBusy(true)
    setActionError('')
    deleteVenue(venueId, session)
      .then(() => {
        navigate('/venues')
      })
      .catch((error: unknown) => {
        setBusy(false)
        setConfirming(false)
        if (error instanceof VenueRuleError) {
          setActionError(error.message)
          return
        }
        setActionError(unexpectedFailureMessage(error, 'delete this venue'))
      })
  }

  return (
    <div className="page">
      <div className="shell">
        <a
          className="venue-back"
          href="#/venues"
          onClick={(event) => {
            event.preventDefault()
            navigate('/venues')
          }}
        >
          ← Back to venues
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

    if (page.state === 'missing') {
      return (
        <div className="card empty">
          <h3>Venue not found</h3>
          <p>That venue is not in the catalogue.</p>
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

    const { venue } = page
    return (
      <>
        <header className="venue-detail-head">
          <div>
            <h1 className="page-title">{venue.name}</h1>
            <p className="page-subtitle">{venue.location}</p>
          </div>
          {/* Said plainly to whoever cannot change it, so the absence of an
              edit button reads as deliberate rather than as something missing. */}
          {!mayEdit && !mayDelete && <span className="venue-readonly-tag">Read-only</span>}
        </header>

        {actionError && (
          <p className="form-error" role="alert">
            {actionError}
          </p>
        )}

        <section className="card venue-detail-card">
          <h2 className="venue-section-title">Venue details</h2>
          <dl className="venue-readonly">
            <dt>Location</dt>
            <dd>{detailOrNotRecorded(venue.location)}</dd>

            <dt>Capacity</dt>
            <dd>{formatCapacity(venue.capacity)}</dd>

            <dt>Facilities</dt>
            <dd>{detailOrNotRecorded(venue.facilities)}</dd>

            <dt>Accessibility features</dt>
            <dd>{detailOrNotRecorded(venue.accessibilityFeatures)}</dd>

            <dt>Supported layouts</dt>
            <dd>{detailOrNotRecorded(venue.supportedLayouts)}</dd>

            <dt>Operating hours</dt>
            <dd>{detailOrNotRecorded(venue.operatingHours)}</dd>
          </dl>

          {venue.updatedAt && (
            <p className="venue-detail-note">
              Catalogue record last updated {formatTimestamp(venue.updatedAt)}.
            </p>
          )}
        </section>

        {(mayEdit || mayDelete) && (
          <section className="card venue-actions">
            <h2 className="venue-section-title">Maintain this record</h2>
            {confirming ? (
              <>
                <p className="venue-confirm-text">
                  Delete <strong>{venue.name}</strong> from the catalogue? This cannot be
                  undone.
                </p>
                <div className="venue-action-row">
                  <button
                    type="button"
                    className="btn btn-danger-solid"
                    disabled={busy}
                    onClick={remove}
                  >
                    {busy ? 'Deleting…' : 'Yes, delete it'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => setConfirming(false)}
                  >
                    Keep it
                  </button>
                </div>
              </>
            ) : (
              <div className="venue-action-row">
                {mayEdit && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => navigate(`/venues/${venue.id}/edit`)}
                  >
                    Edit venue
                  </button>
                )}
                {mayDelete && (
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => setConfirming(true)}
                  >
                    Delete venue
                  </button>
                )}
              </div>
            )}
          </section>
        )}
      </>
    )
  }
}
