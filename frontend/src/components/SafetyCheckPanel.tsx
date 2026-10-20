import { useCallback, useEffect, useState } from 'react'
import {
  EventRuleError,
  approveSafetyCheck,
  getSafetyReadiness,
  returnSafetyCheck,
  sendForSafetyCheck,
  type EventRecord,
  type SafetyReadiness,
} from '../eventsStore'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'

/** The longest note the server accepts, so the box stops where the rule does. */
export const SAFETY_NOTE_MAX = 2000

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
 * US4.4: the Pending Safety Check stage, as each role meets it on the event.
 *
 * The assigned Coordinator sends a Planning event for its check once the
 * server says it is ready; the Safety Officer signs a waiting event off or
 * sends it back to Planning with a note. Nobody else sees anything here.
 * As everywhere else, the server re-checks each move and its refusal is the rule.
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
          Waiting for the Safety Officer. They will confirm the event or send it back to
          Planning with what needs to change.
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

  const ready = readiness.state === 'loaded' && readiness.readiness.ready
  return (
    <div className="detail-decision">
      <h3 className="detail-clarify-title">Safety check</h3>
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

function SafetyDecision({ event, session, disabled, onUpdated, onError }: Props) {
  const [note, setNote] = useState('')
  const [deciding, setDeciding] = useState<'approve' | 'return' | null>(null)

  async function handleApprove() {
    setDeciding('approve')
    try {
      const updated = await approveSafetyCheck(event.id, session)
      onUpdated(updated, 'Approved. The event is now Confirmed.')
    } catch (error) {
      onError(failureText(error, 'approve the safety check'))
    } finally {
      setDeciding(null)
    }
  }

  async function handleReturn() {
    // The button stays disabled until a note is typed, and the server refuses
    // an empty one, so there is no blank note to guard against here.
    setDeciding('return')
    try {
      const updated = await returnSafetyCheck(event.id, note.trim(), session)
      setNote('')
      onUpdated(updated, 'Sent back to Planning. The Coordinator can see your note.')
    } catch (error) {
      onError(failureText(error, 'send the event back'))
    } finally {
      setDeciding(null)
    }
  }

  const busy = disabled || deciding !== null
  return (
    <div className="detail-decision">
      <h3 className="detail-clarify-title">Safety check decision</h3>
      <p className="detail-clarify-lede">
        Approve to confirm this event, or send it back to Planning with what needs to change.
      </p>
      <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={handleApprove}>
        {deciding === 'approve' ? 'Approving…' : 'Approve safety check'}
      </button>
      <label className="detail-clarify-field detail-decision-reason">
        <span className="detail-clarify-label">What needs to change</span>
        <textarea
          rows={4}
          maxLength={SAFETY_NOTE_MAX}
          value={note}
          disabled={busy}
          onChange={(changeEvent) => setNote(changeEvent.target.value)}
        />
      </label>
      <button
        type="button"
        className="btn btn-danger-solid btn-sm"
        disabled={busy || note.trim() === ''}
        onClick={handleReturn}
      >
        {deciding === 'return' ? 'Sending back…' : 'Send back to Planning'}
      </button>
    </div>
  )
}
