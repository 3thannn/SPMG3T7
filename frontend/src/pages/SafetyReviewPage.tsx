import { useEffect, useState } from 'react'
import './SafetyReviewPage.css'
import StatusBadge from '../components/StatusBadge'
import { listSafetyQueue, type EventRecord } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { formatTimestamp } from '../status'
import { navigate } from '../router'
import { unexpectedFailureMessage, type Session } from '../api'

interface Props {
  session: Session
}

type Queue =
  | { state: 'loading' }
  | { state: 'loaded'; events: EventRecord[] }
  | { state: 'error'; message: string }

/** When the event last entered Pending Safety Check — what "waiting since" means. */
function waitingSince(event: EventRecord): string {
  const entered = event.history.filter((change) => change.to === 'Pending Safety Check')
  return entered.length > 0 ? entered[entered.length - 1].at : event.updatedAt
}

/**
 * The Safety Officer's landing page (US1.4): events Pending Safety Check.
 *
 * US4.4 makes the queue real: every event waiting for sign-off, longest
 * waiting first as the server orders them. Opening one shows the approve and
 * send-back controls. US17.1 adds the venue and equipment detail a review
 * needs to this view.
 */
export default function SafetyReviewPage({ session }: Props) {
  const [queue, setQueue] = useState<Queue>({ state: 'loading' })

  useEffect(() => {
    let cancelled = false
    listSafetyQueue(session)
      .then((events) => {
        if (!cancelled) setQueue({ state: 'loaded', events })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setQueue({
            state: 'error',
            message: unexpectedFailureMessage(error, 'load the safety review queue'),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [session])

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Safety Review</h1>
            <p className="page-subtitle">
              Events waiting for your sign-off before they are Confirmed, longest waiting first.
            </p>
          </div>
        </header>
        {renderQueue()}
      </div>
    </div>
  )

  function renderQueue() {
    if (queue.state === 'loading') return <p className="muted">Loading the safety review queue…</p>
    if (queue.state === 'error') {
      return (
        <p className="form-error" role="alert">
          {queue.message}
        </p>
      )
    }
    if (queue.events.length === 0) {
      return (
        <div className="card empty">
          <h3>No events waiting for a safety check</h3>
          <p>An event appears here once its Coordinator sends it for sign-off.</p>
        </div>
      )
    }
    return (
      <ul className="safety-queue" aria-label="Events pending safety check">
        {queue.events.map((event) => (
          <li key={event.id} className="card safety-queue-item">
            <div className="safety-queue-head">
              <a
                className="safety-queue-title"
                href={`#/events/${event.id}`}
                onClick={(clickEvent) => {
                  clickEvent.preventDefault()
                  navigate(`/events/${event.id}`)
                }}
              >
                {displayEventTitle(event.title)}
              </a>
              <StatusBadge status={event.status} />
            </div>
            <dl className="safety-queue-facts">
              <div>
                <dt>Starts</dt>
                <dd>{event.startsAt ? formatTimestamp(event.startsAt) : 'Not set'}</dd>
              </div>
              <div>
                <dt>Expected attendance</dt>
                <dd>
                  {event.expectedAttendance === null
                    ? 'Not estimated'
                    : `${event.expectedAttendance} people`}
                </dd>
              </div>
              <div>
                <dt>Waiting since</dt>
                <dd>{formatTimestamp(waitingSince(event))}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    )
  }
}
