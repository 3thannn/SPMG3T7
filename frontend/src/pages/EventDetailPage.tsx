import { useEffect, useState } from 'react'
import './EventDetailPage.css'
import StatusBadge from '../components/StatusBadge'
import StatusTimeline from '../components/StatusTimeline'
import {
  EventRuleError,
  getEvent,
  saveEvent,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import { navigate } from '../router'
import { canViewStatus, checkSubmit, formatTimestamp, submitRefusalMessage } from '../status'
import type { Session } from '../api'

type EventDetailPageProps = {
  eventId: string
  session: Session
}

type Loading = { state: 'loading' }
type Loaded = { state: 'loaded'; event: EventRecord }
type Missing = { state: 'missing' }
type Forbidden = { state: 'forbidden' }
type PageState = Loading | Loaded | Missing | Forbidden

export default function EventDetailPage({ eventId, session }: EventDetailPageProps) {
  const [page, setPage] = useState<PageState>({ state: 'loading' })
  const [draft, setDraft] = useState({ title: '', description: '', startsAt: '', location: '' })
  const [banner, setBanner] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getEvent(eventId).then((event) => {
      if (cancelled) return
      if (!event) {
        setPage({ state: 'missing' })
        return
      }
      // US4.1: Venue Staff, Technical Support and Attendees have no status
      // visibility in Sprint 1, so they get an explicit refusal, not an empty page.
      if (!canViewStatus(session.role, session.id, event)) {
        setPage({ state: 'forbidden' })
        return
      }
      setPage({ state: 'loaded', event })
      setDraft({
        title: event.title,
        description: event.description,
        startsAt: event.startsAt,
        location: event.location,
      })
    })
    return () => {
      cancelled = true
    }
  }, [eventId, session.id, session.role])

  if (page.state === 'loading') {
    return (
      <div className="page shell">
        <p className="muted">Loading event…</p>
      </div>
    )
  }

  if (page.state === 'missing') {
    return (
      <div className="page shell">
        <div className="card empty">
          <h3>Event not found</h3>
          <p>It may have been removed, or the link is wrong.</p>
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

  if (page.state === 'forbidden') {
    return (
      <div className="page shell">
        <div className="card empty">
          <h3>Not available for your role</h3>
          <p>
            Event status is visible to the owning Organiser and to Coordinators in Sprint 1.
            Venue Staff, Technical Support and Attendee access arrives with their own features.
          </p>
        </div>
      </div>
    )
  }

  const { event } = page
  const isOwner = event.organiserId === session.id
  const submitCheck = checkSubmit(event, session.id)
  const editable = isOwner && event.status === 'Draft'
  const dirty =
    draft.title !== event.title ||
    draft.description !== event.description ||
    draft.startsAt !== event.startsAt ||
    draft.location !== event.location

  async function handleSave() {
    setBusy(true)
    setBanner(null)
    try {
      // US4.2: a save edits content and leaves a Draft as a Draft.
      const updated = await saveEvent(event.id, draft, { id: session.id, name: session.name })
      setPage({ state: 'loaded', event: updated })
      setBanner({ kind: 'ok', text: `Saved. Status is still ${updated.status}.` })
    } catch (error) {
      setBanner({
        kind: 'error',
        text: error instanceof EventRuleError ? error.message : 'Could not save the event.',
      })
    } finally {
      setBusy(false)
    }
  }

  async function handleSubmit() {
    setBusy(true)
    setBanner(null)
    try {
      // US4.2: Draft -> Submitted, exactly once.
      const updated = await submitEvent(event.id, { id: session.id, name: session.name })
      setPage({ state: 'loaded', event: updated })
      setBanner({ kind: 'ok', text: 'Submitted. The status change has been recorded.' })
    } catch (error) {
      setBanner({
        kind: 'error',
        text: error instanceof EventRuleError ? error.message : 'Could not submit the event.',
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="shell">
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

        <header className="detail-head">
          <div className="detail-heading">
            <h1 className="page-title">{event.title}</h1>
            <p className="page-subtitle">
              Organiser: {event.organiserName} · Created {formatTimestamp(event.createdAt)}
            </p>
          </div>
          <StatusBadge status={event.status} size="lg" />
        </header>

        {banner && (
          <p
            className={banner.kind === 'ok' ? 'detail-banner' : 'form-error'}
            role={banner.kind === 'error' ? 'alert' : 'status'}
          >
            {banner.text}
          </p>
        )}

        <div className="detail-grid">
          <section className="card card-pad detail-main">
            <h2 className="detail-section-title">Details</h2>

            {editable ? (
              <div className="detail-form">
                <div className="field">
                  <label htmlFor="title">Title</label>
                  <input
                    id="title"
                    value={draft.title}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                    disabled={busy}
                  />
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
            ) : (
              <dl className="detail-readonly">
                <dt>Starts</dt>
                <dd>{event.startsAt ? formatTimestamp(event.startsAt) : 'Not set'}</dd>
                <dt>Location</dt>
                <dd>{event.location || 'Not set'}</dd>
                <dt>Description</dt>
                <dd>{event.description || 'No description.'}</dd>
              </dl>
            )}

            {isOwner && (
              <div className="detail-actions">
                {editable && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleSave}
                    disabled={busy || !dirty}
                  >
                    {busy ? 'Saving…' : 'Save draft'}
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleSubmit}
                  disabled={busy || !submitCheck.allowed}
                  title={submitCheck.allowed ? undefined : submitRefusalMessage(submitCheck.reason)}
                >
                  {busy ? 'Working…' : 'Submit event'}
                </button>
              </div>
            )}

            {isOwner && !submitCheck.allowed && (
              <p className="detail-note">{submitRefusalMessage(submitCheck.reason)}</p>
            )}

            {!isOwner && (
              <p className="detail-note">
                You are viewing this as {session.role}. Only the owning Organiser can edit or
                submit it.
              </p>
            )}
          </section>

          <aside className="card card-pad detail-side">
            <h2 className="detail-section-title">Status history</h2>
            <p className="detail-side-lede">Who changed it, and when.</p>
            <StatusTimeline history={event.history} />
          </aside>
        </div>
      </div>
    </div>
  )
}
