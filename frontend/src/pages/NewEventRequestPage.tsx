import { useState, type FormEvent } from 'react'
import './NewEventRequestPage.css'
import StatusBadge from '../components/StatusBadge'
import {
  createEventRequest,
  DESCRIPTION_MAX,
  EMPTY_REQUEST,
  EventRequestError,
  isComplete,
  NAME_MAX,
  PURPOSE_MAX,
  todayIso,
  validate,
  type RequestErrors,
  type RequestFields,
} from '../eventRequests'
import { navigate } from '../router'
import type { Session } from '../api'

type NewEventRequestPageProps = {
  session: Session
}

/**
 * The line under an input: its complaint if it has one, otherwise its hint.
 *
 * Declared at module level rather than inside the page. A component defined
 * during a render is a new type on every render, so React unmounts and remounts
 * the node — which drops focus while someone is still typing in the field above.
 */
function FieldMessage({
  field,
  errors,
  hint,
}: {
  field: keyof RequestFields
  errors: RequestErrors
  hint?: string
}) {
  if (errors[field]) {
    return (
      <span className="field-error" id={`${field}-error`}>
        {errors[field]}
      </span>
    )
  }
  if (!hint) return null
  return (
    <span className="field-hint" id={`${field}-hint`}>
      {hint}
    </span>
  )
}

/**
 * Event Request Creation: one form, one submit, and the event is with the
 * Coordinators.
 *
 * This is not the US4.2 "New event" page and does not replace it. That one
 * creates a Draft to come back to; this one is for a proposal already worked
 * out, and says so before you submit — an Organiser should never have to guess
 * which of the two they are looking at, so the heading, the badge and the
 * button all say Submitted.
 *
 * Five fields are required and the rest are not, which the labels state rather
 * than leaving to a red outline after the fact. Every field is plain text, a
 * date or a number: Venue and Equipment lookups arrive in Sprint 2 and 3.
 */
export default function NewEventRequestPage({ session }: NewEventRequestPageProps) {
  const [fields, setFields] = useState<RequestFields>(EMPTY_REQUEST)
  const [errors, setErrors] = useState<RequestErrors>({})
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  if (session.role !== 'Event Organiser') {
    return (
      <div className="page shell">
        <div className="card empty">
          <h3>Only Organisers raise event requests</h3>
          <p>You are signed in as {session.role}.</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate('/events')}
            style={{ marginTop: '1.25rem' }}
          >
            Back to events
          </button>
        </div>
      </div>
    )
  }

  function set<K extends keyof RequestFields>(key: K, value: string) {
    setFields((current) => ({ ...current, [key]: value }))
    // Clear this field's complaint as soon as it is being addressed; the rest
    // stay until the next submit re-checks them.
    setErrors((current) => ({ ...current, [key]: undefined }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')

    const found = validate(fields)
    setErrors(found)
    if (!isComplete(found)) return

    setBusy(true)
    try {
      const created = await createEventRequest(fields, session)
      navigate(`/events/${created.id}`)
    } catch (error) {
      // The server's own sentence when it has one, so a rule this form does not
      // know about still reads as an explanation rather than as "try again".
      setFormError(
        error instanceof EventRequestError
          ? error.message
          : 'Could not submit the request. Try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  /** The bits every field repeats: the error id wiring and the disabled state. */
  function fieldProps(key: keyof RequestFields, hint?: string) {
    return {
      id: key,
      disabled: busy,
      'aria-invalid': Boolean(errors[key]),
      'aria-describedby': errors[key] ? `${key}-error` : hint ? `${key}-hint` : undefined,
      value: fields[key],
    }
  }

  return (
    <div className="page">
      <div className="shell request-shell">
        <a
          className="detail-back"
          href="#/events"
          onClick={(clickEvent) => {
            clickEvent.preventDefault()
            navigate('/events')
          }}
        >
          ← Events
        </a>

        <header className="page-head">
          <div>
            <h1 className="page-title">New event request</h1>
            <p className="page-subtitle">
              Fill this in and it goes straight to the Coordinators as{' '}
              <StatusBadge status="Submitted" /> — there is no draft to come back to.
            </p>
          </div>
        </header>

        <form className="card card-pad" onSubmit={handleSubmit} noValidate>
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}

          <p className="request-required-note">
            Everything except the description is needed before this can be submitted.
          </p>

          <div className="detail-form">
            <div className="field">
              <label htmlFor="name">Event name</label>
              <input {...fieldProps('name')} maxLength={NAME_MAX} onChange={(e) => set('name', e.target.value)} />
              <FieldMessage field="name" errors={errors} />
            </div>

            <div className="field">
              <label htmlFor="purpose">Purpose</label>
              <input
                {...fieldProps('purpose', 'Why the event is being held.')}
                maxLength={PURPOSE_MAX}
                onChange={(e) => set('purpose', e.target.value)}
              />
              <FieldMessage field="purpose" errors={errors} hint="Why the event is being held." />
            </div>

            <div className="field">
              <label htmlFor="proposedDate">Proposed date</label>
              <input
                {...fieldProps('proposedDate')}
                type="date"
                // The picker greys out the past as well, so the rule is visible
                // before it is broken. It is not the check — a typed date and a
                // hand-written request both go past it — which is why `validate`
                // and the server both re-test it.
                min={todayIso()}
                onChange={(e) => set('proposedDate', e.target.value)}
              />
              <FieldMessage field="proposedDate" errors={errors} />
            </div>

            <div className="request-times">
              <div className="field">
                <label htmlFor="startTime">Start time</label>
                <input
                  {...fieldProps('startTime')}
                  type="time"
                  onChange={(e) => set('startTime', e.target.value)}
                />
                <FieldMessage field="startTime" errors={errors} />
              </div>

              <div className="field">
                <label htmlFor="endTime">End time</label>
                <input
                  {...fieldProps('endTime')}
                  type="time"
                  onChange={(e) => set('endTime', e.target.value)}
                />
                <FieldMessage field="endTime" errors={errors} hint="Must be later the same day." />
              </div>
            </div>

            <div className="field">
              <label htmlFor="expectedAttendance">Expected attendance</label>
              <input
                {...fieldProps('expectedAttendance', 'How many people you expect.')}
                type="number"
                min={1}
                step={1}
                inputMode="numeric"
                onChange={(e) => set('expectedAttendance', e.target.value)}
              />
              <FieldMessage
                field="expectedAttendance"
                errors={errors}
                hint="How many people you expect."
              />
            </div>

            <div className="field">
              <label htmlFor="description">Description (optional)</label>
              <textarea
                {...fieldProps('description', 'Anything the Coordinators should know.')}
                maxLength={DESCRIPTION_MAX}
                onChange={(e) => set('description', e.target.value)}
              />
              <FieldMessage
                field="description"
                errors={errors}
                hint="Anything the Coordinators should know."
              />
            </div>
          </div>

          <div className="detail-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Submitting…' : 'Submit request'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate('/events')}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
