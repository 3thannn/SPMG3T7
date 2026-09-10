import { useState, type FormEvent } from 'react'
import StatusBadge from '../components/StatusBadge'
import { createEvent, parseAttendance } from '../eventsStore'
import { navigate } from '../router'
import type { Session } from '../api'

type NewEventPageProps = {
  session: Session
}

/**
 * The fields are the writable columns of the `events` table: name, purpose,
 * description, proposed_date and expected_attendance. Title and date are the
 * NOT NULL ones and are asked for as required; the rest are nullable, so the
 * form lets them be left blank rather than inventing a value to store.
 *
 * The lengths mirror VARCHAR(255) on `name` and VARCHAR(500) on `purpose`, so
 * an over-long entry is caught in the field rather than by a rejected write.
 */
const TITLE_MAX = 255
const PURPOSE_MAX = 500

/** Form state is all strings — attendance becomes a number on submit. */
type DraftFields = {
  title: string
  purpose: string
  description: string
  startsAt: string
  expectedAttendance: string
}

const EMPTY: DraftFields = {
  title: '',
  purpose: '',
  description: '',
  startsAt: '',
  expectedAttendance: '',
}

type FieldErrors = Partial<Record<keyof DraftFields, string>>

/** Everything the fields say is wrong, so the user sees it in one pass. */
function validate(fields: DraftFields): FieldErrors {
  const errors: FieldErrors = {}
  const title = fields.title.trim()
  if (!title) errors.title = 'Give the event a title.'
  else if (title.length > TITLE_MAX) {
    errors.title = `Keep the title to ${TITLE_MAX} characters or fewer.`
  }
  if (fields.purpose.trim().length > PURPOSE_MAX) {
    errors.purpose = `Keep the purpose to ${PURPOSE_MAX} characters or fewer.`
  }
  // Required by the database: events.proposed_date is NOT NULL, so there is no
  // such thing as a stored draft without a date. Checking here means the user
  // is told in the field rather than by a rejected request.
  if (!fields.startsAt.trim()) errors.startsAt = 'Give the event a date.'
  if (parseAttendance(fields.expectedAttendance) === 'invalid') {
    errors.expectedAttendance = 'Enter a whole number of people, or leave it blank.'
  }
  return errors
}

/**
 * US4.2: creating an event always lands in Draft. The form says so before you
 * submit it, so the starting status is never a surprise.
 */
export default function NewEventPage({ session }: NewEventPageProps) {
  const [fields, setFields] = useState<DraftFields>(EMPTY)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  if (session.role !== 'Event Organiser') {
    return (
      <div className="page shell">
        <div className="card empty">
          <h3>Only Organisers create events</h3>
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

  function set<K extends keyof DraftFields>(key: K, value: string) {
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
    if (Object.values(found).some(Boolean)) return

    const attendance = parseAttendance(fields.expectedAttendance)
    setBusy(true)
    try {
      const created = await createEvent(
        {
          title: fields.title.trim(),
          purpose: fields.purpose.trim(),
          description: fields.description.trim(),
          startsAt: fields.startsAt.trim(),
          expectedAttendance: attendance === 'invalid' ? null : attendance,
        },
        session,
      )
      navigate(`/events/${created.id}`)
    } catch {
      setFormError('Could not create the event. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="shell" style={{ maxWidth: '46rem' }}>
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
            <h1 className="page-title">New event</h1>
            <p className="page-subtitle">
              It will be created as <StatusBadge status="Draft" /> — you can submit it once
              you are ready.
            </p>
          </div>
        </header>

        <form className="card card-pad" onSubmit={handleSubmit} noValidate>
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}

          <div className="detail-form">
            <div className="field">
              <label htmlFor="title">Title</label>
              <input
                id="title"
                maxLength={TITLE_MAX}
                value={fields.title}
                onChange={(e) => set('title', e.target.value)}
                aria-invalid={Boolean(errors.title)}
                aria-describedby={errors.title ? 'title-error' : undefined}
                disabled={busy}
              />
              {errors.title && (
                <span className="field-error" id="title-error">
                  {errors.title}
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="startsAt">Starts</label>
              <input
                id="startsAt"
                type="datetime-local"
                value={fields.startsAt}
                onChange={(e) => set('startsAt', e.target.value)}
                aria-invalid={Boolean(errors.startsAt)}
                aria-describedby={errors.startsAt ? 'startsAt-error' : undefined}
                disabled={busy}
              />
              {errors.startsAt && (
                <span className="field-error" id="startsAt-error">
                  {errors.startsAt}
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="purpose">Purpose</label>
              <input
                id="purpose"
                maxLength={PURPOSE_MAX}
                value={fields.purpose}
                onChange={(e) => set('purpose', e.target.value)}
                aria-invalid={Boolean(errors.purpose)}
                aria-describedby={errors.purpose ? 'purpose-error' : 'purpose-hint'}
                disabled={busy}
              />
              {errors.purpose ? (
                <span className="field-error" id="purpose-error">
                  {errors.purpose}
                </span>
              ) : (
                <span className="field-hint" id="purpose-hint">
                  Optional. One line on why the event is being held.
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="expectedAttendance">Expected attendance</label>
              <input
                id="expectedAttendance"
                type="number"
                min={0}
                step={1}
                inputMode="numeric"
                value={fields.expectedAttendance}
                onChange={(e) => set('expectedAttendance', e.target.value)}
                aria-invalid={Boolean(errors.expectedAttendance)}
                aria-describedby={
                  errors.expectedAttendance
                    ? 'expectedAttendance-error'
                    : 'expectedAttendance-hint'
                }
                disabled={busy}
              />
              {errors.expectedAttendance ? (
                <span className="field-error" id="expectedAttendance-error">
                  {errors.expectedAttendance}
                </span>
              ) : (
                <span className="field-hint" id="expectedAttendance-hint">
                  Optional. Leave blank if you do not have an estimate yet.
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={fields.description}
                onChange={(e) => set('description', e.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="detail-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Creating…' : 'Create draft'}
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
