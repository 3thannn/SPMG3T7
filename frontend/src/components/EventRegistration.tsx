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
/** Over, or not going ahead: nobody registers any more. */
const CLOSED: readonly EventStatus[] = ['Completed', 'Cancelled', 'Rejected']

/**
 * Whether Attendees can see the event on Upcoming Events, which needs two
 * things: registration turned on, and the event Confirmed. Turning it on early
 * is allowed, so "on" alone does not mean anyone can see it yet.
 */
type Visibility = 'visible' | 'full' | 'waiting' | 'off' | 'closed'

function visibilityOf(status: EventStatus, settings: RegistrationSettings): Visibility {
  if (CLOSED.includes(status)) return 'closed'
  if (!settings.open) return 'off'
  if (status !== 'Confirmed') return 'waiting'
  return settings.placesLeft === 0 ? 'full' : 'visible'
}

const VISIBILITY_LABELS: Record<Visibility, string> = {
  visible: 'Visible to Attendees',
  full: 'Visible to Attendees: full',
  waiting: 'Not visible to Attendees yet',
  off: 'Not open to Attendees',
  closed: 'Closed to Attendees',
}

/** The step the event still has to take to be Confirmed, from where it is now. */
function untilConfirmed(status: EventStatus): string {
  // US4.7: the Safety Officer's approval no longer confirms it; the Coordinator does.
  if (status === 'Pending Safety Check') {
    return (
      'It is Pending Safety Check. It is Confirmed once the Safety Officer signs it off ' +
      'and the Coordinator confirms it.'
    )
  }
  if (status === 'Approved' || status === 'Planning') {
    return (
      `It is ${status}. It is Confirmed after the Coordinator sends it for its safety check, ` +
      'the Safety Officer signs it off, and the Coordinator confirms it.'
    )
  }
  return `It is ${status}. It is Confirmed after it is approved and passes its safety check.`
}

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
                  <tr
                    key={person.id}
                    className={person.status === 'Registered' ? undefined : 'is-withdrawn'}
                  >
                    <td>{person.name}</td>
                    <td>{person.email}</td>
                    <td>{formatRecordedAt(person.registeredAt)}</td>
                    <td>
                      {person.status === 'Withdrawn'
                        ? `Withdrawn ${formatRecordedAt(person.withdrawnAt)}`
                        : person.status}
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

  // US20.1: the assigned Coordinator; D3: the owning Organiser as well.
  const manages =
    can(session, 'registration:manage') &&
    (event.coordinatorId === session.id || event.organiserId === session.id)
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
      const places = `${settings.capacity} ${settings.capacity === 1 ? 'place' : 'places'}`
      setSaved(
        !settings.open
          ? 'Saved. Registration is off.'
          : event.status === 'Confirmed'
            ? `Saved. Registration is on, for ${places}.`
            : `Saved. Registration is on, for ${places}. Attendees will see the event once it is Confirmed.`,
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
        {renderVisibility(settings)}
        {!manages && !CLOSED.includes(event.status) && (
          <p className="detail-note">
            Only the event’s assigned Coordinator can turn registration on or change the capacity.
          </p>
        )}
        {manages && !settable && ['Submitted', 'Under Review'].includes(event.status) && (
          <p className="detail-note">Registration can be opened once the event is approved.</p>
        )}
        {manages && settable && renderForm()}
        {seesPeople && <WhoRegistered key={saves} event={event} session={session} />}
      </>
    )
  }

  /**
   * Whether Attendees can see the event now, in words rather than colour alone,
   * and, when they cannot, which of the two things it needs is still missing.
   */
  function renderVisibility(settings: RegistrationSettings) {
    const visibility = visibilityOf(event.status, settings)
    const confirmed = event.status === 'Confirmed'
    return (
      <div className={`registration-visibility is-${visibility}`}>
        <p className="registration-visibility-label">{VISIBILITY_LABELS[visibility]}</p>
        <p className="registration-summary">{summarise(settings)}</p>
        {visibility === 'visible' && (
          <p className="registration-visibility-lede">
            Attendees can see this event on their Upcoming Events page and register for it.
          </p>
        )}
        {visibility === 'full' && (
          <p className="registration-visibility-lede">
            Attendees can see this event on their Upcoming Events page, but every place is taken.
          </p>
        )}
        {visibility === 'closed' && (
          <p className="registration-visibility-lede">
            This event is {event.status}, so Attendees can no longer register for it.
          </p>
        )}
        {(visibility === 'waiting' || visibility === 'off') && (
          <>
            <p className="registration-visibility-lede">
              Attendees see this event on their Upcoming Events page once both of these are done:
            </p>
            <ul className="registration-checklist">
              {checklistItem(settings.open, 'Registration is turned on.')}
              {checklistItem(
                confirmed,
                confirmed ? 'The event is Confirmed.' : `The event is Confirmed. ${untilConfirmed(event.status)}`,
              )}
            </ul>
          </>
        )}
      </div>
    )
  }

  function checklistItem(done: boolean, text: string) {
    return (
      <li className={done ? 'is-done' : undefined}>
        <span className="registration-check" aria-hidden="true">
          {done ? '✓' : '○'}
        </span>
        <span className="sr-only">{done ? 'Done: ' : 'Not yet: '}</span>
        {text}
      </li>
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
