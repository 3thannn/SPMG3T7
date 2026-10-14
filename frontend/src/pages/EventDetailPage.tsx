import { useEffect, useState } from 'react'
import './EventDetailPage.css'
import EventBookings from '../components/EventBookings'
import EventEquipment from '../components/EventEquipment'
import StatusBadge from '../components/StatusBadge'
import StatusTimeline from '../components/StatusTimeline'
import ProposedChanges from '../components/ProposedChanges'
import {
  EventRuleError,
  approveEvent,
  approveEventChange,
  completeEvent,
  attendanceField,
  getEvent,
  parseAttendance,
  rejectEvent,
  rejectEventChange,
  requestClarification,
  requestEventChange,
  saveEvent,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import {
  DRAFT_CONTENT_ERROR,
  displayEventTitle,
  hasDraftContent,
  submissionError,
} from '../draftRules'
import { navigate } from '../router'
import {
  canViewStatus,
  changeRequestRefusalMessage,
  checkChangeRequest,
  checkClarification,
  checkSubmit,
  clarificationRefusalMessage,
  formatTimestamp,
  submitRefusalMessage,
} from '../status'
import { unexpectedFailureMessage, type Session } from '../api'
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

function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** The edit form's fields, filled from an event. */
function draftFrom(event: EventRecord) {
  return {
    title: event.title,
    purpose: event.purpose,
    description: event.description,
    startsAt: event.startsAt,
    endsAt: event.endsAt ?? '',
    expectedAttendance: attendanceField(event.expectedAttendance),
  }
}

export default function EventDetailPage({ eventId, session }: EventDetailPageProps) {
  const [page, setPage] = useState<PageState>({ state: 'loading' })
  const [draft, setDraft] = useState({
    title: '',
    purpose: '',
    description: '',
    startsAt: '',
    endsAt: '',
    expectedAttendance: '',
  })
  const [banner, setBanner] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  //: US7.3. Kept apart from `draft` because asking a question is not an edit
  //: to the event, and a half-typed request must not read as unsaved changes.
  const [clarification, setClarification] = useState('')
  const [asking, setAsking] = useState(false)
  const [rejectionReason, setRejectionReason] = useState('')
  const [deciding, setDeciding] = useState<'approve' | 'reject' | null>(null)
  const [completing, setCompleting] = useState(false)
  const [nowMs, setNowMs] = useState<number | null>(null)
  //: US11.1. `proposing` opens the existing edit form on a submitted event; what
  //: is typed there is sent as a change request rather than saved.
  const [proposing, setProposing] = useState(false)
  const [changeNote, setChangeNote] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [changeRejection, setChangeRejection] = useState('')
  const [answering, setAnswering] = useState<'approve' | 'reject' | null>(null)

  useEffect(() => {
    let cancelled = false
    getEvent(eventId, session).then((event) => {
      if (cancelled) return
      if (!event) {
        setPage({ state: 'missing' })
        return
      }
      // The API enforces visibility. Keep the same check here so an invalid or
      // stale response still cannot render a private Draft.
      if (!canViewStatus(session.role, session.id, event)) {
        setPage({ state: 'forbidden' })
        return
      }
      setPage({ state: 'loaded', event })
      setDraft(draftFrom(event))
    })
    return () => {
      cancelled = true
    }
  }, [eventId, session])

  useEffect(() => {
    if (page.state !== 'loaded' || page.event.status !== 'Confirmed') return
    const updateClock = () => setNowMs(Date.now())
    updateClock()
    const timer = window.setInterval(updateClock, 1000)
    return () => window.clearInterval(timer)
  }, [page])


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
            Drafts are visible only to the Organiser who owns them. Event Coordinators can
            view an event after it has been submitted.
          </p>
        </div>
      </div>
    )
  }

  const { event } = page
  const isOwner = event.organiserId === session.id
  const canEdit = can(session, 'events:edit')
  const submitCheck = checkSubmit(event, session.id)
  // US8.1 enforces assignment when the API loads this event; the permission
  // determines whether this review UI belongs to the signed-in role.
  const mayReview = can(session, 'events:review')
  const clarificationCheck = checkClarification(event)
  // US11.1: a pending change request is answered before the event is decided.
  const changeRequested = event.changeRequested ?? false
  const pendingChanges = event.pendingChanges ?? []
  // Shown once nothing is waiting, so a fresh request is not overshadowed by
  // the answer to the one before it.
  const lastReview = changeRequested ? null : (event.lastChangeReview ?? null)
  const changeCheck = checkChangeRequest(event, session.id)
  const canDecide = mayReview && event.status === 'Under Review' && !changeRequested
  const canComplete = can(session, 'events:complete') &&
    event.coordinatorId === session.id && event.status === 'Confirmed'
  const eventEnded = Boolean(event.endsAt) && nowMs !== null &&
    nowMs > Date.parse(`${event.endsAt}+08:00`)
  const writePending =
    busy || asking || deciding !== null || requesting || answering !== null || completing
  // US5.2: Coordinators can edit submitted events (not drafts), owners can edit their own drafts.
  // US11.1: an owner can also open the form on a submitted event, to propose changes.
  const editable =
    (canEdit && event.status !== 'Draft') ||
    (isOwner && event.status === 'Draft') ||
    (isOwner && proposing)
  const dirty =
    draft.title !== event.title ||
    draft.purpose !== event.purpose ||
    draft.description !== event.description ||
    draft.startsAt !== event.startsAt ||
    draft.endsAt !== (event.endsAt ?? '') ||
    draft.expectedAttendance !== attendanceField(event.expectedAttendance)

  /** US7.3: attach the message and move the event to Under Review. */
  async function handleRequestClarification() {
    const message = clarification.trim()
    if (!message) {
      setBanner({ kind: 'error', text: 'Say what you need from the Organiser.' })
      return
    }
    setAsking(true)
    setBanner(null)
    try {
      const updated = await requestClarification(event.id, message, session)
      setPage({ state: 'loaded', event: updated })
      // Cleared only on success, so a refused request does not lose what was
      // typed and leave the Coordinator to write it again.
      setClarification('')
      setBanner({
        kind: 'ok',
        text: `Request sent. The event is now ${updated.status} and the Organiser can see your message.`,
      })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'send the request'),
      })
    } finally {
      setAsking(false)
    }
  }

  async function handleApprove() {
    setDeciding('approve')
    setBanner(null)
    try {
      const updated = await approveEvent(event.id, session)
      setPage({ state: 'loaded', event: updated })
      setBanner({ kind: 'ok', text: 'Approved. The status change has been recorded.' })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'approve the event'),
      })
    } finally {
      setDeciding(null)
    }
  }

  async function handleReject() {
    const reason = rejectionReason.trim()
    if (!reason) {
      setBanner({ kind: 'error', text: 'Give the Organiser a reason for rejecting this event.' })
      return
    }
    setDeciding('reject')
    setBanner(null)
    try {
      const updated = await rejectEvent(event.id, reason, session)
      setPage({ state: 'loaded', event: updated })
      setRejectionReason('')
      setBanner({ kind: 'ok', text: 'Rejected. The Organiser can see your reason.' })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'reject the event'),
      })
    } finally {
      setDeciding(null)
    }
  }

  async function handleComplete() {
    setCompleting(true)
    setBanner(null)
    try {
      const updated = await completeEvent(event.id, session)
      setPage({ state: 'loaded', event: updated })
      setBanner({ kind: 'ok', text: 'Completed. The status change has been recorded.' })
    } catch (error) {
      setBanner({
        kind: 'error',
        text: error instanceof EventRuleError
          ? error.message
          : unexpectedFailureMessage(error, 'complete the event'),
      })
    } finally {
      setCompleting(false)
    }
  }

  function refreshAfterBooking() {
    void getEvent(event.id, session).then((updated) => {
      if (updated) setPage({ state: 'loaded', event: updated })
    }).catch(() => {
      setBanner({ kind: 'error', text: 'The venue request was saved. Refresh to see the latest event status.' })
    })
  }

  /** US11.1: send the form's values as a change request, not as a save. */
  async function handleRequestChange() {
    // A submitted event has to stay complete, so the proposal meets the same
    // rules submitting it did. The server re-checks.
    const problem = submissionError(draft, todayIso())
    if (problem) {
      setBanner({ kind: 'error', text: problem })
      return
    }
    setRequesting(true)
    setBanner(null)
    try {
      // Sent as typed, not trimmed: the server compares exactly, and trimming
      // here would propose a change to a field the Organiser never touched.
      const updated = await requestEventChange(
        event.id,
        {
          title: draft.title,
          purpose: draft.purpose,
          description: draft.description,
          startsAt: draft.startsAt,
          endsAt: draft.endsAt,
          expectedAttendance: Number(draft.expectedAttendance.trim()),
        },
        changeNote.trim(),
        session,
      )
      setPage({ state: 'loaded', event: updated })
      setDraft(draftFrom(updated))
      setProposing(false)
      setChangeNote('')
      setBanner({
        kind: 'ok',
        text: `Change request sent. The event is now ${updated.status} and the Coordinator will review your changes.`,
      })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'send the change request'),
      })
    } finally {
      setRequesting(false)
    }
  }

  function handleCancelProposal() {
    setProposing(false)
    setDraft(draftFrom(event))
    setChangeNote('')
    setBanner(null)
  }

  async function handleApproveChange() {
    setAnswering('approve')
    setBanner(null)
    try {
      const updated = await approveEventChange(event.id, session)
      setPage({ state: 'loaded', event: updated })
      setDraft(draftFrom(updated))
      setBanner({
        kind: 'ok',
        text: 'Changes approved and applied. You can now decide the event.',
      })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'approve the requested changes'),
      })
    } finally {
      setAnswering(null)
    }
  }

  async function handleRejectChange() {
    // The button stays disabled until a reason is typed, and the server
    // refuses an empty one, so there is no blank reason to guard against here.
    const reason = changeRejection.trim()
    setAnswering('reject')
    setBanner(null)
    try {
      const updated = await rejectEventChange(event.id, reason, session)
      setPage({ state: 'loaded', event: updated })
      setChangeRejection('')
      setBanner({
        kind: 'ok',
        text: 'Changes rejected. The Organiser can see your reason.',
      })
    } catch (error) {
      setBanner({
        kind: 'error',
        text:
          error instanceof EventRuleError
            ? error.message
            : unexpectedFailureMessage(error, 'reject the requested changes'),
      })
    } finally {
      setAnswering(null)
    }
  }

  async function handleSave() {
    if (!hasDraftContent(draft)) {
      setBanner({ kind: 'error', text: DRAFT_CONTENT_ERROR })
      return
    }
    if (draft.endsAt.trim() && draft.endsAt <= draft.startsAt) {
      setBanner({ kind: 'error', text: 'The end date must be after the start date.' })
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
          title: draft.title,
          purpose: draft.purpose,
          description: draft.description,
          startsAt: draft.startsAt,
          endsAt: draft.endsAt || null,
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
    const problem = submissionError(draft, todayIso())
    if (problem) {
      setBanner({ kind: 'error', text: problem })
      return
    }
    const attendance = Number(draft.expectedAttendance.trim())
    setBusy(true)
    setBanner(null)
    try {
      // Save the fields edited on this page before moving the draft to Submitted.
      // Otherwise the submit request would validate the older database values.
      const saved = await saveEvent(
        event.id,
        {
          title: draft.title.trim(),
          purpose: draft.purpose.trim(),
          description: draft.description.trim(),
          startsAt: draft.startsAt.trim(),
          endsAt: draft.endsAt.trim(),
          expectedAttendance: attendance,
        },
        session,
      )
      const updated = await submitEvent(saved.id, session)
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
            <h1 className="page-title">{displayEventTitle(event.title)}</h1>
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
                    onChange={(e) => {
                      setDraft({ ...draft, title: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
                  />
                </div>
                <div className="field">
                  <label htmlFor="startsAt">Starts</label>
                  <input
                    id="startsAt"
                    type="datetime-local"
                    value={draft.startsAt}
                    onChange={(e) => {
                      setDraft({ ...draft, startsAt: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
                  />
                </div>
                <div className="field">
                  <label htmlFor="purpose">Purpose</label>
                  <input
                    id="purpose"
                    maxLength={500}
                    value={draft.purpose}
                    onChange={(e) => {
                      setDraft({ ...draft, purpose: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
                  />
                </div>
                <div className="field">
                  <label htmlFor="endsAt">Ends</label>
                  <input
                    id="endsAt"
                    type="datetime-local"
                    value={draft.endsAt}
                    onChange={(e) => {
                      setDraft({ ...draft, endsAt: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
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
                    onChange={(e) => {
                      setDraft({ ...draft, expectedAttendance: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
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
                    onChange={(e) => {
                      setDraft({ ...draft, description: e.target.value })
                      setBanner(null)
                    }}
                    disabled={writePending}
                  />
                </div>
              </div>
            ) : (
              <dl className="detail-readonly">
                <dt>Starts</dt>
                <dd>{event.startsAt ? formatTimestamp(event.startsAt) : 'Not set'}</dd>
                <dt>Ends</dt>
                <dd>{event.endsAt ? formatTimestamp(event.endsAt) : 'Not set'}</dd>
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
                    disabled={writePending || !dirty}
                  >
                    {busy ? 'Saving…' : canEdit && !isOwner ? 'Save changes' : 'Save draft'}
                  </button>
                )}
                {isOwner && event.status === 'Draft' && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={writePending || !submitCheck.allowed}
                    title={submitCheck.allowed ? undefined : submitRefusalMessage(submitCheck.reason)}
                  >
                    {busy ? 'Working…' : 'Submit event'}
                  </button>
                )}
                {isOwner && proposing && (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleRequestChange}
                      disabled={writePending || !dirty}
                    >
                      {requesting ? 'Sending…' : 'Submit change request'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleCancelProposal}
                      disabled={writePending}
                    >
                      Cancel
                    </button>
                  </>
                )}
                {isOwner && !proposing && changeCheck.allowed && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => {
                      setProposing(true)
                      setBanner(null)
                    }}
                    disabled={writePending}
                  >
                    Request changes
                  </button>
                )}
              </div>
            )}

            {/* US11.1: the note travels with the request, in the history the
                Coordinator reads — where an answer to a US7.3 question goes. */}
            {isOwner && proposing && (
              <label className="detail-clarify-field detail-change-note">
                <span className="detail-clarify-label">Note for the Coordinator (optional)</span>
                <textarea
                  rows={3}
                  maxLength={2000}
                  value={changeNote}
                  disabled={writePending}
                  onChange={(changeEvent) => setChangeNote(changeEvent.target.value)}
                />
              </label>
            )}

            {isOwner && event.status !== 'Draft' && (
              <p className="detail-note">
                {proposing
                  ? 'Edit the details above, then submit them for the Coordinator to review. ' +
                    'Your event keeps its current details until they approve.'
                  : changeCheck.allowed
                    ? 'This event has been submitted, so it is no longer edited directly. ' +
                      'Request changes and the Coordinator will review them.'
                    : changeRequestRefusalMessage(changeCheck.reason)}
              </p>
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
            <p className="detail-side-lede">Event status transitions and requested changes.</p>
            <StatusTimeline history={event.history} />

            {/* US11.1: the Coordinator's answer to the last request. It is not a
                status change, so it is not in the trail above; it is kept on
                the request itself and shown here. */}
            {lastReview && (
              <div className="detail-change-review">
                <h3 className="detail-clarify-title">
                  {lastReview.outcome === 'approved'
                    ? 'Requested changes approved'
                    : 'Requested changes rejected'}
                </h3>
                <p className="detail-clarify-lede">
                  {lastReview.outcome === 'approved'
                    ? 'The Coordinator applied the changes on '
                    : 'The Coordinator kept the current details on '}
                  <time dateTime={lastReview.at}>{formatTimestamp(lastReview.at)}</time>.
                </p>
                {lastReview.requestNote && (
                  <blockquote className="timeline-note">
                    <p className="timeline-note-label">Organiser’s note</p>
                    {lastReview.requestNote}
                  </blockquote>
                )}
                {lastReview.note && (
                  <blockquote className="timeline-note">
                    <p className="timeline-note-label">Reason</p>
                    {lastReview.note}
                  </blockquote>
                )}
              </div>
            )}

            {/* US11.1: the Organiser's proposal, visible to both sides. The
                Coordinator answers it here, before the decision below. */}
            {changeRequested && pendingChanges.length > 0 && (
              <div className="detail-change-review">
                <h3 className="detail-clarify-title">Requested changes</h3>
                <p className="detail-clarify-lede">
                  {mayReview
                    ? event.status === 'Under Review'
                      ? 'The Organiser has asked to change these details. Review them and ' +
                        'approve or reject the request before deciding the event.'
                      : 'The Organiser has asked to change these details. Approve or reject ' +
                        'the request; the event keeps its current status.'
                    : 'Awaiting the Coordinator’s review. Your event keeps its current ' +
                      'details until the changes are approved.'}
                </p>
                <ProposedChanges changes={pendingChanges} />
                {event.changeRequestNote && <p className="detail-clarify-lede">{event.changeRequestNote}</p>}
                {mayReview && (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={writePending}
                      onClick={handleApproveChange}
                    >
                      {answering === 'approve' ? 'Approving…' : 'Approve changes'}
                    </button>
                    <label className="detail-clarify-field detail-decision-reason">
                      <span className="detail-clarify-label">
                        Reason for rejecting the changes
                      </span>
                      <textarea
                        rows={3}
                        maxLength={2000}
                        value={changeRejection}
                        disabled={writePending}
                        onChange={(changeEvent) => setChangeRejection(changeEvent.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn btn-danger-solid btn-sm"
                      disabled={writePending || changeRejection.trim() === ''}
                      onClick={handleRejectChange}
                    >
                      {answering === 'reject' ? 'Rejecting…' : 'Reject changes'}
                    </button>
                  </>
                )}
              </div>
            )}

            {canDecide && (
              <div className="detail-decision">
                <h3 className="detail-clarify-title">Review decision</h3>
                <p className="detail-clarify-lede">
                  Approve this event to move it forward, or reject it with a reason the
                  Organiser can see.
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={writePending}
                  onClick={handleApprove}
                >
                  {deciding === 'approve' ? 'Approvingâ€¦' : 'Approve event'}
                </button>
                <label className="detail-clarify-field detail-decision-reason">
                  <span className="detail-clarify-label">Reason for rejection</span>
                  <textarea
                    rows={4}
                    maxLength={2000}
                    value={rejectionReason}
                    disabled={writePending}
                    onChange={(changeEvent) => setRejectionReason(changeEvent.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-danger-solid btn-sm"
                  disabled={writePending || rejectionReason.trim() === ''}
                  onClick={handleReject}
                >
                  {deciding === 'reject' ? 'Rejectingâ€¦' : 'Reject event'}
                </button>
              </div>
            )}

            {canComplete && (
              <div className="detail-decision">
                <h3 className="detail-clarify-title">Complete event</h3>
                <p className="detail-clarify-lede">
                  {eventEnded ? 'The event has ended and can be marked Completed.'
                    : 'You can mark this event Completed after its end date and time.'}
                </p>
                <button type="button" className="btn btn-primary btn-sm"
                  disabled={writePending || !eventEnded} onClick={handleComplete}>
                  {completing ? 'Completing…' : 'Mark Completed'}
                </button>
              </div>
            )}

            {/* US7.3. In the history panel rather than beside the form, because
                a request is an entry in this trail and the Organiser reads it
                here. A Coordinator who cannot ask yet is told why instead of
                being shown a control that would be refused. */}
            {mayReview && (
              <div className="detail-clarify">
                <h3 className="detail-clarify-title">Request clarification</h3>
                {clarificationCheck.allowed ? (
                  <>
                    <p className="detail-clarify-lede">
                      Ask the Organiser for information or changes. This moves the event to
                      Under Review, and they will see your message here.
                    </p>
                    <label className="detail-clarify-field">
                      <span className="detail-clarify-label">
                        What do you need from them?
                      </span>
                      <textarea
                        rows={4}
                        maxLength={2000}
                        value={clarification}
                        disabled={writePending}
                        onChange={(changeEvent) => setClarification(changeEvent.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={writePending || clarification.trim() === ''}
                      onClick={handleRequestClarification}
                    >
                      {asking ? 'Sending…' : 'Send request'}
                    </button>
                  </>
                ) : (
                  <p className="detail-clarify-lede">
                    {clarificationRefusalMessage(clarificationCheck.reason)}
                  </p>
                )}
              </div>
            )}
          </aside>
        </div>

        {/* US14.1. Not on a Draft: nothing can be requested for one, so the
            card would only ever say so. */}
        {event.status !== 'Draft' && <EventBookings event={event} session={session} onBookingRequested={refreshAfterBooking} />}
        <EventEquipment event={event} session={session} />
      </div>
    </div>
  )
}
