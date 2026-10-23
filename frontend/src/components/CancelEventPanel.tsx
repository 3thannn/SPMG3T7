import { useState } from 'react'
import './CancelEventPanel.css'
import {
  EVENT_CANCELLATION_REASON_MAX,
  EventRuleError,
  cancelEvent,
  type EventRecord,
} from '../eventsStore'
import { unexpectedFailureMessage, type Session } from '../api'
import { can } from '../permissions'
import { checkCancel, formatTimestamp } from '../status'

type Props = {
  event: EventRecord
  session: Session
  /** Another write on the page is in flight. */
  disabled: boolean
  /** The event was cancelled: the page shows it as it now is, and says so. */
  onUpdated: (event: EventRecord, message: string) => void
  onError: (message: string) => void
}

/**
 * Whether this person may cancel this event: the Organiser who owns it, or the
 * Coordinator it is assigned to once it has been submitted. The server
 * re-checks, and its refusal is the rule.
 */
function mayCancel(event: EventRecord, session: Session): boolean {
  if (!can(session, 'events:cancel') || !checkCancel(event).allowed) return false
  if (event.organiserId === session.id) return true
  return event.coordinatorId === session.id && event.status !== 'Draft'
}

/**
 * US4.6: cancelling the event.
 *
 * Cancelling is final and gives back every venue and every equipment line, so
 * it takes two steps: a button opens a box that says what will happen and asks
 * why, and only a reason enables the confirmation.
 */
export default function CancelEventPanel({ event, session, disabled, onUpdated, onError }: Props) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [cancelling, setCancelling] = useState(false)

  if (!mayCancel(event, session)) return null

  async function handleConfirm() {
    // The button stays disabled until a reason is typed, and the server
    // refuses an empty one, so there is no blank reason to guard against here.
    setCancelling(true)
    try {
      const updated = await cancelEvent(event.id, reason.trim(), session)
      onUpdated(
        updated,
        'Cancelled. Its venue bookings and equipment have been released, its registrations ' +
          'cancelled, and everyone involved has been told.',
      )
    } catch (error) {
      onError(
        error instanceof EventRuleError
          ? error.message
          : unexpectedFailureMessage(error, 'cancel the event'),
      )
    } finally {
      setCancelling(false)
    }
  }

  const busy = disabled || cancelling
  return (
    <div className="detail-decision event-cancel">
      <h3 className="detail-clarify-title">Cancel event</h3>
      {open ? (
        <>
          <p className="detail-clarify-lede event-cancel-warning" role="note">
            This cannot be undone. Every venue booking and hold still keeping a slot is
            cancelled, every equipment request is released, every registration is marked Event
            Cancelled, and the event becomes read-only. Everyone involved is told, with your
            reason; registered Attendees are told it is cancelled, without the reason.
          </p>
          <label className="detail-clarify-field detail-decision-reason">
            <span className="detail-clarify-label">Why is this event being cancelled?</span>
            <textarea
              rows={4}
              maxLength={EVENT_CANCELLATION_REASON_MAX}
              value={reason}
              disabled={busy}
              onChange={(changeEvent) => setReason(changeEvent.target.value)}
            />
          </label>
          <div className="event-cancel-actions">
            <button
              type="button"
              className="btn btn-danger-solid btn-sm"
              disabled={busy || reason.trim() === ''}
              onClick={handleConfirm}
            >
              {cancelling ? 'Cancelling…' : 'Confirm cancellation'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={cancelling}
              onClick={() => {
                setOpen(false)
                setReason('')
              }}
            >
              Keep event
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="detail-clarify-lede">
            If this event is no longer going ahead, cancel it to give back its venues and
            equipment.
          </p>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={disabled}
            onClick={() => setOpen(true)}
          >
            Cancel this event…
          </button>
        </>
      )}
    </div>
  )
}

/**
 * US4.6: on a cancelled event, who cancelled it, when and why, above
 * everything else, so nobody reads a read-only page as one they can change.
 */
export function CancelledNotice({ event }: { event: EventRecord }) {
  if (event.status !== 'Cancelled') return null
  const entry = [...event.history].reverse().find((change) => change.to === 'Cancelled')
  return (
    <div className="event-cancelled" role="note">
      <p className="event-cancelled-title">
        Cancelled
        {entry && ` by ${entry.byName || 'a former user'} on ${formatTimestamp(entry.at)}`}
      </p>
      {entry?.notes && <p className="event-cancelled-reason">Reason: {entry.notes}</p>}
      <p className="event-cancelled-lede">
        This event is read-only. Its venue bookings and equipment were released and its
        registrations cancelled.
      </p>
    </div>
  )
}
