import { useEffect, useState } from 'react'
import './EventDetailPage.css'
import StatusBadge from '../components/StatusBadge'
import StatusTimeline from '../components/StatusTimeline'
import {
  EventRuleError,
  attendanceField,
  getEvent,
  parseAttendance,
  saveEvent,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import { navigate } from '../router'
import { canViewStatus, checkSubmit, formatTimestamp, submitRefusalMessage } from '../status'
import type { Session } from '../api'
import { can } from '../permissions'

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
  const [draft, setDraft] = useState({
    title: '',
    purpose: '',
    description: '',
    startsAt: '',
    expectedAttendance: '',
  })
  const [banner, setBanner] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getEvent(eventId, session).then((event) => {
      if (cancelled) return
      if (!event) {
        setPage({ state: 'missing' })
        return
      }
      // US4.1: an Organiser sees only the events they own, so someone else's
      // event is an explicit refusal rather than an empty page.
      if (!canViewStatus(session.role, session.id, event)) {
        setPage({ state: 'forbidden' })
        return
      }
      setPage({ state: 'loaded', event })
      setDraft({
        title: event.title,
        purpose: event.purpose,
        description: event.description,
        startsAt: event.startsAt,
        expectedAttendance: attendanceField(event.expectedAttendance),
      })
    })
    return () => {
      cancelled = true
    }
  }, [eventId, session])

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
            An event is visible to the Organiser who owns it and to Event Coordinators. This
            one belongs to another Organiser.
          </p>
        </div>
      </div>
    )
  }

  const { event } = page
  const isOwner = event.organiserId === session.id
  const canEdit = can(session, 'events:edit')
  const submitCheck = checkSubmit(event, session.id)
  // US5.2: Coordinators can edit submitted events (not drafts), owners can edit their own drafts
  const editable = (canEdit && event.status !== 'Draft') || (isOwner && event.status === 'Draft')
  const dirty =
    draft.title !== event.title ||
    draft.purpose !== event.purpose ||
    draft.description !== event.description ||
    draft.startsAt !== event.startsAt ||
    draft.expectedAttendance !== attendanceField(event.expectedAttendance)

  async function handleSave() {
    if (!draft.title.trim()) {
      setBanner({ kind: 'error', text: 'Give the event a title.' })
      return
    }
    if (!draft.startsAt.trim()) {
      setBanner({ kind: 'error', text: 'Give the event a date.' })
      return
    }
    const attendance = parseAttendance(draft.expectedAttendance)
    if (attendance === 'invalid') {
      setBanner({
        kind: 'error',
        text: 'Enter a whole number for expected attendance, or leave it blank.',
      })
      return
    }
    setBusy(true)
    setBanner(null)
    try {
      // US4.2: a save edits content and leaves a Draft as a Draft. Every
      // writable column goes with it, so a field left alone is written back
      // unchanged rather than being cleared by its absence.
      const updated = await saveEvent(
        event.id,
        {
          title: draft.title.trim(),
          purpose: draft.purpose.trim(),
          description: draft.description.trim(),
          startsAt: draft.startsAt.trim(),
          expectedAttendance: attendance,
        },
        session,
      )
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
      const updated = await submitEvent(event.id, session)
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
                  <label htmlFor="purpose">Purpose</label>
                  <input
                    id="purpose"
                    maxLength={500}
                    value={draft.purpose}
                    onChange={(e) => setDraft({ ...draft, purpose: e.target.value })}
                    disabled={busy}
                  />
                </div>
                <div className="field">
                  <label htmlFor="expectedAttendance">Expected attendance</label>
                  <input
                    id="expectedAttendance"
                    type="number"
                    min={0}
                    step={1}
                    inputMode="numeric"
                    value={draft.expectedAttendance}
                    onChange={(e) =>
                      setDraft({ ...draft, expectedAttendance: e.target.value })
                    }
                    disabled={busy}
                  />
                  <span className="field-hint">
                    Optional. Leave blank if you do not have an estimate yet.
                  </span>
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
                <dt>Purpose</dt>
                <dd>{event.purpose || 'Not stated.'}</dd>
                <dt>Expected attendance</dt>
                <dd>
                  {event.expectedAttendance === null
                    ? 'Not estimated.'
                    : `${event.expectedAttendance} people`}
                </dd>
                <dt>Description</dt>
                <dd>{event.description || 'No description.'}</dd>
              </dl>
            )}

            {(isOwner || canEdit) && (
              <div className="detail-actions">
                {editable && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleSave}
                    disabled={busy || !dirty}
                  >
                    {busy ? 'Saving…' : canEdit && !isOwner ? 'Save changes' : 'Save draft'}
                  </button>
                )}
                {isOwner && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={busy || !submitCheck.allowed}
                    title={submitCheck.allowed ? undefined : submitRefusalMessage(submitCheck.reason)}
                  >
                    {busy ? 'Working…' : 'Submit event'}
                  </button>
                )}
              </div>
            )}

            {isOwner && !submitCheck.allowed && (
              <p className="detail-note">{submitRefusalMessage(submitCheck.reason)}</p>
            )}

            {!isOwner && !canEdit && (
              <p className="detail-note">
                You are viewing this as {session.role}. Only the owning Organiser can edit or submit it.
              </p>
            )}

            {!isOwner && canEdit && (
              <p className="detail-note">
                You are editing this event as {session.role}. Changes are tracked and logged.
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
