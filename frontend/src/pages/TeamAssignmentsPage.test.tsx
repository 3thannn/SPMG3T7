/**
 * US8.5: Team Assignments - Coordinator Lead views workload distribution.
 *
 * Tests that the Lead can see all active events, filter by coordinator,
 * and view workload statistics.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import TeamAssignmentsPage from './TeamAssignmentsPage'
import * as eventsStore from '../eventsStore'
import { buildSession } from '../test/sessions'
import type { EventRecord } from '../eventsStore'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listEvents: vi.fn(),
}))

const listEventsMock = vi.mocked(eventsStore.listEvents)

afterEach(() => {
  vi.resetAllMocks()
})

const lead = buildSession({ role: 'Event Coordinator Lead', id: '10', name: 'Jordan' })

function buildEvent(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Tech Conference',
    purpose: 'Annual tech meetup',
    description: 'A gathering of tech enthusiasts',
    startsAt: '2027-03-15T09:00',
    endsAt: '2027-03-15T17:00',
    expectedAttendance: 100,
    status: 'Under Review',
    organiserId: '1',
    organiserName: 'Dylan',
    coordinatorId: '2',
    coordinatorName: 'Alice Chen',
    createdAt: '2027-02-01T10:00:00+08:00',
    updatedAt: '2027-02-01T10:00:00+08:00',
    history: [],
    ...overrides,
  }
}

it('excludes Draft, Completed, Cancelled, and Rejected events', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent({ id: '101', title: 'Under Review Event', status: 'Under Review' }),
    buildEvent({ id: '102', title: 'Draft Event', status: 'Draft' }),
    buildEvent({ id: '103', title: 'Completed Event', status: 'Completed' }),
    buildEvent({ id: '104', title: 'Cancelled Event', status: 'Cancelled' }),
    buildEvent({ id: '105', title: 'Rejected Event', status: 'Rejected' }),
    buildEvent({ id: '106', title: 'Approved Event', status: 'Approved' }),
  ])

  render(<TeamAssignmentsPage session={lead} />)

  await screen.findByText('Under Review Event')
  expect(screen.getByText('Approved Event')).toBeInTheDocument()
  expect(screen.getByText(/2.*active.*events/)).toBeInTheDocument()

  expect(screen.queryByText('Draft Event')).not.toBeInTheDocument()
  expect(screen.queryByText('Completed Event')).not.toBeInTheDocument()
  expect(screen.queryByText('Cancelled Event')).not.toBeInTheDocument()
  expect(screen.queryByText('Rejected Event')).not.toBeInTheDocument()
})

it('displays workload distribution statistics', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent({ id: '101', coordinatorId: '2', coordinatorName: 'Alice Chen' }),
    buildEvent({ id: '102', coordinatorId: '2', coordinatorName: 'Alice Chen' }),
    buildEvent({ id: '103', coordinatorId: '3', coordinatorName: 'Bob Smith' }),
    buildEvent({ id: '104', coordinatorId: null, coordinatorName: undefined }),
  ])

  render(<TeamAssignmentsPage session={lead} />)

  await screen.findByText('Workload Distribution')

  // Check stats cards - use getAllByText since names appear in both stats and table
  expect(screen.getAllByText('Alice Chen').length).toBeGreaterThan(0)
  expect(screen.getByText('2 events')).toBeInTheDocument()
  expect(screen.getAllByText('Bob Smith').length).toBeGreaterThan(0)
  expect(screen.getAllByText(/1.*event/).length).toBeGreaterThan(0)
  expect(screen.getAllByText('Unassigned').length).toBeGreaterThan(0)
})

it('allows filtering by coordinator', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent({ id: '101', title: 'Alice Event 1', coordinatorId: '2', coordinatorName: 'Alice Chen' }),
    buildEvent({ id: '102', title: 'Alice Event 2', coordinatorId: '2', coordinatorName: 'Alice Chen' }),
    buildEvent({ id: '103', title: 'Bob Event', coordinatorId: '3', coordinatorName: 'Bob Smith' }),
  ])

  render(<TeamAssignmentsPage session={lead} />)

  await screen.findByText('Alice Event 1')
  expect(screen.getByText('Bob Event')).toBeInTheDocument()

  // Filter to Alice's events (using her ID since that's the option value)
  const filterSelect = screen.getByLabelText('Filter by Coordinator:')
  await userEvent.selectOptions(filterSelect, '2')

  expect(screen.getByText('Alice Event 1')).toBeInTheDocument()
  expect(screen.getByText('Alice Event 2')).toBeInTheDocument()
  expect(screen.queryByText('Bob Event')).not.toBeInTheDocument()
})

it('filters to unassigned events, and back to all', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent({ id: '101', title: 'Alice Event', coordinatorId: '2', coordinatorName: 'Alice Chen' }),
    buildEvent({ id: '102', title: 'Nobody Event', coordinatorId: null, coordinatorName: undefined }),
  ])

  render(<TeamAssignmentsPage session={lead} />)

  await screen.findByText('Alice Event')
  const filterSelect = screen.getByLabelText('Filter by Coordinator:')
  await userEvent.selectOptions(filterSelect, 'unassigned')

  expect(screen.getByText('Nobody Event')).toBeInTheDocument()
  expect(screen.queryByText('Alice Event')).not.toBeInTheDocument()

  await userEvent.selectOptions(filterSelect, 'all')
  expect(screen.getByText('Alice Event')).toBeInTheDocument()
})

it('says so when the events cannot be loaded', async () => {
  listEventsMock.mockRejectedValue(new Error('offline'))
  vi.spyOn(console, 'error').mockImplementation(() => {})

  render(<TeamAssignmentsPage session={lead} />)

  expect(await screen.findByText('Could not load team assignments.')).toBeInTheDocument()
})
