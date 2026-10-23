import { useEffect, useState, type FormEvent } from 'react'
import './EventRegistration.css'
import { EventRuleError, type EventRecord } from '../eventsStore'
import {
  getRegistrationSettings,
  listEventRegistrations,
  parseCapacity,
  REGISTRATION_CAPACITY_MAX,
  saveRegistrationSettings,
  type EventRegistrations,
  type RegistrationSettings,
} from '../registrationStore'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'
import { formatRecordedAt, type EventStatus } from '../status'

type Props = {
  event: EventRecord
  session: Session
}

type Loaded =
  | { state: 'loading' }
  | { state: 'loaded'; settings: RegistrationSettings }
  | { state: 'error'; message: string }

/** From approval until the event is over, as the server allows. */
const SETTABLE: readonly EventStatus[] = ['Approved', 'Planning', 'Pending Safety Check', 'Confirmed']

/** "Registration is on: 3 of 50 places taken." */
function summarise(settings: RegistrationSettings): string {
  if (!settings.open) {
    return settings.registered > 0
      ? `Registration is off. ${settings.registered} registered before it was turned off.`
      : 'Registration is off.'
  }
  const taken = `${settings.registered} of ${settings.capacity} ${settings.capacity === 1 ? 'place' : 'places'} taken`
  return settings.placesLeft === 0
    ? `Registration is on: ${taken}. The event is full.`
    : `Registration is on: ${taken}.`
}

/** What the capacity box starts at: the stored capacity, or the expected attendance. */
function startingCapacity(settings: RegistrationSettings): string {
  const value = settings.capacity ?? settings.defaultCapacity
  return value === null ? '' : String(value)
}

type People =
  | { state: 'loading' }
  | { state: 'loaded'; list: EventRegistrations }
  | { state: 'error'; message: string }

/** "3 of 50 registered", or "3 registered" before a capacity is set. */
function registeredCount(list: EventRegistrations): string {
  return list.capacity === null
    ? `${list.registered} registered`
    : `${list.registered} of ${list.capacity} registered`
}

/**
 * US20.3: who registered — name, email, when, and status — with the count
 * against the capacity. Only for the owning Organiser and the assigned
 * Coordinator; the server refuses everyone else.
 */
