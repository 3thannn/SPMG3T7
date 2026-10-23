import { useEffect, useState, type FormEvent } from 'react'
import './EventRegistration.css'
import { EventRuleError, type EventRecord } from '../eventsStore'
import {
  getRegistrationSettings,
  parseCapacity,
  REGISTRATION_CAPACITY_MAX,
  saveRegistrationSettings,
  type RegistrationSettings,
} from '../registrationStore'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'
import type { EventStatus } from '../status'

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

/**
 * US20.1 AC1: registration on the event page.
 *
 * The Coordinator the event is assigned to turns it on or off and sets the
 * capacity, which starts from the expected attendance. Everyone else who can
 * open the event sees where it stands. Attendees see the event only once it is
 * Confirmed, so it can be opened ahead of that.
 */
export default function EventRegistration({ event, session }: Props) {
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' })
  const [open, setOpen] = useState(false)
  const [capacityText, setCapacityText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const manages = can(session, 'registration:manage') && event.coordinatorId === session.id
  const settable = SETTABLE.includes(event.status)

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
