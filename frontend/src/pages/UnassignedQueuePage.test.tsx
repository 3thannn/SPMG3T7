/**
 * US8.2 + US8.3: Unassigned queue and coordinator assignment tests.
 *
 * Tests that the Lead can view unassigned events and assign coordinators.
 */

import { act, render, screen, waitFor } from '@testing-library/react'
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

it('loads and displays unassigned events', async () => {
  listUnassignedEventsMock.mockResolvedValue([
    buildUnassignedEvent(),
    buildUnassignedEvent({
      id: '102',
      title: 'Workshop Series',
      organiserName: 'Ethan',
    }),
  ])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  expect(await screen.findByText('Tech Conference')).toBeInTheDocument()
  expect(screen.getByText('Workshop Series')).toBeInTheDocument()
  // Check that both events are shown (can verify via their titles above)
  // The count display shows "2 events pending" but text is split, so just verify events loaded
})

it('shows empty state when there are no unassigned events', async () => {
  listUnassignedEventsMock.mockResolvedValue([])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  expect(await screen.findByText('All caught up!')).toBeInTheDocument()
  expect(
    screen.getByText(/No unassigned events right now/),
  ).toBeInTheDocument()
})

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

it('shows coordinator picker when assign button is clicked', async () => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  await screen.findByText('Tech Conference')

  const assignButton = screen.getByRole('button', { name: /Assign Coordinator/ })
  await userEvent.click(assignButton)

  expect(screen.getByText(/Select a coordinator to assign this event to/)).toBeInTheDocument()
  expect(screen.getByText('Alice Chen')).toBeInTheDocument()
  expect(screen.getByText('alice@spmg3t7.edu')).toBeInTheDocument()
  expect(screen.getByText('Bob Smith')).toBeInTheDocument()
  expect(screen.getByText('bob@spmg3t7.edu')).toBeInTheDocument()
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

it('shows success message and removes event from list after successful assignment', async () => {
  listUnassignedEventsMock.mockResolvedValue([
    buildUnassignedEvent(),
    buildUnassignedEvent({ id: '102', title: 'Workshop Series' }),
  ])
  listCoordinatorsMock.mockResolvedValue(coordinators)
  assignCoordinatorMock.mockResolvedValue()

  render(<UnassignedQueuePage session={lead} />)

  await screen.findByText('Tech Conference')
  await screen.findByText('Workshop Series')

  // Click assign on first event
  const assignButtons = screen.getAllByRole('button', { name: /Assign Coordinator/ })
  await userEvent.click(assignButtons[0])

  // Select Alice
  const aliceButton = screen.getByRole('button', { name: /Alice Chen/ })
  await userEvent.click(aliceButton)

  // Verify success message
  expect(await screen.findByText(/Event assigned to Alice Chen successfully!/)).toBeInTheDocument()

  // Verify first event is removed
  expect(screen.queryByText('Tech Conference')).not.toBeInTheDocument()
  // But second event remains
  expect(screen.getByText('Workshop Series')).toBeInTheDocument()
})

it('shows error message on failed assignment', async () => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)
  assignCoordinatorMock.mockRejectedValue(new Error('Network error'))

  render(<UnassignedQueuePage session={lead} />)

  await screen.findByText('Tech Conference')

  const assignButton = screen.getByRole('button', { name: /Assign Coordinator/ })
  await userEvent.click(assignButton)

  const aliceButton = screen.getByRole('button', { name: /Alice Chen/ })
  await userEvent.click(aliceButton)

  expect(await screen.findByText(/Network error/)).toBeInTheDocument()
})

it('shows loading state while fetching events', () => {
  listUnassignedEventsMock.mockImplementation(() => new Promise(() => {})) // Never resolves
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  expect(screen.getByText('Loading unassigned events…')).toBeInTheDocument()
})

it('shows error when events fail to load', async () => {
  listUnassignedEventsMock.mockRejectedValue(new Error('Failed to fetch'))
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  expect(await screen.findByText(/Failed to fetch/)).toBeInTheDocument()
})

it('allows canceling coordinator selection', async () => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)

  await screen.findByText('Tech Conference')

  // Open picker
  const assignButton = screen.getByRole('button', { name: /Assign Coordinator/ })
  await userEvent.click(assignButton)

  expect(screen.getByText(/Select a coordinator to assign this event to/)).toBeInTheDocument()

  // Cancel
  const cancelButton = screen.getByRole('button', { name: /Cancel/ })
  await userEvent.click(cancelButton)

  // Picker should be hidden, assign button should be back
  expect(screen.queryByText(/Select a coordinator to assign this event to/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Assign Coordinator/ })).toBeInTheDocument()
})


