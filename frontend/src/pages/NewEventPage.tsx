import { useState } from 'react'
import EventNeedsFields from '../components/EventNeedsFields'
import StatusBadge from '../components/StatusBadge'
import { createEvent, EventRuleError, parseAttendance, submitEvent } from '../eventsStore'
import { DRAFT_CONTENT_ERROR, hasDraftContent } from '../draftRules'
import { missingNeeds, NO_NEEDS, type EventNeeds } from '../eventNeeds'
import { navigate } from '../router'
import type { Session } from '../api'

type NewEventPageProps = {
  session: Session
}

/**
 * The fields are the writable columns of the `events` table. A draft only
 * needs meaningful content in one of them; submitting still requires the
 * complete event details.
 *
 * US2.1 (reopened in Sprint 3): the customer clarified that submitting needs
 * every one of name, description, purpose, date, start/end time, expected
 * attendance, venue requirements, preferred layout, accessibility needs,
 * equipment needs and registration needs. A need that does not apply is
 * answered "None / Not required". Drafts still save without these checks.
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
  endsAt: string
  expectedAttendance: string
} & EventNeeds

const EMPTY: DraftFields = {
  title: '',
  purpose: '',
  description: '',
  startsAt: '',
  endsAt: '',
  expectedAttendance: '',
  ...NO_NEEDS,
}

/** Shown above the form when Submit finds something to fix, which may be off-screen. */
export const SUBMIT_BLOCKED =
  'Some required details are missing or invalid. Fix the highlighted fields to submit.'

type FieldErrors = Partial<Record<keyof DraftFields, string>>

/** Everything the fields say is wrong, so the user sees it in one pass. */
function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function validate(fields: DraftFields, requireSubmit: boolean): FieldErrors {
  const errors: FieldErrors = {}
  if (requireSubmit && !fields.title.trim()) errors.title = 'Give the event a title.'
  else if (fields.title.length > TITLE_MAX) {
    errors.title = `Keep the title to ${TITLE_MAX} characters or fewer.`
  }
  if (fields.purpose.length > PURPOSE_MAX) {
    errors.purpose = `Keep the purpose to ${PURPOSE_MAX} characters or fewer.`
  }
  if (requireSubmit && !fields.startsAt.trim()) errors.startsAt = 'Give the event a date.'
  else if (requireSubmit && fields.startsAt.slice(0, 10) < todayIso()) {
    errors.startsAt = 'The start date cannot be in the past.'
  }
  if (requireSubmit && !fields.purpose.trim()) errors.purpose = 'Give the event a purpose.'
  const attendance = parseAttendance(fields.expectedAttendance)
  if (requireSubmit && !fields.expectedAttendance.trim()) {
    errors.expectedAttendance = 'Give the expected attendance.'
  } else if (requireSubmit && attendance !== 'invalid' && (attendance ?? 0) < 1) {
    errors.expectedAttendance = 'Expected attendance must be at least 1.'
  }
  if (requireSubmit && !fields.endsAt.trim()) errors.endsAt = 'Give the event an end date.'
  if (fields.endsAt.trim() && fields.startsAt.trim() && fields.endsAt <= fields.startsAt) {
    errors.endsAt = 'The end date must be after the start date.'
  }
  if (attendance === 'invalid') {
    errors.expectedAttendance = 'Enter a whole number of people, or leave it blank.'
  }
  if (requireSubmit) {
    if (!fields.description.trim()) errors.description = 'Give the event a description.'
    Object.assign(errors, missingNeeds(fields))
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

  async function handleAction(action: 'draft' | 'submit') {
    setFormError('')

    if (action === 'draft' && !hasDraftContent(fields)) {
      setErrors({})
      setFormError(DRAFT_CONTENT_ERROR)
      return
    }

    const found = validate(fields, action === 'submit')
    setErrors(found)
    if (Object.values(found).some(Boolean)) {
      if (action === 'submit') setFormError(SUBMIT_BLOCKED)
      return
    }

    const attendance = parseAttendance(fields.expectedAttendance)
    setBusy(true)
    try {
      const created = await createEvent(
        {
          title: action === 'draft' ? fields.title : fields.title.trim(),
          purpose: action === 'draft' ? fields.purpose : fields.purpose.trim(),
          description: action === 'draft' ? fields.description : fields.description.trim(),
          startsAt: action === 'draft' ? fields.startsAt : fields.startsAt.trim(),
          endsAt: action === 'draft' ? fields.endsAt || null : fields.endsAt.trim() || null,
          expectedAttendance: attendance === 'invalid' ? null : attendance,
          venueRequirements: fields.venueRequirements,
          preferredLayout: fields.preferredLayout,
          accessibilityNeeds: fields.accessibilityNeeds,
          equipmentNeeds:
            action === 'draft' ? fields.equipmentNeeds : fields.equipmentNeeds.trim(),
          registrationNeeds:
            action === 'draft' ? fields.registrationNeeds : fields.registrationNeeds.trim(),
        },
        session,
      )
      if (action === 'submit') await submitEvent(created.id, session)
      navigate(`/events/${created.id}`)
    } catch (error) {
      setFormError(
        error instanceof EventRuleError
          ? error.message
          : action === 'submit'
            ? 'Could not submit the event. Try again.'
            : 'Could not save the event. Try again.',
      )
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

        <form
          className="card card-pad"
          onSubmit={(event) => {
            event.preventDefault()
            void handleAction('draft')
          }}
          noValidate
        >
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
                min={`${todayIso()}T00:00`}
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
              <label htmlFor="endsAt">Ends</label>
              <input
                id="endsAt"
                type="datetime-local"
                value={fields.endsAt}
                onChange={(e) => set('endsAt', e.target.value)}
                aria-invalid={Boolean(errors.endsAt)}
                aria-describedby={errors.endsAt ? 'endsAt-error' : 'endsAt-hint'}
                disabled={busy}
              />
              {errors.endsAt ? (
                <span className="field-error" id="endsAt-error">
                  {errors.endsAt}
                </span>
              ) : (
                <span className="field-hint" id="endsAt-hint">
                  Required when submitting. Optional for a saved draft.
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
                  Required when submitting. One line on why the event is being held.
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="expectedAttendance">Expected attendance</label>
              <input
                id="expectedAttendance"
                type="number"
                min={1}
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
                  Required when submitting. Enter at least 1 person.
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={fields.description}
                onChange={(e) => set('description', e.target.value)}
                aria-invalid={Boolean(errors.description)}
                aria-describedby={errors.description ? 'description-error' : 'description-hint'}
                disabled={busy}
              />
              {errors.description ? (
                <span className="field-error" id="description-error">
                  {errors.description}
                </span>
              ) : (
                <span className="field-hint" id="description-hint">
                  Required when submitting. What happens at the event.
                </span>
              )}
            </div>

            <EventNeedsFields needs={fields} onChange={set} errors={errors} disabled={busy} />
          </div>

          <div className="detail-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void handleAction('draft')}
              disabled={busy}
            >
              Save as draft
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleAction('submit')}
              disabled={busy}
            >
              Submit
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
