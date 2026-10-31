import { useEffect, useState, useMemo } from 'react'
import type { Session } from '../api'
import {
  assignCoordinator,
  listCoordinators,
  listUnassignedEvents,
  type Coordinator,
  type UnassignedEvent,
} from '../unassignedQueueStore'
import { formatRecordedAt } from '../status'
import './UnassignedQueuePage.css'

interface Props {
  session: Session
}

/**
 * US8.2 + US8.3: Coordinator Lead's landing page - unassigned event queue.
 *
 * Shows all Submitted events with no assigned Coordinator, oldest first.
 * Lead can assign each event to a Coordinator.
 */
export default function UnassignedQueuePage({ session }: Props) {
  const [events, setEvents] = useState<UnassignedEvent[] | null>(null)
  const [coordinators, setCoordinators] = useState<Coordinator[]>([])
  const [loadError, setLoadError] = useState('')
  const [assigningEvent, setAssigningEvent] = useState<string | null>(null)
  const [selectedEventForAssignment, setSelectedEventForAssignment] = useState<string | null>(null)
  const [assignError, setAssignError] = useState('')
  const [assignSuccess, setAssignSuccess] = useState('')

  const [searchQuery, setSearchQuery] = useState('')

  // Load unassigned events
  useEffect(() => {
    let cancelled = false
    listUnassignedEvents(session)
      .then((loaded) => {
        if (!cancelled) setEvents(loaded)
      })
      .catch((error) => {
        if (!cancelled) {
          setEvents([])
          setLoadError(error.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [session])

  // Load coordinators for assignment
  useEffect(() => {
    let cancelled = false
    listCoordinators(session)
      .then((loaded) => {
        if (!cancelled) setCoordinators(loaded)
      })
      .catch(() => {
        // Non-critical
      })
    return () => {
      cancelled = true
    }
  }, [session])

  // Filter and sort events
  const filteredAndSortedEvents = useMemo(() => {
    if (!events) return null

    let filtered = events

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = events.filter(
        (event) =>
          event.title.toLowerCase().includes(query) ||
          event.organiserName.toLowerCase().includes(query) ||
          event.purpose?.toLowerCase().includes(query) ||
          event.description?.toLowerCase().includes(query),
      )
    }

    // US8.2: oldest submission first, so the event waiting longest is on top.
    // The sort controls went in 9770658; this was the order they defaulted to.
    return [...filtered].sort((a, b) =>
      a.submittedAt < b.submittedAt ? -1 : a.submittedAt > b.submittedAt ? 1 : 0,
    )
  }, [events, searchQuery])

  async function handleAssign(eventId: string, coordinatorId: string) {
    setAssigningEvent(eventId)
    setAssignError('')
    setAssignSuccess('')
    setSelectedEventForAssignment(null)

    try {
      await assignCoordinator(session, eventId, coordinatorId)

      // Remove event from list (it's now assigned)
      setEvents((prev) => (prev ? prev.filter((e) => e.id !== eventId) : []))

      const coordinator = coordinators.find((c) => c.id === coordinatorId)
      setAssignSuccess(`Event assigned to ${coordinator?.name ?? 'coordinator'} successfully!`)

      // Clear success message after 5 seconds
      setTimeout(() => setAssignSuccess(''), 5000)
    } catch (error) {
      setAssignError(error instanceof Error ? error.message : 'Failed to assign coordinator')
    } finally {
      setAssigningEvent(null)
    }
  }

  const displayEvents = filteredAndSortedEvents ?? []
  const hasEvents = events && events.length > 0
  const hasResults = displayEvents.length > 0

  return (
    <div className="page">
      <div className="shell">
        <header className="unassigned-header">
          <h1 className="page-title">Unassigned Events</h1>
          {hasEvents && (
            <div className="queue-count">
              {events.length} event{events.length === 1 ? '' : 's'} awaiting assignment
            </div>
          )}
        </header>

        {assignSuccess && (
          <div className="alert alert-success" role="status">
            {assignSuccess}
          </div>
        )}

        {assignError && (
          <div className="alert alert-error" role="alert">
            {assignError}
          </div>
        )}

        {loadError && (
          <div className="alert alert-error" role="alert">
            {loadError}
          </div>
        )}

        {events === null ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading unassigned events…</p>
          </div>
        ) : loadError ? null : events.length === 0 ? (
          <div className="empty-state">
            <h3>All caught up!</h3>
            <p>No unassigned events right now. New submissions will appear here automatically.</p>
          </div>
        ) : (
          <>
            {/* Search bar */}
            <div className="search-bar">
              <input
                type="text"
                placeholder="Search events..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="search-input"
              />
              {searchQuery && (
                <button
                  className="search-clear"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                >
                  ×
                </button>
              )}
            </div>

            {/* Events list */}
            {hasResults ? (
              <div className="events-list">
                {displayEvents.map((event) => (
                  <div key={event.id} className="event-card">
                    <div className="event-date-badge">
                      <div className="date-day">
                        {event.startsAt ? new Date(event.startsAt).getDate() : '—'}
                      </div>
                      <div className="date-month">
                        {event.startsAt
                          ? new Date(event.startsAt).toLocaleDateString('en-US', { month: 'short' })
                          : 'TBD'}
                      </div>
                      {event.startsAt && (
                        <div className="date-time">
                          {new Date(event.startsAt).toLocaleTimeString('en-US', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </div>
                      )}
                    </div>

                    <div className="event-content">
                      <h3 className="event-title">{event.title}</h3>
                      <p className="event-purpose">{event.purpose || event.description || 'No description provided'}</p>
                      <div className="event-details">
                        <span className="detail-item">
                          <strong>Organiser:</strong> {event.organiserName}
                        </span>
                        {event.expectedAttendance && (
                          <span className="detail-item">
                            <strong>Attendance:</strong> {event.expectedAttendance}
                          </span>
                        )}
                        <span className="detail-item">
                          <strong>Submitted:</strong> {formatRecordedAt(event.submittedAt)}
                        </span>
                      </div>
                    </div>

                    <div className="event-action">
                      <button
                        type="button"
                        className="btn-assign-coordinator"
                        onClick={() => setSelectedEventForAssignment(event.id)}
                        disabled={assigningEvent === event.id || coordinators.length === 0}
                      >
                        {assigningEvent === event.id ? 'Assigning...' : '+ Assign Coordinator'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>No events found</h3>
                <p>Try adjusting your search query.</p>
              </div>
            )}
          </>
        )}

        {/* Coordinator assignment modal */}
        {selectedEventForAssignment && (
          <div className="modal-overlay" onClick={() => setSelectedEventForAssignment(null)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Assign Coordinator</h3>
                <button
                  type="button"
                  className="modal-close"
                  onClick={() => setSelectedEventForAssignment(null)}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>
              <div className="modal-body">
                <p>Select a coordinator to assign this event to:</p>
                <div className="coordinator-list">
                  {coordinators.map((coord) => (
                    <button
                      key={coord.id}
                      type="button"
                      className="coordinator-option"
                      onClick={() => handleAssign(selectedEventForAssignment, coord.id)}
                      disabled={assigningEvent === selectedEventForAssignment}
                    >
                      <div className="coordinator-avatar">
                        {coord.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div className="coordinator-info">
                        <span className="coordinator-name">{coord.name}</span>
                        <span className="coordinator-email">{coord.email}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setSelectedEventForAssignment(null)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