function WhoRegistered({ event, session }: Props) {
  const [people, setPeople] = useState<People>({ state: 'loading' })

  useEffect(() => {
    let cancelled = false
    listEventRegistrations(event.id, session)
      .then((list) => {
        if (!cancelled) setPeople({ state: 'loaded', list })
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setPeople({
            state: 'error',
            message: unexpectedFailureMessage(failure, 'load who has registered'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  return (
    <section className="registrants" aria-labelledby="registrants-title">
      <h3 className="registrants-title" id="registrants-title">
        Who has registered
      </h3>
      {renderPeople()}
    </section>
  )

  function renderPeople() {
    if (people.state === 'loading') return <p className="muted">Loading who has registered…</p>
    if (people.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {people.message}
        </p>
      )
    }
    const { list } = people
    return (
      <>
        <p className="registrants-count">{registeredCount(list)}</p>
        {list.registrations.length === 0 ? (
          <p className="muted">Nobody has registered yet.</p>
        ) : (
          <div className="registrants-scroll">
            <table className="registrants-table">
              <caption className="sr-only">People registered for this event</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Registered</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {list.registrations.map((person) => (
                  <tr key={person.id} className={person.status === 'Withdrawn' ? 'is-withdrawn' : undefined}>
                    <td>{person.name}</td>
                    <td>{person.email}</td>
                    <td>{formatRecordedAt(person.registeredAt)}</td>
                    <td>
                      {person.status === 'Withdrawn'
                        ? `Withdrawn ${formatRecordedAt(person.withdrawnAt)}`
                        : 'Registered'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    )
  }
}

/**
 * US20.1 AC1: registration on the event page.
 *
 * The Coordinator the event is assigned to turns it on or off and sets the
 * capacity, which starts from the expected attendance. Everyone else who can
 * open the event sees where it stands. Attendees see the event only once it is
 * Confirmed, so it can be opened ahead of that. US20.3 adds who registered,
 * for the owning Organiser and the assigned Coordinator.
 */
export default function EventRegistration({ event, session }: Props) {
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' })
  const [open, setOpen] = useState(false)
  const [capacityText, setCapacityText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  // Bumped on every save, so the list's count against the capacity is read again.
  const [saves, setSaves] = useState(0)

  const manages = can(session, 'registration:manage') && event.coordinatorId === session.id
  const settable = SETTABLE.includes(event.status)
  const seesPeople =
    can(session, 'registrations:read') &&
    (event.organiserId === session.id || event.coordinatorId === session.id)

  useEffect(() => {
    let cancelled = false
    getRegistrationSettings(event.id, session)
      .then((settings) => {
        if (cancelled) return
        setLoaded({ state: 'loaded', settings })
        setOpen(settings.open)
        setCapacityText(startingCapacity(settings))
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setLoaded({
            state: 'error',
            message: unexpectedFailureMessage(failure, 'load the registration settings'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  async function save(submitEvent: FormEvent) {
    submitEvent.preventDefault()
    setError(null)
    setSaved(null)
    const capacity = parseCapacity(capacityText)
    if (capacity === 'invalid') {
      setError('Give the capacity as a whole number of places, at least 1.')
      return
    }
    setSaving(true)
    try {
      const settings = await saveRegistrationSettings(event.id, { open, capacity }, session)
      setLoaded({ state: 'loaded', settings })
      setOpen(settings.open)
      setCapacityText(startingCapacity(settings))
      setSaves((count) => count + 1)
      setSaved(
        settings.open
          ? `Saved. Registration is on, for ${settings.capacity} ${settings.capacity === 1 ? 'place' : 'places'}.`
          : 'Saved. Registration is off.',
      )
    } catch (failure) {
      setError(
        failure instanceof EventRuleError
          ? failure.message
          : unexpectedFailureMessage(failure, 'save the registration settings'),
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card card-pad event-registration" aria-labelledby="event-registration-title">
      <h2 className="detail-section-title" id="event-registration-title">
        Registration
      </h2>
      {renderBody()}
    </section>
  )

  function renderBody() {
    if (loaded.state === 'loading') return <p className="muted">Loading registration…</p>
    if (loaded.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {loaded.message}
        </p>
      )
    }
    const { settings } = loaded
    return (
      <>
        <p className="registration-summary">{summarise(settings)}</p>
        {settings.open && event.status !== 'Confirmed' && (
          <p className="detail-note">Attendees will see this event once it is Confirmed.</p>
        )}
        {manages && !settable && ['Submitted', 'Under Review'].includes(event.status) && (
          <p className="detail-note">Registration can be opened once the event is approved.</p>
        )}
        {manages && settable && renderForm()}
        {seesPeople && <WhoRegistered key={saves} event={event} session={session} />}
      </>
    )
  }

  function renderForm() {
    return (
      <form className="registration-form" onSubmit={save} noValidate>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {saved && (
          <p className="registration-saved" role="status">
            {saved}
          </p>
        )}
        <fieldset className="registration-fields" disabled={saving}>
          <label className="registration-toggle">
            <input
              type="checkbox"
              checked={open}
              onChange={(changeEvent) => setOpen(changeEvent.target.checked)}
            />
            <span>Open registration to Attendees</span>
          </label>
          <div className="field registration-capacity">
            <label htmlFor="registration-capacity">Capacity</label>
            <input
              id="registration-capacity"
              type="number"
              inputMode="numeric"
              min={1}
              max={REGISTRATION_CAPACITY_MAX}
              step={1}
              value={capacityText}
              aria-describedby="registration-capacity-hint"
              onChange={(changeEvent) => setCapacityText(changeEvent.target.value)}
            />
            <span className="field-hint" id="registration-capacity-hint">
              Places Attendees can take. Starts at the expected attendance.
            </span>
          </div>
        </fieldset>
        <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
          {saving ? 'Saving…' : 'Save registration'}
        </button>
      </form>
    )
  }
}
