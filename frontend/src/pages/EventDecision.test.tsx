import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  EventRuleError,
  approveEvent,
  getEvent,
  rejectEvent,
  saveEvent,
  type EventRecord,
} from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  approveEvent: vi.fn(),
  getEvent: vi.fn(),
  rejectEvent: vi.fn(),
  saveEvent: vi.fn(),
}))

// US14.1: the venue bookings card loads its own data. These tests are not about
// it, so it gets no bookings and an empty catalogue. The empty answers are the
// mocks' own implementations rather than a beforeEach, because the card mounts
// only once the event has loaded and its effect can run after this file's
// resetAllMocks; a reset restores an implementation given to vi.fn.
vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(async () => []),
}))

const getEventMock = vi.mocked(getEvent)
const approveEventMock = vi.mocked(approveEvent)
const rejectEventMock = vi.mocked(rejectEvent)
const saveEventMock = vi.mocked(saveEvent)

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })
const editingCoordinator = buildSession({
  role: 'Event Coordinator',
  id: '2',
  name: 'Priya',
  permissions: [...coordinator.permissions, 'events:edit'],
})
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

function reviewed(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Faculty Welcome Night',
    purpose: 'Welcome the new intake.',
    description: 'Talks.',
    startsAt: '2027-11-02T18:00',
    endsAt: '2027-11-02T21:00',
    expectedAttendance: 120,
    status: 'Under Review',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-09-08T10:00:00',
    updatedAt: '2026-09-08T10:05:00',
    history: [
      { from: null, to: 'Draft', at: '2026-09-08T10:00:00', byId: '1', byName: 'Dylan' },
      {
        from: 'Submitted',
        to: 'Under Review',
        at: '2026-09-08T10:05:00',
        byId: '2',
        byName: 'Priya',
        notes: 'Please clarify.',
      },
    ],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

afterEach(() => {
  vi.resetAllMocks()
})

it('offers approval and rejection only for an Under Review event', async () => {
  getEventMock.mockResolvedValue(reviewed())

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Review decision' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve event' })).toBeInTheDocument()
  expect(screen.getByLabelText('Reason for rejection')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reject event' })).toBeDisabled()
})

it.each(['Submitted', 'Approved', 'Rejected'] as const)(
  'does not offer decision controls when status is %s',
  async (status) => {
    getEventMock.mockResolvedValue(reviewed({ status }))

    render(<EventDetailPage eventId="101" session={coordinator} />)

    await screen.findByText('Faculty Welcome Night')
    expect(screen.queryByRole('heading', { name: 'Review decision' })).not.toBeInTheDocument()
  },
)

it('does not offer decision controls to the Organiser', async () => {
  getEventMock.mockResolvedValue(reviewed())

  render(<EventDetailPage eventId="101" session={organiser} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('heading', { name: 'Review decision' })).not.toBeInTheDocument()
})

it('approves and replaces the page with the returned event', async () => {
  getEventMock.mockResolvedValue(reviewed())
  approveEventMock.mockResolvedValue(reviewed({ status: 'Approved' }))

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Approve event' }))

  await waitFor(() => expect(approveEventMock).toHaveBeenCalledWith('101', coordinator))
  expect(await screen.findByText(/Approved\. The status change has been recorded/)).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Review decision' })).not.toBeInTheDocument()
})

it('trims and sends a rejection reason', async () => {
  const rejected = reviewed({
    status: 'Rejected',
    history: [
      ...reviewed().history,
      {
        from: 'Under Review',
        to: 'Rejected',
        at: '2026-09-08T10:06:00',
        byId: '2',
        byName: 'Priya',
        notes: 'No capacity.',
      },
    ],
  })
  getEventMock.mockResolvedValue(reviewed())
  rejectEventMock.mockResolvedValue(rejected)

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await userEvent.type(await screen.findByLabelText('Reason for rejection'), '  No capacity.  ')
  await userEvent.click(screen.getByRole('button', { name: 'Reject event' }))

  await waitFor(() =>
    expect(rejectEventMock).toHaveBeenCalledWith('101', 'No capacity.', coordinator),
  )
  expect(await screen.findByText('Rejection reason')).toBeInTheDocument()
  expect(screen.getByText('No capacity.')).toBeInTheDocument()
})

it('retains the rejection reason when the server refuses it', async () => {
  getEventMock.mockResolvedValue(reviewed())
  rejectEventMock.mockRejectedValue(
    new EventRuleError('Only an event that is Under Review can be decided.'),
  )

  render(<EventDetailPage eventId="101" session={coordinator} />)
  const field = await screen.findByLabelText('Reason for rejection')
  await userEvent.type(field, 'Keep this reason')
  await userEvent.click(screen.getByRole('button', { name: 'Reject event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/only an event that is under review/i)
  expect(field).toHaveValue('Keep this reason')
})

it('reports an unreachable API without losing the decision controls', async () => {
  getEventMock.mockResolvedValue(reviewed())
  approveEventMock.mockRejectedValue(new TypeError('Failed to fetch'))

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Approve event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/API could not be reached/i)
  expect(screen.getByRole('heading', { name: 'Review decision' })).toBeInTheDocument()
})

it('locks decision controls while an event save is pending', async () => {
  const pendingSave = deferred<EventRecord>()
  getEventMock.mockResolvedValue(reviewed())
  saveEventMock.mockReturnValue(pendingSave.promise)
  const user = userEvent.setup()

  render(<EventDetailPage eventId="101" session={editingCoordinator} />)
  await user.type(await screen.findByLabelText('Title'), ' updated')
  await user.click(screen.getByRole('button', { name: 'Save changes' }))
  await waitFor(() => expect(saveEventMock).toHaveBeenCalledOnce())

  expect(screen.getByRole('button', { name: 'Approve event' })).toBeDisabled()
  expect(screen.getByLabelText('Reason for rejection')).toBeDisabled()

  await act(async () => {
    pendingSave.resolve(reviewed({ title: 'Faculty Welcome Night updated' }))
    await pendingSave.promise
  })
})

it('locks event editing and saving while a decision is pending', async () => {
  const pendingDecision = deferred<EventRecord>()
  getEventMock.mockResolvedValue(reviewed())
  approveEventMock.mockReturnValue(pendingDecision.promise)
  const user = userEvent.setup()

  render(<EventDetailPage eventId="101" session={editingCoordinator} />)
  const title = await screen.findByLabelText('Title')
  await user.type(title, ' updated')
  const saveButton = screen.getByRole('button', { name: 'Save changes' })
  expect(saveButton).toBeEnabled()

  await user.click(screen.getByRole('button', { name: 'Approve event' }))
  await waitFor(() => expect(approveEventMock).toHaveBeenCalledOnce())

  expect(title).toBeDisabled()
  expect(saveButton).toBeDisabled()

  await act(async () => {
    pendingDecision.resolve(reviewed({ status: 'Approved' }))
    await pendingDecision.promise
  })
})

it('shows the Organiser the labelled rejection reason', async () => {
  getEventMock.mockResolvedValue(
    reviewed({
      status: 'Rejected',
      history: [
        ...reviewed().history,
        {
          from: 'Under Review',
          to: 'Rejected',
          at: '2026-09-08T10:06:00',
          byId: '2',
          byName: 'Priya',
          notes: 'The safety plan is incomplete.',
        },
      ],
    }),
  )

  render(<EventDetailPage eventId="101" session={organiser} />)

  expect(await screen.findByText('Rejection reason')).toBeInTheDocument()
  expect(screen.getByText('The safety plan is incomplete.')).toBeInTheDocument()
})
