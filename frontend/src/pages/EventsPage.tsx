import { useEffect, useMemo, useState } from 'react'
import './EventsPage.css'
import StatusBadge from '../components/StatusBadge'
import { listEvents, type EventRecord } from '../eventsStore'
import { displayEventTitle } from '../draftRules'
import { navigate } from '../router'
import { EVENT_STATUSES, formatTimestamp, type EventStatus } from '../status'
import type { Session } from '../api'

type EventsPageProps = {
  session: Session
}

type Filter = EventStatus | 'All'

/**
 * US4.1: the list surface. Every row carries its status badge, and what the
 * list contains depends on the viewer's role — an Organiser sees the events
 * they own, a Coordinator sees all of them.
 */
export default function EventsPage({ session }: EventsPageProps) {
  const [events, setEvents] = useState<EventRecord[] | null>(null)
  const [filter, setFilter] = useState<Filter>('All')
  const [loadError, setLoadError] = useState('')

  const seesAll = session.role === 'Event Coordinator'

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
              {seesAll
                ? 'Every event across the programme, as Coordinator.'
                : 'Events you own, as Organiser.'}
            </p>
          </div>
          {!seesAll && (
            <div className="page-head-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/events/new')}
              >
                Create event
              </button>
            </div>
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
                ? seesAll
                  ? 'Once an Organiser creates an event, it appears here.'
                  : 'Create your first event and it will start as a Draft.'
                : 'Try a different status.'}
            </p>
            {events.length === 0 && !seesAll && (
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
                  className="event-row card"
                  href={`#/events/${event.id}`}
                  onClick={(clickEvent) => {
                    clickEvent.preventDefault()
                    navigate(`/events/${event.id}`)
                  }}
                >
                  <div className="event-row-main">
                    <h3 className="event-row-title">{displayEventTitle(event.title)}</h3>
                    <p className="event-row-meta">
                      {event.startsAt ? formatTimestamp(event.startsAt) : 'Not set'}
                      {seesAll && <> · Organiser: {event.organiserName}</>}
                    </p>
                  </div>
                  <div className="event-row-end">
                    <StatusBadge status={event.status} />
                    <span className="event-row-updated">
                      Updated {formatTimestamp(event.updatedAt)}
                    </span>
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
