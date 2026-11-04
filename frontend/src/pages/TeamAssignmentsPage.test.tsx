/**
 * The Lead's team assignments page — US8.5.
 *
 * Who may see every event is the server's rule (backend tests, US8.5); this
 * page's job is listing the active ones, counting each Coordinator's load and
 * filtering by Coordinator.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import TeamAssignmentsPage from './TeamAssignmentsPage'
import { listEvents, type EventRecord } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listEvents: vi.fn(),
}))

const listMock = vi.mocked(listEvents)
const lead = buildSession({ role: 'Event Coordinator Lead' })

function event(id: string, title: string, overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id,
    title,
    purpose: '',
    description: '',
    startsAt: '2027-11-02T09:00:00',
    expectedAttendance: 30,
    status: 'Planning',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2027-10-01T09:00:00',
    updatedAt: '2027-10-01T09:00:00',
    coordinatorId: '2',
    coordinatorName: 'Priya',
    history: [],
    ...overrides,
  } as EventRecord
}

afterEach(() => {
  vi.resetAllMocks()
})

function rows() {
  return within(screen.getByRole('table')).getAllByRole('row').slice(1)
}

it('TC-TA01 lists active events only, with each Coordinator\'s load', async () => {
  listMock.mockResolvedValue([
    event('1', 'Open Day'),
    event('2', 'Gala', { coordinatorId: '7', coordinatorName: 'Alex' }),
    event('3', 'Careers Fair', { coordinatorId: null, coordinatorName: '' }),
    event('4', 'Old Fair', { status: 'Completed' }),
    event('5', 'A draft', { status: 'Draft' }),
  ])
  render(<TeamAssignmentsPage session={lead} />)

  expect(await screen.findByText(/3 active events/)).toBeInTheDocument()
  expect(rows()).toHaveLength(3)
  expect(screen.queryByText('Old Fair')).toBeNull()
  expect(screen.getByRole('option', { name: 'All Coordinators (3)' })).toBeInTheDocument()
})

it('TC-TA02 filters by Coordinator, and by unassigned', async () => {
  listMock.mockResolvedValue([
    event('1', 'Open Day'),
    event('2', 'Gala', { coordinatorId: '7', coordinatorName: 'Alex' }),
    event('3', 'Careers Fair', { coordinatorId: null, coordinatorName: '' }),
  ])
  render(<TeamAssignmentsPage session={lead} />)
  const filter = await screen.findByLabelText('Filter by Coordinator:')

  await userEvent.selectOptions(filter, '7')
  expect(rows().map((row) => within(row).getAllByRole('cell')[0].textContent)).toEqual(['Gala'])

  await userEvent.selectOptions(filter, 'unassigned')
  expect(rows().map((row) => within(row).getAllByRole('cell')[0].textContent)).toEqual([
    'Careers Fair',
  ])

  await userEvent.selectOptions(filter, 'all')
  expect(rows()).toHaveLength(3)
})

it('TC-TA03 says so when the events cannot be loaded', async () => {
  listMock.mockRejectedValue(new Error('offline'))
  vi.spyOn(console, 'error').mockImplementation(() => {})
  render(<TeamAssignmentsPage session={lead} />)

  expect(await screen.findByText('Could not load team assignments.')).toBeInTheDocument()
})
