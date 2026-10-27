import { useCallback, useEffect, useState } from 'react'
import './SafetyCheckPanel.css'
import {
  EventRuleError,
  approveSafetyCheck,
  formatBookingTimes,
  getSafetyReadiness,
  getSafetyReview,
  listSafetyDecisions,
  rejectSafetyCheck,
  requestSafetyChanges,
  resolveSafetyFlag,
  sendForSafetyCheck,
  type EventRecord,
  type SafetyDecision as SafetyDecisionRecord,
  type SafetyFlag,
  type SafetyOutcome,
  type SafetyReadiness,
  type SafetyReview,
} from '../eventsStore'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'

/** The longest note the server accepts, so the box stops where the rule does. */
export const SAFETY_NOTE_MAX = 2000

/** US17.2: how each outcome reads wherever a decision is shown. */
const OUTCOME_LABELS: Record<SafetyOutcome, string> = {
  approved: 'Approved',
  'changes-requested': 'Changes requested',
  rejected: 'Rejected',
}

type Props = {
  event: EventRecord
  session: Session
  /** Another write on the page is in flight. */
  disabled: boolean
  /** A move succeeded: the page shows the event as it now is, and says so. */
  onUpdated: (event: EventRecord, message: string) => void
  onError: (message: string) => void
}

function failureText(error: unknown, action: string): string {
  return error instanceof EventRuleError ? error.message : unexpectedFailureMessage(error, action)
}

/**
 * US4.4/US17.2: the Pending Safety Check stage, as each role meets it on the event.
 *
 * The assigned Coordinator sends a Planning event for its check once the
 * server says it is ready, after re-reviewing anything the Safety Officer
 * flagged last time. The Safety Officer approves a waiting event, requests
 * changes, or rejects it. Nobody else sees anything here. As everywhere else,
 * the server re-checks each move and its refusal is the rule.
 */
export default function SafetyCheckPanel(props: Props) {
  const { event, session } = props
  const assigned = can(session, 'safety:submit') && event.coordinatorId === session.id
  if (assigned && event.status === 'Planning') return <SendForSafetyCheck {...props} />
  if (assigned && event.status === 'Pending Safety Check') {
    return (
      <div className="detail-decision">
        <h3 className="detail-clarify-title">Safety check</h3>
        <p className="detail-clarify-lede">
          Waiting for the Safety Officer. They will confirm the event, or send it back to
          Planning with what needs to change or why it was rejected.
        </p>
      </div>
    )
  }
  if (can(session, 'safety:review') && event.status === 'Pending Safety Check') {
    return <SafetyDecision {...props} />
  }
  return null
}

type Readiness =
  | { state: 'loading' }
  | { state: 'loaded'; readiness: SafetyReadiness }
  | { state: 'error' }

