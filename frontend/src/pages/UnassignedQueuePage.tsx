import { useEffect, useState } from 'react'
import type { Session } from '../api'
import {
  assignCoordinator,
  listCoordinators,
  listUnassignedEvents,
  type Coordinator,
  type UnassignedEvent,
} from '../unassignedQueueStore'
import { formatTimestamp } from '../status'
import StatusBadge from '../components/StatusBadge'
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

  return (
    <div className="page">
      <div className="shell">
        <header className="unassigned-header">
          <div>
            <h1 className="page-title">Unassigned Event Queue</h1>
            <p className="page-subtitle">
              Submitted events awaiting coordinator assignment
            </p>
          </div>
          {events && events.length > 0 && (
            <div className="queue-count">
              <span className="count-number">{events.length}</span>
              <span className="count-label">event{events.length === 1 ? '' : 's'} pending</span>
            </div>
          )}
        </header>

        {assignSuccess && (
          <div className="alert alert-success" role="status">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 0C4.48 0 0 4.48 0 10C0 15.52 4.48 20 10 20C15.52 20 20 15.52 20 10C20 4.48 15.52 0 10 0ZM8 15L3 10L4.41 8.59L8 12.17L15.59 4.58L17 6L8 15Z" fill="currentColor"/>
            </svg>
            <span>{assignSuccess}</span>
          </div>
        )}

        {assignError && (
          <div className="alert alert-error" role="alert">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 0C4.48 0 0 4.48 0 10C0 15.52 4.48 20 10 20C15.52 20 20 15.52 20 10C20 4.48 15.52 0 10 0ZM11 15H9V13H11V15ZM11 11H9V5H11V11Z" fill="currentColor"/>
            </svg>
            <span>{assignError}</span>
          </div>
        )}

        {loadError && (
          <div className="alert alert-error" role="alert">
            <span>{loadError}</span>
          </div>
        )}

        {events === null ? (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Loading unassigned events…</p>
          </div>
        ) : loadError ? null : events.length === 0 ? (
          <div className="empty-state">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="32" cy="32" r="30" stroke="currentColor" strokeWidth="2" opacity="0.2"/>
              <path d="M32 20L32 44M20 32L44 32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.3"/>
            </svg>
            <h3>All caught up!</h3>
            <p>
              No unassigned events right now. New submissions will appear here automatically.
            </p>
          </div>
        ) : (
          <div className="events-grid">
            {events.map((event) => (
              <div key={event.id} className={`event-card ${assigningEvent === event.id ? 'assigning' : ''}`}>
                <div className="event-card-header">
                  <div className="event-title-section">
                    <h3 className="event-title">{event.title}</h3>
                    <StatusBadge status={event.status} />
                  </div>
                  {event.purpose && <p className="event-purpose">{event.purpose}</p>}
                </div>

                <div className="event-meta-grid">
                  <div className="meta-item">
                    <span className="meta-label">Proposed Date</span>
                    <span className="meta-value">
                      {event.startsAt ? formatTimestamp(event.startsAt) : 'Not set'}
                    </span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Expected Attendance</span>
                    <span className="meta-value">{event.expectedAttendance ?? '—'}</span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Organiser</span>
                    <span className="meta-value">{event.organiserName}</span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Submitted</span>
                    <span className="meta-value meta-timestamp">
                      {formatTimestamp(event.submittedAt)}
                    </span>
                  </div>
                </div>

                {event.description && (
                  <div className="event-description">
                    <p>{event.description}</p>
                  </div>
                )}

                <div className="event-card-footer">
                  {selectedEventForAssignment === event.id ? (
                    <div className="coordinator-picker">
                      <p className="picker-label">Select a coordinator:</p>
                      <div className="coordinator-list">
                        {coordinators.map((coord) => (
                          <button
                            key={coord.id}
                            type="button"
                            className="coordinator-option"
                            onClick={() => handleAssign(event.id, coord.id)}
                            disabled={assigningEvent === event.id}
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
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setSelectedEventForAssignment(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => setSelectedEventForAssignment(event.id)}
                      disabled={assigningEvent === event.id || coordinators.length === 0}
                    >
                      {assigningEvent === event.id ? (
                        <>
                          <div className="button-spinner"></div>
                          Assigning...
                        </>
                      ) : (
                        <>
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M8 0C3.6 0 0 3.6 0 8C0 12.4 3.6 16 8 16C12.4 16 16 12.4 16 8C16 3.6 12.4 0 8 0ZM8 4C9.1 4 10 4.9 10 6C10 7.1 9.1 8 8 8C6.9 8 6 7.1 6 6C6 4.9 6.9 4 8 4ZM8 14C6 14 4.3 12.9 3.4 11.2C3.4 9.5 6.7 8.5 8 8.5C9.3 8.5 12.6 9.5 12.6 11.2C11.7 12.9 10 14 8 14Z" fill="currentColor"/>
                          </svg>
                          Assign Coordinator
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
