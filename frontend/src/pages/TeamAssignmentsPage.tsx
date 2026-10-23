import { useEffect, useState } from 'react'
import './TeamAssignmentsPage.css'
import { listEvents, type EventRecord } from '../eventsStore'
import { formatTimestamp } from '../status'
import StatusBadge from '../components/StatusBadge'
import { navigate } from '../router'
import type { Session } from '../api'

/**
 * US8.5: Team Assignments - Coordinator Lead sees all active events and assignments.
 *
 * Shows all active events (not Draft, Completed, Cancelled or Rejected) with their
 * assigned Coordinator or 'Unassigned'. Includes filtering by coordinator and
 * event count statistics per coordinator.
 */

type CoordinatorStats = {
  coordinatorId: string | null
  coordinatorName: string
  eventCount: number
}

type TeamAssignmentsPageProps = {
  session: Session
}

export default function TeamAssignmentsPage({ session }: TeamAssignmentsPageProps) {
  const [allEvents, setAllEvents] = useState<EventRecord[]>([])
  const [filteredEvents, setFilteredEvents] = useState<EventRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedCoordinator, setSelectedCoordinator] = useState<string>('all')

  // Load events on mount
  useEffect(() => {
    setLoading(true)
    setError('')

    listEvents(session)
      .then((events) => {
        // US8.5: Filter to active events only (exclude Draft, Completed, Cancelled, Rejected)
        const activeEvents = events.filter(
          (e) =>
            e.status !== 'Draft' &&
            e.status !== 'Completed' &&
            e.status !== 'Cancelled' &&
            e.status !== 'Rejected'
        )
        setAllEvents(activeEvents)
        setFilteredEvents(activeEvents)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to load events:', err)
        setError('Could not load team assignments.')
        setLoading(false)
      })
  }, [session])

  // Apply coordinator filter
  useEffect(() => {
    if (selectedCoordinator === 'all') {
      setFilteredEvents(allEvents)
    } else if (selectedCoordinator === 'unassigned') {
      setFilteredEvents(allEvents.filter((e) => !e.coordinatorId))
    } else {
      setFilteredEvents(allEvents.filter((e) => e.coordinatorId === selectedCoordinator))
    }
  }, [selectedCoordinator, allEvents])

  // Calculate coordinator statistics
  const coordinatorStats: CoordinatorStats[] = (() => {
    const statsMap = new Map<string | null, CoordinatorStats>()

    allEvents.forEach((event) => {
      const key = event.coordinatorId ?? null
      const existing = statsMap.get(key)

      if (existing) {
        existing.eventCount++
      } else {
        statsMap.set(key, {
          coordinatorId: key,
          coordinatorName: event.coordinatorName || 'Unassigned',
          eventCount: 1,
        })
      }
    })

    return Array.from(statsMap.values()).sort((a, b) => {
      // Unassigned first, then alphabetical by name
      if (a.coordinatorId === null) return -1
      if (b.coordinatorId === null) return 1
      return a.coordinatorName.localeCompare(b.coordinatorName)
    })
  })()

  // Get unique coordinators for filter dropdown
  const coordinatorOptions = coordinatorStats.map((stat) => ({
    id: stat.coordinatorId || 'unassigned',
    name: stat.coordinatorName,
  }))

  return (
    <div className="shell page-container">
      <header className="page-header">
        <h1 className="page-title">Team Assignments</h1>
        <p className="page-subtitle">
          All active events and their assigned coordinators · {allEvents.length} active{' '}
          {allEvents.length === 1 ? 'event' : 'events'}
        </p>
      </header>

      {error && (
        <div className="notice notice-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {loading ? (
        <div className="page-loading">Loading assignments...</div>
      ) : (
        <>
          {/* US8.5: Coordinator Statistics */}
          {coordinatorStats.length > 0 && (
            <div className="assignments-stats">
              <h2 className="assignments-stats-title">Workload Distribution</h2>
              <div className="assignments-stats-grid">
                {coordinatorStats.map((stat) => (
                  <div key={stat.coordinatorId || 'unassigned'} className="stat-card">
                    <div className="stat-name">{stat.coordinatorName}</div>
                    <div className="stat-count">
                      {stat.eventCount} {stat.eventCount === 1 ? 'event' : 'events'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* US8.5: Filter by Coordinator */}
          <div className="assignments-filters">
            <label htmlFor="coordinator-filter" className="filter-label">
              Filter by Coordinator:
            </label>
            <select
              id="coordinator-filter"
              className="filter-select"
              value={selectedCoordinator}
              onChange={(e) => setSelectedCoordinator(e.target.value)}
            >
              <option value="all">All Coordinators ({allEvents.length})</option>
              {coordinatorOptions.map((option) => {
                const count = coordinatorStats.find(
                  (s) => (s.coordinatorId || 'unassigned') === option.id
                )?.eventCount || 0
                return (
                  <option key={option.id} value={option.id}>
                    {option.name} ({count})
                  </option>
                )
              })}
            </select>
          </div>

          {/* US8.5: Events List */}
          {filteredEvents.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-message">
                {selectedCoordinator === 'all'
                  ? 'No active events to display.'
                  : 'No events match the selected filter.'}
              </p>
            </div>
          ) : (
            <div className="assignments-table-container">
              <table className="assignments-table">
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Status</th>
                    <th>Assigned Coordinator</th>
                    <th>Start Date</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.map((event) => (
                    <tr
                      key={event.id}
                      className="assignments-table-row"
                      onClick={() => navigate(`/events/${event.id}`)}
                    >
                      <td className="event-title-cell">
                        <div className="event-title">{event.title || 'Untitled Event'}</div>
                        {event.purpose && <div className="event-purpose">{event.purpose}</div>}
                      </td>
                      <td>
                        <StatusBadge status={event.status} size="sm" />
                      </td>
                      <td className="coordinator-cell">
                        {event.coordinatorName ? (
                          <span className="coordinator-name">{event.coordinatorName}</span>
                        ) : (
                          <span className="coordinator-unassigned">Unassigned</span>
                        )}
                      </td>
                      <td className="date-cell">{formatTimestamp(event.startsAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
