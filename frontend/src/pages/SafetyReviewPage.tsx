import { useEffect, useState } from 'react'
import './SafetyReviewPage.css'
import StatusBadge from '../components/StatusBadge'
import { listSafetyQueue, type EventRecord } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { formatRecordedAt } from '../status'
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
 * US4.4/US17.1: every event waiting for sign-off, oldest first as the server
 * orders them. Opening one shows the read-only safety review (US17.1) and the
 * approve and send-back controls (US4.4).
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
          <li key={event.id}>
            <a
              className="safety-event-card"
              href={`#/events/${event.id}`}
              aria-label={displayEventTitle(event.title)}
              onClick={(clickEvent) => {
                clickEvent.preventDefault()
                navigate(`/events/${event.id}`)
              }}
            >
              <div className="safety-event-date-badge">
                {event.startsAt ? (
                  <>
                    <span className="safety-date-day">{new Date(event.startsAt).getDate()}</span>
                    <span className="safety-date-month">
                      {new Date(event.startsAt).toLocaleDateString('en-US', { month: 'short' })}
                    </span>
                    <span className="safety-date-time">
                      {new Date(event.startsAt).toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="safety-date-day">—</span>
                    <span className="safety-date-month">TBD</span>
                  </>
                )}
              </div>

              <div className="safety-event-content">
                <div className="safety-event-header">
                  <h2 className="safety-event-title">{displayEventTitle(event.title)}</h2>
                  <StatusBadge status={event.status} />
                </div>
                <p className="safety-event-meta">
                  Expected attendance:{' '}
                  {event.expectedAttendance === null
                    ? 'Not estimated'
                    : `${event.expectedAttendance} people`}
                  <span aria-hidden="true"> · </span>
                  Waiting since: {formatRecordedAt(waitingSince(event))}
                </p>
              </div>

              <div className="safety-event-arrow" aria-hidden="true">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </div>
            </a>
          </li>
        ))}
      </ul>
    )
  }
}
