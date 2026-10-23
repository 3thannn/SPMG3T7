import { useEffect, useState, type FormEvent } from 'react'
import './AttendPage.css'
import { displayEventTitle } from '../draftRules'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import {
  describePlacesLeft,
  listOpenEvents,
  REGISTRATION_FIELD_MAX,
  registerForEvent,
  validateRegistration,
  type OpenEvent,
  type RegistrationForm,
} from '../registrationStore'
import { navigate } from '../router'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

interface Props {
  session: Session
}

type Listing =
  | { state: 'loading' }
  | { state: 'loaded'; events: OpenEvent[] }
  | { state: 'error'; message: string }

function when(event: OpenEvent): string {
  if (!event.startsAt) return 'To be announced'
  return event.endsAt ? formatBookingTimes(event.startsAt, event.endsAt) : formatTimestamp(event.startsAt)
}

/**
 * The Attendee's landing page — US20.1.
 *
 * AC2: every Confirmed event taking registrations, soonest first, with its
 * name, when it runs, where, and how many places are left, and nothing of how
 * it was planned. AC3/AC4: register with a name and an email, which start as
 * the account's own; once per event, while places last. A refusal from the
 * server, such as the last place going to someone else first, is shown where
 * the Attendee is, and the list is read again so the places are current.
 */
export default function AttendPage({ session }: Props) {
  const [listing, setListing] = useState<Listing>({ state: 'loading' })
  const [registeringId, setRegisteringId] = useState<string | null>(null)
  const [form, setForm] = useState<RegistrationForm>({ name: session.name, email: session.email })
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  // Bumped after every registration attempt, to read the places again.
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    let cancelled = false
    listOpenEvents(session)
      .then((events) => {
        if (!cancelled) setListing({ state: 'loaded', events })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setListing({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the events open for registration'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [session, reloads])

  function startRegistering(eventId: string) {
    setRegisteringId(eventId)
    setForm({ name: session.name, email: session.email })
    setFormError(null)
    setNotice(null)
  }

  async function submit(submitEvent: FormEvent, event: OpenEvent) {
    submitEvent.preventDefault()
    const problem = validateRegistration(form)
    if (problem) {
      setFormError(problem)
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await registerForEvent(event.id, form, session)
      setRegisteringId(null)
      setNotice(`You are registered for ${displayEventTitle(event.title)}.`)
    } catch (error) {
      setFormError(
        error instanceof EventRuleError
          ? error.message
          : unexpectedFailureMessage(error, 'register for this event'),
      )
    } finally {
      setBusy(false)
      // Places may have changed either way: someone else may have taken the last one.
      setReloads((count) => count + 1)
    }
  }

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Upcoming Events</h1>
            <p className="page-subtitle">
              Confirmed events you can register for, soonest first.
            </p>
          </div>
        </header>
        {notice && (
          <p className="attend-notice" role="status">
            {notice}
          </p>
        )}
        {renderListing()}
      </div>
    </div>
  )

  function renderListing() {
    if (listing.state === 'loading') return <p className="muted">Loading events…</p>
    if (listing.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {listing.message}
        </p>
      )
    }
    if (listing.events.length === 0) {
      return (
        <div className="card empty">
          <h3>No events are open for registration</h3>
          <p>An event appears here once it is confirmed and its Coordinator opens registration.</p>
        </div>
      )
    }
    return (
      <ul className="attend-list" aria-label="Events open for registration">
        {listing.events.map((event) => (
          <li key={event.id} className="card attend-item">
            <h2 className="attend-title">{displayEventTitle(event.title)}</h2>
            <dl className="attend-facts">
              <div>
                <dt>When</dt>
                <dd>{when(event)}</dd>
              </div>
              <div>
                <dt>Where</dt>
                <dd>{event.venues.length > 0 ? event.venues.join(', ') : 'Venue to be announced'}</dd>
              </div>
              <div>
                <dt>Places</dt>
                <dd>{describePlacesLeft(event.placesLeft)}</dd>
              </div>
            </dl>
            {renderAction(event)}
          </li>
        ))}
      </ul>
    )
  }

  function renderAction(event: OpenEvent) {
    if (event.registered) {
      return (
        <p className="attend-registered">
          You are registered for this event. To withdraw, go to{' '}
          <a
            href="#/my-registrations"
            onClick={(clickEvent) => {
              clickEvent.preventDefault()
              navigate('/my-registrations')
            }}
          >
            My Registrations
          </a>
          .
        </p>
      )
    }
    if (registeringId === event.id) return renderForm(event)
    if (event.placesLeft <= 0) {
      return <p className="attend-full">No places are left.</p>
    }
    return (
      <button
        type="button"
        className="btn btn-primary btn-sm"
        aria-label={`Register for ${displayEventTitle(event.title)}`}
        onClick={() => startRegistering(event.id)}
      >
        Register
      </button>
    )
  }

  function renderForm(event: OpenEvent) {
    const nameId = `attend-name-${event.id}`
    const emailId = `attend-email-${event.id}`
    return (
      <form className="attend-form" onSubmit={(submitEvent) => submit(submitEvent, event)} noValidate>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <fieldset className="attend-fields" disabled={busy}>
          <div className="field">
            <label htmlFor={nameId}>Name</label>
            <input
              id={nameId}
              autoComplete="name"
              maxLength={REGISTRATION_FIELD_MAX}
              value={form.name}
              onChange={(changeEvent) => setForm({ ...form, name: changeEvent.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor={emailId}>Email</label>
            <input
              id={emailId}
              type="email"
              autoComplete="email"
              maxLength={REGISTRATION_FIELD_MAX}
              value={form.email}
              onChange={(changeEvent) => setForm({ ...form, email: changeEvent.target.value })}
            />
          </div>
        </fieldset>
        <div className="attend-actions">
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
            {busy ? 'Registering…' : 'Confirm registration'}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            onClick={() => setRegisteringId(null)}
          >
            Cancel
          </button>
        </div>
      </form>
    )
  }
}
