import { useState, type FormEvent } from 'react'
import StatusBadge from '../components/StatusBadge'
import { createEvent } from '../eventsStore'
import { navigate } from '../router'
import type { Session } from '../api'

type NewEventPageProps = {
  session: Session
}

/**
 * US4.2: creating an event always lands in Draft. The form says so before you
 * submit it, so the starting status is never a surprise.
 */
export default function NewEventPage({ session }: NewEventPageProps) {
  const [draft, setDraft] = useState({
    title: '',
    description: '',
    startsAt: '',
    location: '',
  })
  const [titleError, setTitleError] = useState('')
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  if (session.role !== 'Organiser') {
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')

    if (!draft.title.trim()) {
      setTitleError('Give the event a title.')
      return
    }
    setTitleError('')

    setBusy(true)
    try {
      const created = await createEvent(draft, { id: session.id, name: session.name })
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
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                aria-invalid={Boolean(titleError)}
                aria-describedby={titleError ? 'title-error' : undefined}
                disabled={busy}
              />
              {titleError && (
                <span className="field-error" id="title-error">
                  {titleError}
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="startsAt">Starts</label>
              <input
                id="startsAt"
                type="datetime-local"
                value={draft.startsAt}
                onChange={(e) => setDraft({ ...draft, startsAt: e.target.value })}
                disabled={busy}
              />
              <span className="field-hint">You can fill this in later while it is a Draft.</span>
            </div>

            <div className="field">
              <label htmlFor="location">Location</label>
              <input
                id="location"
                value={draft.location}
                onChange={(e) => setDraft({ ...draft, location: e.target.value })}
                disabled={busy}
              />
            </div>

            <div className="field">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
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