function SendForSafetyCheck({ event, session, disabled, onUpdated, onError }: Props) {
  const [readiness, setReadiness] = useState<Readiness>({ state: 'loading' })
  const [sending, setSending] = useState(false)
  // US17.2: the Safety Officer's last word, and the flags it raised.
  const [latest, setLatest] = useState<SafetyDecisionRecord | null>(null)
  const [decisionsFailed, setDecisionsFailed] = useState(false)
  const [resolving, setResolving] = useState<string | null>(null)

  const load = useCallback(() => {
    let cancelled = false
    getSafetyReadiness(event.id, session)
      .then((found) => {
        if (!cancelled) setReadiness({ state: 'loaded', readiness: found })
      })
      .catch(() => {
        if (!cancelled) setReadiness({ state: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  // Re-checked whenever the event is reloaded, which is what the page does
  // after a booking changes.
  useEffect(load, [load, event.updatedAt])

  useEffect(() => {
    let cancelled = false
    listSafetyDecisions(event.id, session)
      .then((found) => {
        if (!cancelled) setLatest(found[0] ?? null)
      })
      .catch(() => {
        if (!cancelled) setDecisionsFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  function check() {
    setReadiness({ state: 'loading' })
    load()
  }

  async function handleSend() {
    setSending(true)
    try {
      const updated = await sendForSafetyCheck(event.id, session)
      onUpdated(updated, 'Sent for the safety check. The event is now Pending Safety Check.')
    } catch (error) {
      onError(failureText(error, 'send the event for its safety check'))
      // What made it unready is worth showing straight away.
      check()
    } finally {
      setSending(false)
    }
  }

  async function handleResolve(decision: SafetyDecisionRecord, flag: SafetyFlag) {
    setResolving(flag.id)
    try {
      const resolved = await resolveSafetyFlag(event.id, flag.id, session)
      setLatest({
        ...decision,
        flags: decision.flags.map((each) => (each.id === resolved.id ? resolved : each)),
      })
      // The last open flag may have been the only thing holding the event back.
      check()
    } catch (error) {
      onError(failureText(error, 'mark the arrangement re-reviewed'))
    } finally {
      setResolving(null)
    }
  }

  const ready = readiness.state === 'loaded' && readiness.readiness.ready
  // An approval moves the event to Confirmed, so in Planning the latest
  // decision is a request for changes or a rejection, if there is one at all.
  const sentBack = latest !== null && latest.outcome !== 'approved' ? latest : null
  return (
    <div className="detail-decision">
      <h3 className="detail-clarify-title">Safety check</h3>
      {decisionsFailed && (
        <p className="detail-clarify-lede">Could not load the Safety Officer's last decision.</p>
      )}
      {sentBack && (
        <DecisionSummary
          decision={sentBack}
          className="safety-feedback"
          resolving={resolving}
          disabled={disabled || sending || resolving !== null}
          onResolve={(flag) => handleResolve(sentBack, flag)}
        />
      )}
      <p className="detail-clarify-lede" role="status">
        {readiness.state === 'loading' && 'Checking whether this event is ready…'}
        {readiness.state === 'error' && 'Could not check whether this event is ready.'}
        {readiness.state === 'loaded' &&
          (readiness.readiness.ready
            ? 'Every venue booking is Confirmed and all equipment is reserved. ' +
              'Send the event to the Safety Officer for sign-off.'
            : readiness.readiness.message)}
      </p>
      <button
        type="button"
        className="btn btn-primary btn-sm"
        disabled={disabled || sending || !ready}
        onClick={handleSend}
      >
        {sending ? 'Sending…' : 'Send for safety check'}
      </button>
      {!ready && readiness.state !== 'loading' && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={check}>
          Check again
        </button>
      )}
    </div>
  )
}

type Review = { state: 'loading' } | { state: 'loaded'; review: SafetyReview } | { state: 'error' }

/** The two ways back to Planning. Approval is its own button. */
type SendBack = 'changes-requested' | 'rejected'

/** A flag's key in the picker: one namespace for bookings and equipment. */
type FlagKey = `${'booking' | 'equipment'}:${string}`

function SafetyDecision({ event, session, disabled, onUpdated, onError }: Props) {
  const [review, setReview] = useState<Review>({ state: 'loading' })
  const [earlier, setEarlier] = useState<SafetyDecisionRecord[]>([])
  const [sendBack, setSendBack] = useState<SendBack>('changes-requested')
  const [note, setNote] = useState('')
  const [flagged, setFlagged] = useState<ReadonlySet<FlagKey>>(new Set())
  const [deciding, setDeciding] = useState<SafetyOutcome | null>(null)

  const load = useCallback(() => {
    let cancelled = false
    getSafetyReview(event.id, session)
      .then((found) => {
        if (!cancelled) setReview({ state: 'loaded', review: found })
      })
      .catch(() => {
        if (!cancelled) setReview({ state: 'error' })
      })
    listSafetyDecisions(event.id, session)
      .then((found) => {
        if (!cancelled) setEarlier(found)
      })
      // Earlier decisions are context; without them the decision can still be made.
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [event.id, session])

  useEffect(load, [load])

  function retry() {
    setReview({ state: 'loading' })
    load()
  }

  function toggle(key: FlagKey) {
    setFlagged((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function flaggedIds(target: 'booking' | 'equipment'): string[] {
    return [...flagged]
      .filter((key) => key.startsWith(`${target}:`))
      .map((key) => key.slice(target.length + 1))
  }

  async function decide(
    outcome: SafetyOutcome,
    action: () => Promise<EventRecord>,
    message: string,
    failure: string,
  ) {
    setDeciding(outcome)
    try {
      onUpdated(await action(), message)
    } catch (error) {
      onError(failureText(error, failure))
    } finally {
      setDeciding(null)
    }
  }

  // The decision is pinned to the submission the Safety Officer is looking
  // at, so nothing can be decided until the review has loaded.
  const loaded = review.state === 'loaded' ? review.review : null
  const startedAt = loaded?.waitingSince ?? ''

  function handleApprove() {
    return decide(
      'approved',
      () => approveSafetyCheck(event.id, startedAt, session),
      'Approved. The event is now Confirmed.',
      'approve the safety check',
    )
  }

  function handleSendBack() {
    // The button stays disabled until a note is typed, and the server refuses
    // an empty one, so there is no blank note to guard against here.
    const trimmed = note.trim()
    if (sendBack === 'rejected') {
      return decide(
        'rejected',
        () => rejectSafetyCheck(event.id, trimmed, startedAt, session),
        'Rejected. The event is back in Planning with your reason, and the Coordinator has been told.',
        'reject the safety check',
      )
    }
    return decide(
      'changes-requested',
      () =>
        requestSafetyChanges(
          event.id,
          {
            checkStartedAt: startedAt,
            note: trimmed,
            flaggedBookingIds: flaggedIds('booking'),
            flaggedEquipmentIds: flaggedIds('equipment'),
          },
          session,
        ),
      'Changes requested. The event is back in Planning and the Coordinator has been told.',
      'request changes',
    )
  }

  const busy = disabled || deciding !== null || loaded === null
  const rejecting = sendBack === 'rejected'
  let sendBackLabel = rejecting ? 'Reject safety check' : 'Request changes'
  if (deciding === 'rejected') sendBackLabel = 'Rejecting…'
  if (deciding === 'changes-requested') sendBackLabel = 'Sending back…'
  return (
    <div className="detail-decision">
      <h3 className="detail-clarify-title">Safety check decision</h3>
      <p className="detail-clarify-lede">
        Approve to confirm this event, or send it back to Planning: request changes, or
        reject it with your reason.
      </p>
      {review.state === 'loading' && (
        <p className="detail-clarify-lede">Loading what you are deciding on…</p>
      )}
      {review.state === 'error' && (
        <div className="form-error" role="alert">
          Could not load the safety review, so no decision can be recorded yet.{' '}
          <button type="button" className="btn btn-secondary btn-sm" onClick={retry}>
            Try again
          </button>
        </div>
      )}
      <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={handleApprove}>
        {deciding === 'approved' ? 'Approving…' : 'Approve safety check'}
      </button>

      <fieldset className="safety-choice" disabled={busy}>
        <legend className="detail-clarify-label">Or send it back to Planning</legend>
        <label className="safety-choice-option">
          <input
            type="radio"
            name="safety-send-back"
            checked={!rejecting}
            onChange={() => setSendBack('changes-requested')}
          />
          Request changes
        </label>
        <label className="safety-choice-option">
          <input
            type="radio"
            name="safety-send-back"
            checked={rejecting}
            onChange={() => setSendBack('rejected')}
          />
          Reject
        </label>
      </fieldset>
      <label className="detail-clarify-field detail-decision-reason">
        <span className="detail-clarify-label">
          {rejecting ? 'Reason for rejecting' : 'What needs to change'}
        </span>
        <textarea
          rows={4}
          maxLength={SAFETY_NOTE_MAX}
          value={note}
          disabled={busy}
          onChange={(changeEvent) => setNote(changeEvent.target.value)}
        />
      </label>
      {!rejecting && loaded && (
        <FlagPicker review={loaded} flagged={flagged} disabled={busy} onToggle={toggle} />
      )}
      <button
        type="button"
        className="btn btn-danger-solid btn-sm"
        disabled={busy || note.trim() === ''}
        onClick={handleSendBack}
      >
        {sendBackLabel}
      </button>

      {earlier.length > 0 && (
        <section className="safety-earlier" aria-label="Earlier safety decisions">
          <h4 className="safety-earlier-title">Earlier decisions on this event</h4>
          {earlier.map((decision) => (
            <DecisionSummary key={decision.id} decision={decision} className="safety-earlier-item" />
          ))}
        </section>
      )}
    </div>
  )
}

type FlagPickerProps = {
  review: SafetyReview
  flagged: ReadonlySet<FlagKey>
  disabled: boolean
  onToggle: (key: FlagKey) => void
}

/** US17.2: the booked venues and reserved equipment the request is about. */
function FlagPicker({ review, flagged, disabled, onToggle }: FlagPickerProps) {
  const options: { key: FlagKey; label: string }[] = [
    ...review.venues.map((venue) => ({
      key: `booking:${venue.bookingId}` as const,
      label: `${venue.venueName} · ${formatBookingTimes(venue.startsAt, venue.endsAt)}`,
    })),
    ...review.equipment.map((line) => ({
      key: `equipment:${line.id}` as const,
      label: `${line.type} × ${line.quantity}`,
    })),
  ]
  return (
    <fieldset className="safety-choice" disabled={disabled}>
      <legend className="detail-clarify-label">Flag for re-review (optional)</legend>
      {options.length === 0 ? (
        <p className="detail-clarify-lede">Nothing is booked or reserved to flag.</p>
      ) : (
        options.map((option) => (
          <label key={option.key} className="safety-choice-option">
            <input
              type="checkbox"
              checked={flagged.has(option.key)}
              onChange={() => onToggle(option.key)}
            />
            {option.label}
          </label>
        ))
      )}
    </fieldset>
  )
}

type DecisionSummaryProps = {
  decision: SafetyDecisionRecord
  className: string
  /** Given only to the Coordinator, who re-reviews what was flagged. */
  onResolve?: (flag: SafetyFlag) => void
  resolving?: string | null
  disabled?: boolean
}

/** US17.2: one decision — what, why, who and when — and the flags it raised. */
function DecisionSummary({
  decision,
  className,
  onResolve,
  resolving = null,
  disabled = false,
}: DecisionSummaryProps) {
  return (
    <div className={className}>
      <p className="safety-decision-head">
        <strong>{OUTCOME_LABELS[decision.outcome]}</strong> by{' '}
        {decision.decidedByName || 'the Safety Officer'} · {formatTimestamp(decision.decidedAt)}
      </p>
      <p className="safety-decision-note">{decision.note}</p>
      {decision.flags.length > 0 && (
        <ul className="safety-flags" aria-label="Flagged for re-review">
          {decision.flags.map((flag) => (
            <li key={flag.id} className={`safety-flag${flag.resolvedAt ? '' : ' is-open'}`}>
              <span className="safety-flag-label">
                {flag.label}
                {flag.startsAt && ` · ${formatBookingTimes(flag.startsAt, flag.endsAt)}`}
                {flag.status && <span className="muted"> ({flag.status})</span>}
              </span>
              {flag.resolvedAt ? (
                <span className="muted">
                  Re-reviewed by {flag.resolvedByName || 'the Coordinator'} ·{' '}
                  {formatTimestamp(flag.resolvedAt)}
                </span>
              ) : onResolve ? (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={disabled}
                  aria-label={`Mark ${flag.label} re-reviewed`}
                  onClick={() => onResolve(flag)}
                >
                  {resolving === flag.id ? 'Saving…' : 'Mark re-reviewed'}
                </button>
              ) : (
                <span className="muted">Not re-reviewed yet</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
