import { useEffect, useState } from 'react'
import './SafetyReviewDetails.css'
import {
  formatBookingTimes,
  getSafetyReview,
  type ReviewedEquipment,
  type ReviewedVenue,
  type SafetyReview,
} from '../eventsStore'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

type Props = {
  eventId: string
  session: Session
}

type Loaded =
  | { state: 'loading' }
  | { state: 'loaded'; review: SafetyReview }
  | { state: 'error'; message: string }

function orNone(value: string, none = 'None recorded'): string {
  return value.trim() ? value : none
}

function minutes(value: number): string {
  return value === 1 ? '1 minute' : `${value} minutes`
}

function formatDay(iso: string): string {
  const day = new Date(`${iso}T00:00`)
  return day.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

/**
 * US17.1: everything the Safety Officer needs to assess an event, in one place.
 *
 * Expected attendance and the event's accessibility requirements, then each
 * booked venue — its capacity against the headcount, the layout asked for
 * against the ones it supports, its accessibility against what was asked,
 * and its known restrictions — then the reserved equipment.
 *
 * Read-only: there is nothing here to edit. The decision itself is the
 * separate safety check panel (US4.4/US17.2).
 */
export default function SafetyReviewDetails({ eventId, session }: Props) {
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' })

  useEffect(() => {
    let cancelled = false
    getSafetyReview(eventId, session)
      .then((review) => {
        if (!cancelled) setLoaded({ state: 'loaded', review })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoaded({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the safety review'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [eventId, session])

  return (
    <section className="card card-pad safety-review" aria-labelledby="safety-review-title">
      <h2 className="detail-section-title" id="safety-review-title">
        Safety review
      </h2>
      {loaded.state === 'loading' && <p className="muted">Loading the safety review…</p>}
      {loaded.state === 'error' && (
        <p className="form-error" role="alert">
          {loaded.message}
        </p>
      )}
      {loaded.state === 'loaded' && <ReviewBody review={loaded.review} />}
    </section>
  )
}

function ReviewBody({ review }: { review: SafetyReview }) {
  return (
    <>
      <dl className="safety-review-facts">
        <div>
          <dt>Expected attendance</dt>
          <dd>
            {review.expectedAttendance === null
              ? 'Not estimated'
              : `${review.expectedAttendance} people`}
          </dd>
        </div>
        <div>
          <dt>Accessibility requirements</dt>
          <dd>{orNone(review.accessibilityNeeds, 'Not stated')}</dd>
        </div>
        <div>
          <dt>Preferred layout</dt>
          <dd>{orNone(review.preferredLayout, 'Not stated')}</dd>
        </div>
        <div>
          <dt>Venue requirements</dt>
          <dd>{orNone(review.venueRequirements, 'Not stated')}</dd>
        </div>
        <div>
          <dt>Waiting since</dt>
          <dd>{formatTimestamp(review.waitingSince)}</dd>
        </div>
      </dl>

      <h3 className="safety-review-heading">Booked venues</h3>
      {review.venues.length === 0 ? (
        <p className="muted">No venue is booked for this event.</p>
      ) : (
        <ul className="safety-review-list" aria-label="Booked venues">
          {review.venues.map((venue) => (
            <VenueCard key={venue.bookingId} venue={venue} />
          ))}
        </ul>
      )}

      <h3 className="safety-review-heading">Reserved equipment</h3>
      {review.equipment.length === 0 ? (
        <p className="muted">No equipment is reserved for this event.</p>
      ) : (
        <ul className="safety-review-list" aria-label="Reserved equipment">
          {review.equipment.map((line) => (
            <EquipmentRow key={line.id} line={line} />
          ))}
        </ul>
      )}
    </>
  )
}

function VenueCard({ venue }: { venue: ReviewedVenue }) {
  const capacity = venue.capacity === null ? 'Unknown' : `${venue.capacity} people`
  const headcount = venue.headcount === null ? 'Not set' : `${venue.headcount} people`
  return (
    <li className={`safety-review-item${venue.overCapacity ? ' is-warning' : ''}`}>
      <div className="safety-review-item-head">
        <strong>{venue.venueName}</strong>
        {venue.location && <span className="muted"> · {venue.location}</span>}
        <p className="safety-review-when">{formatBookingTimes(venue.startsAt, venue.endsAt)}</p>
      </div>
      {venue.overCapacity && (
        <p className="safety-review-warning" role="note">
          More people are booked into this venue than it holds.
        </p>
      )}
      <dl className="safety-review-facts">
        <div>
          <dt>Capacity</dt>
          <dd>{capacity}</dd>
        </div>
        <div>
          <dt>Headcount</dt>
          <dd>{headcount}</dd>
        </div>
        <div>
          <dt>Layout</dt>
          <dd>
            {orNone(venue.requiredLayout, 'None requested')} · supports{' '}
            {orNone(venue.supportedLayouts)}
          </dd>
        </div>
        <div>
          <dt>Venue accessibility</dt>
          <dd>{orNone(venue.accessibilityFeatures)}</dd>
        </div>
        <div>
          <dt>Accessibility asked for</dt>
          <dd>
            {venue.accessibilityNeeds.length === 0
              ? 'None'
              : venue.accessibilityNeeds.join(', ')}
          </dd>
        </div>
        <div>
          <dt>Facilities</dt>
          <dd>{orNone(venue.facilities)}</dd>
        </div>
      </dl>
      <h4 className="safety-review-subheading">Known restrictions</h4>
      <ul className="safety-review-restrictions">
        <li>Operating hours: {orNone(venue.operatingHours)}</li>
        <li>
          Setup {minutes(venue.setupMinutes)} before, turnaround{' '}
          {minutes(venue.turnaroundMinutes)} after
        </li>
        {venue.closures.length === 0 ? (
          <li>No upcoming unavailability</li>
        ) : (
          venue.closures.map((closure) => (
            <li key={`${closure.startDate}-${closure.endDate}`}>
              Unavailable {formatDay(closure.startDate)}
              {closure.endDate !== closure.startDate && ` – ${formatDay(closure.endDate)}`}
              {closure.reason && `: ${closure.reason}`}
            </li>
          ))
        )}
      </ul>
    </li>
  )
}

function EquipmentRow({ line }: { line: ReviewedEquipment }) {
  return (
    <li className="safety-review-item">
      <div className="safety-review-item-head">
        <strong>
          {line.type} × {line.quantity}
        </strong>
        <p className="safety-review-when">{formatBookingTimes(line.startsAt, line.endsAt)}</p>
      </div>
      {line.technicalRequirements && <p>Technical requirements: {line.technicalRequirements}</p>}
      {line.supportNotes && <p>Support notes: {line.supportNotes}</p>}
    </li>
  )
}
