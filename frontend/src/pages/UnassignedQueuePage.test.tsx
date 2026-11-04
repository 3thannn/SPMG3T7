/**
 * US8.2 + US8.3: Unassigned queue and coordinator assignment tests.
 *
 * Tests that the Lead can view unassigned events and assign coordinators.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import UnassignedQueuePage from './UnassignedQueuePage'
import * as unassignedQueueStore from '../unassignedQueueStore'
import { buildSession } from '../test/sessions'

vi.mock('../unassignedQueueStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../unassignedQueueStore')>()),
  listUnassignedEvents: vi.fn(),
  listCoordinators: vi.fn(),
  assignCoordinator: vi.fn(),
}))

const listUnassignedEventsMock = vi.mocked(unassignedQueueStore.listUnassignedEvents)
const listCoordinatorsMock = vi.mocked(unassignedQueueStore.listCoordinators)
const assignCoordinatorMock = vi.mocked(unassignedQueueStore.assignCoordinator)

afterEach(() => {
  vi.resetAllMocks()
})

const lead = buildSession({ role: 'Event Coordinator Lead', id: '10', name: 'Jordan' })

const coordinators: unassignedQueueStore.Coordinator[] = [
  { id: '2', name: 'Alice Chen', email: 'alice@spmg3t7.edu' },
  { id: '3', name: 'Bob Smith', email: 'bob@spmg3t7.edu' },
]

function buildUnassignedEvent(
  overrides: Partial<unassignedQueueStore.UnassignedEvent> = {},
): unassignedQueueStore.UnassignedEvent {
  return {
    id: '101',
    title: 'Tech Conference',
    purpose: 'Annual tech meetup',
    description: 'A gathering of tech enthusiasts',
    startsAt: '2027-03-15T09:00',
    expectedAttendance: 100,
    status: 'Submitted',
    organiserId: '1',
    organiserName: 'Dylan',
    submittedAt: '2027-02-01T10:00:00+08:00',
    coordinatorId: null,
    ...overrides,
  }
}

it('displays event details including organiser and submission time', async () => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  expect(await screen.findByText('Tech Conference')).toBeInTheDocument()
  expect(screen.getByText('Annual tech meetup')).toBeInTheDocument()
  expect(screen.getByText('Dylan')).toBeInTheDocument()
  // Submission time is shown in the redesigned card layout
  expect(screen.getByText(/01 Feb 2027, 10:00/)).toBeInTheDocument()
})

it('assigns coordinator when a coordinator is selected', async () => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)
  assignCoordinatorMock.mockResolvedValue()

  render(<UnassignedQueuePage session={lead} />)

  await screen.findByText('Tech Conference')

  // Click assign button
  const assignButton = screen.getByRole('button', { name: /Assign Coordinator/ })
  await userEvent.click(assignButton)

  // Select a coordinator
  const aliceButton = screen.getByRole('button', { name: /Alice Chen/ })
  await userEvent.click(aliceButton)

  // Verify assignment was called
  await waitFor(() =>
    expect(assignCoordinatorMock).toHaveBeenCalledWith(lead, '101', '2'),
  )
})