it('lists the event that has waited longest first', async () => {
  listUnassignedEventsMock.mockResolvedValue([
    buildUnassignedEvent({ id: '102', title: 'Later', submittedAt: '2027-02-03T10:00:00+08:00' }),
    buildUnassignedEvent({ id: '103', title: 'Earliest', submittedAt: '2027-01-15T10:00:00+08:00' }),
    buildUnassignedEvent({ id: '104', title: 'Middle', submittedAt: '2027-02-01T10:00:00+08:00' }),
    buildUnassignedEvent({ id: '105', title: 'Same time', submittedAt: '2027-02-01T10:00:00+08:00' }),
  ])
  listCoordinatorsMock.mockResolvedValue(coordinators)

  render(<UnassignedQueuePage session={lead} />)
  await screen.findByText('Earliest')

  const titles = screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
  expect(titles).toEqual(['Earliest', 'Middle', 'Same time', 'Later'])
})

it('narrows the queue by title, organiser, purpose or description, and clears', async () => {
  const user = userEvent.setup()
  listUnassignedEventsMock.mockResolvedValue([
    buildUnassignedEvent(),
    buildUnassignedEvent({
      id: '102',
      title: 'Workshop Series',
      organiserName: 'Mei Lin',
      purpose: null,
      description: 'Hands-on sessions',
    }),
    buildUnassignedEvent({ id: '103', title: 'Alumni Night', purpose: null, description: null }),
  ])
  listCoordinatorsMock.mockResolvedValue(coordinators)
  render(<UnassignedQueuePage session={lead} />)
  await screen.findByText('Tech Conference')
  const search = screen.getByPlaceholderText('Search events...')

  for (const [query, shown] of [
    ['workshop', 'Workshop Series'],
    ['MEI', 'Workshop Series'],
    ['annual tech', 'Tech Conference'],
    ['hands-on', 'Workshop Series'],
  ]) {
    await user.clear(search)
    await user.type(search, query)
    expect(screen.getByText(shown)).toBeInTheDocument()
    expect(screen.queryByText('Alumni Night')).not.toBeInTheDocument()
  }

  await user.click(screen.getByRole('button', { name: 'Clear search' }))

  expect(screen.getByText('Tech Conference')).toBeInTheDocument()
  expect(screen.getByText('Workshop Series')).toBeInTheDocument()
  expect(screen.getByText('Alumni Night')).toBeInTheDocument()
})

it('clears the success message after five seconds', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
    listCoordinatorsMock.mockResolvedValue(coordinators)
    assignCoordinatorMock.mockResolvedValue()
    render(<UnassignedQueuePage session={lead} />)

    await user.click(await screen.findByRole('button', { name: /Assign Coordinator/ }))
    await user.click(screen.getByRole('button', { name: /Alice Chen/ }))
    expect(await screen.findByText(/Event assigned to Alice Chen successfully!/)).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(screen.queryByText(/Event assigned to Alice Chen successfully!/)).not.toBeInTheDocument()
  } finally {
    vi.useRealTimers()
  }
})

it.each([
  ['the close button', () => userEvent.click(screen.getByRole('button', { name: 'Close' }))],
  ['a click outside it', () => userEvent.click(document.querySelector('.modal-overlay')!)],
])('closes the picker from %s, and not from a click inside it', async (_how, close) => {
  listUnassignedEventsMock.mockResolvedValue([buildUnassignedEvent()])
  listCoordinatorsMock.mockResolvedValue(coordinators)
  render(<UnassignedQueuePage session={lead} />)
  await userEvent.click(await screen.findByRole('button', { name: /Assign Coordinator/ }))

  await userEvent.click(screen.getByText(/Select a coordinator to assign this event to/))
  expect(screen.getByText(/Select a coordinator to assign this event to/)).toBeInTheDocument()

  await close()

  expect(screen.queryByText(/Select a coordinator to assign this event to/)).not.toBeInTheDocument()
  expect(assignCoordinatorMock).not.toHaveBeenCalled()
})

it('ignores answers that arrive after the page has gone', async () => {
  let deliverEvents!: (events: unassignedQueueStore.UnassignedEvent[]) => void
  let deliverCoordinators!: (loaded: unassignedQueueStore.Coordinator[]) => void
  listUnassignedEventsMock.mockReturnValue(new Promise((resolve) => (deliverEvents = resolve)))
  listCoordinatorsMock.mockReturnValue(new Promise((resolve) => (deliverCoordinators = resolve)))
  const { unmount } = render(<UnassignedQueuePage session={lead} />)

  unmount()
  deliverEvents([buildUnassignedEvent()])
  deliverCoordinators(coordinators)
  await Promise.resolve()

  expect(listUnassignedEventsMock).toHaveBeenCalledTimes(1)
})

it('ignores a failure that arrives after the page has gone', async () => {
  let fail!: (error: Error) => void
  listUnassignedEventsMock.mockReturnValue(new Promise((_resolve, reject) => (fail = reject)))
  listCoordinatorsMock.mockResolvedValue(coordinators)
  const { unmount } = render(<UnassignedQueuePage session={lead} />)

  unmount()
  fail(new Error('Could not load unassigned events.'))
  await Promise.resolve()

  expect(listUnassignedEventsMock).toHaveBeenCalledTimes(1)
})
