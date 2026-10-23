import { useEffect, useState } from 'react'
import './MyRegistrationsPage.css'
import { displayEventTitle } from '../draftRules'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import {
  describePlacesLeft,
  listMyRegistrations,
  registerForEvent,
  withdrawRegistration,
  type MyRegistration,
} from '../registrationStore'
import { navigate } from '../router'
import { formatRecordedAt, formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

interface Props {
  session: Session
}

type Listing =
  | { state: 'loading' }
  | { state: 'loaded'; registrations: MyRegistration[] }
  | { state: 'error'; message: string }

function when(item: MyRegistration): string {
  if (!item.startsAt) return 'To be announced'
  return item.endsAt ? formatBookingTimes(item.startsAt, item.endsAt) : formatTimestamp(item.startsAt)
}

/** Why a Withdrawn registration offers no way back in. */
function noWayBack(item: MyRegistration): string {
  if (item.placesLeft === null) return 'This event is no longer taking registrations.'
  return 'No places are left to register again.'
}

/**
 * The Attendee's registrations — US20.2.
 *
 * AC1: each event they registered for, with its current date, time and venues
 * (read now, so a moved event shows where it moved to) and the registration's
 * status. AC2: withdraw before the event starts, which gives the place back;
 * it asks first. AC3: a withdrawn registration can be made again while the
 * event still has places, with the same name and email as before.
 */
export default function MyRegistrationsPage({ session }: Props) {
  const [listing, setListing] = useState<Listing>({ state: 'loading' })
  const [reloads, setReloads] = useState(0)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listMyRegistrations(session)
      .then((registrations) => {
        if (!cancelled) setListing({ state: 'loaded', registrations })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setListing({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load your registrations'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [session, reloads])

  async function act(item: MyRegistration, action: () => Promise<unknown>, done: string, doing: string) {
    setBusyId(item.id)
    setErrors((current) => ({ ...current, [item.id]: '' }))
    setNotice(null)
    try {
      await action()
      setConfirmingId(null)
      setNotice(done)
    } catch (error) {
      setErrors((current) => ({
        ...current,
        [item.id]:
          error instanceof EventRuleError ? error.message : unexpectedFailureMessage(error, doing),
      }))
    } finally {
      setBusyId(null)
      // Read again either way: the places, and what can be done, may have changed.
      setReloads((count) => count + 1)
    }
  }

  function withdraw(item: MyRegistration) {
    const title = displayEventTitle(item.title)
    return act(
      item,
      () => withdrawRegistration(item.id, session),
      `You have withdrawn from ${title}. Your place has gone back to the event.`,
      'withdraw from this event',
    )
  }

  function registerAgain(item: MyRegistration) {
    return act(
      item,
      () => registerForEvent(item.eventId, { name: item.name, email: item.email }, session),
      `You are registered again for ${displayEventTitle(item.title)}.`,
      'register for this event',
    )
  }

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">My Registrations</h1>
            <p className="page-subtitle">
              The events you registered for, with their latest details.
            </p>
          </div>
        </header>
        {notice && (
          <p className="mine-notice" role="status">
            {notice}
          </p>
        )}
        {renderListing()}
      </div>
    </div>
  )

  function renderListing() {
    if (listing.state === 'loading') return <p className="muted">Loading your registrations…</p>
    if (listing.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {listing.message}
        </p>
      )
    }
    if (listing.registrations.length === 0) {
      return (
        <div className="card empty">
          <h3>You have not registered for any events yet</h3>
          <p>
            Find one under{' '}
            <a
              href="#/attend"
              onClick={(clickEvent) => {
                clickEvent.preventDefault()
                navigate('/attend')
              }}
            >
              Upcoming Events
            </a>
            .
          </p>
        </div>
      )
    }
    return (
      <ul className="mine-list" aria-label="Your registrations">
        {listing.registrations.map((item) => (
          <li key={item.id} className="card mine-item">
            <div className="mine-head">
              <h2 className="mine-title">{displayEventTitle(item.title)}</h2>
              <span
                className={`mine-status ${item.status === 'Registered' ? 'is-registered' : 'is-withdrawn'}`}
              >
                {item.status}
              </span>
            </div>
            <dl className="mine-facts">
              <div>
                <dt>When</dt>
                <dd>{when(item)}</dd>
              </div>
              <div>
                <dt>Where</dt>
                <dd>{item.venues.length > 0 ? item.venues.join(', ') : 'Venue to be announced'}</dd>
              </div>
              <div>
                <dt>Registered as</dt>
                <dd>
                  {item.name} · {item.email}
                </dd>
              </div>
              <div>
                <dt>{item.status === 'Withdrawn' ? 'Withdrawn' : 'Registered'}</dt>
                <dd>
                  {formatRecordedAt(item.status === 'Withdrawn' ? item.withdrawnAt : item.registeredAt)}
                </dd>
              </div>
            </dl>
            {errors[item.id] && (
              <p className="form-error" role="alert">
                {errors[item.id]}
              </p>
            )}
            {renderAction(item)}
          </li>
        ))}
      </ul>
    )
  }

  function renderAction(item: MyRegistration) {
    const busy = busyId === item.id
    const title = displayEventTitle(item.title)
    if (item.status === 'Registered') {
      if (!item.canWithdraw) {
        return <p className="mine-note">Withdrawing has closed for this event.</p>
      }
      if (confirmingId === item.id) {
        return (
          <div className="mine-confirm" role="group" aria-label={`Withdraw from ${title}`}>
            <p className="mine-note">
              Withdraw from {title}? Your place goes back to the event, and you can register again
              only while places are left.
            </p>
            <div className="mine-actions">
              <button
                type="button"
                className="btn btn-danger-solid btn-sm"
                disabled={busy}
                onClick={() => withdraw(item)}
              >
                {busy ? 'Withdrawing…' : 'Confirm withdrawal'}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={() => setConfirmingId(null)}
              >
                Keep my place
              </button>
            </div>
          </div>
        )
      }
      return (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          aria-label={`Withdraw from ${title}`}
          onClick={() => {
            setConfirmingId(item.id)
            setNotice(null)
          }}
        >
          Withdraw…
        </button>
      )
    }
    if (item.canRegisterAgain) {
      return (
        <div className="mine-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            aria-label={`Register again for ${title}`}
            disabled={busy}
            onClick={() => registerAgain(item)}
          >
            {busy ? 'Registering…' : 'Register again'}
          </button>
          {item.placesLeft !== null && (
            <span className="mine-note">{describePlacesLeft(item.placesLeft)}</span>
          )}
        </div>
      )
    }
    return <p className="mine-note">{noWayBack(item)}</p>
  }
}
