import { useEffect, useMemo, useState } from 'react'
import './EventsPage.css'
import StatusBadge from '../components/StatusBadge'
import { listEvents, type EventRecord } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { navigate } from '../router'
import { EVENT_STATUSES, formatRecordedAt, type EventStatus } from '../status'
import type { Session } from '../api'

type EventsPageProps = {
  session: Session
}

type Filter = EventStatus | 'All'

/**
 * US4.1: the list surface. Every row carries its status badge, and what the
 * list contains depends on the viewer's role — an Organiser sees the events
 * they own, while a Coordinator sees requests after submission.
 * US8.6: Coordinator Lead sees all events, across all statuses and organisers.
 */
export default function EventsPage({ session }: EventsPageProps) {
  const [events, setEvents] = useState<EventRecord[] | null>(null)
  const [filter, setFilter] = useState<Filter>('All')
  const [loadError, setLoadError] = useState('')

  const seesAcrossOrganisers =
    session.role === 'Event Coordinator' || session.role === 'Event Coordinator Lead'

  useEffect(() => {
    let cancelled = false
    listEvents(session)
      .then((loaded) => {
        if (!cancelled) setEvents(loaded)
      })
      .catch(() => {
        // The list is now a network call, so it can fail for reasons that have
        // nothing to do with the user. Say so rather than showing "no events",
        // which reads as "you have none" and is a different thing entirely.
        if (cancelled) return
        setEvents([])
        setLoadError('Could not load your events. Check the API is running and try again.')
      })
    return () => {
      cancelled = true
    }
    // The token identifies both the caller and the session; a new one means a
    // different view of the list.
  }, [session, session.token])

  // Only offer filters for statuses actually present, so the control never
  // shows nine chips against two events.
  const presentStatuses = useMemo(() => {
    const present = new Set((events ?? []).map((event) => event.status))
    return EVENT_STATUSES.filter((status) => present.has(status))
  }, [events])

  const visible = useMemo(() => {
    if (!events) return []
    return filter === 'All' ? events : events.filter((event) => event.status === filter)
  }, [events, filter])

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Events</h1>
            <p className="page-subtitle">
              {session.role === 'Event Coordinator Lead'
                ? 'All events across the programme, as Coordinator Lead.'
                : seesAcrossOrganisers
                  ? 'Submitted event requests across the programme, as Coordinator.'
                  : 'Events you own, as Organiser.'}
            </p>
          </div>
          {!seesAcrossOrganisers && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate('/events/new')}
            >
              New event
            </button>
          )}
        </header>

        {presentStatuses.length > 1 && (
          <div className="event-filters" role="group" aria-label="Filter by status">
            <button
              type="button"
              className={`filter-chip${filter === 'All' ? ' is-active' : ''}`}
              onClick={() => setFilter('All')}
              aria-pressed={filter === 'All'}
            >
              All
            </button>
            {presentStatuses.map((status) => (
              <button
                key={status}
                type="button"
                className={`filter-chip${filter === status ? ' is-active' : ''}`}
                onClick={() => setFilter(status)}
                aria-pressed={filter === status}
              >
                {status}
              </button>
            ))}
          </div>
        )}

        {loadError && (
          <p className="form-error" role="alert">
            {loadError}
          </p>
        )}

        {events === null ? (
          <p className="muted">Loading events…</p>
        ) : loadError ? null : visible.length === 0 ? (
          <div className="card empty">
            <h3>{events.length === 0 ? 'No events yet' : 'Nothing matches that filter'}</h3>
            <p>
              {events.length === 0
                ? seesAcrossOrganisers
                  ? 'Once an Organiser submits an event, it appears here.'
                  : 'Create your first event and it will start as a Draft.'
                : 'Try a different status.'}
            </p>
            {events.length === 0 && !seesAcrossOrganisers && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/events/new')}
                style={{ marginTop: '1.25rem' }}
              >
                New event
              </button>
            )}
          </div>
        ) : (
          <ul className="event-list">
            {visible.map((event) => (
              <li key={event.id}>
                <a
                  className="event-card"
                  href={`#/events/${event.id}`}
                  onClick={(clickEvent) => {
                    clickEvent.preventDefault()
                    navigate(`/events/${event.id}`)
                  }}
                >
                  <div className={`event-date-badge status-${event.status.toLowerCase().replace(/\s+/g, '-')}`}>
                    {event.startsAt ? (
                      <>
                        <div className="date-day">{new Date(event.startsAt).getDate()}</div>
                        <div className="date-month">
                          {new Date(event.startsAt).toLocaleDateString('en-US', { month: 'short' })}
                        </div>
                        <div className="date-time">
                          {new Date(event.startsAt).toLocaleTimeString('en-US', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="date-day">—</div>
                        <div className="date-month">TBD</div>
                      </>
                    )}
                  </div>

                  <div className="event-content">
                    <div className="event-header">
                      <h3 className="event-title">{displayEventTitle(event.title)}</h3>
                      {/* US11.1: what puts a request in the Coordinator's queue.
                          US4.6: nobody can answer one on a cancelled event. */}
                      {event.changeRequested && event.status !== 'Cancelled' && (
                        <span className="event-row-flag">Change requested</span>
                      )}
                      <StatusBadge status={event.status} />
                    </div>
                    <p className="event-meta">
                      {seesAcrossOrganisers && <>Organiser: {event.organiserName}</>}
                    </p>
                    <p className="event-updated">Updated {formatRecordedAt(event.updatedAt)}</p>
                  </div>

                  <div className="event-arrow">
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
        )}
      </div>
    </div>
  )
}