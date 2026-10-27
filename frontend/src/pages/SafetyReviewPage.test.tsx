import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import SafetyReviewPage from './SafetyReviewPage'
import { listSafetyQueue, type EventRecord } from '../eventsStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listSafetyQueue: vi.fn(),
}))

const queueMock = vi.mocked(listSafetyQueue)
const officer = buildSession({ role: 'Safety Officer', id: '5', name: 'Alex' })

function waiting(id: string, overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id,
    title: `Event ${id}`,
    purpose: 'Purpose',
    description: '',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    expectedAttendance: 30,
    status: 'Pending Safety Check',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2099-01-01T09:00:00',
    updatedAt: '2099-01-01T09:00:00',
    coordinatorId: '2',
    history: [],
    ...overrides,
  }
}

afterEach(() => {
  vi.resetAllMocks()
  window.location.hash = ''
})

it('lists the events waiting for sign-off, in the order the server sends them', async () => {
  queueMock.mockResolvedValue([
    waiting('2', {
      history: [
        { from: 'Planning', to: 'Pending Safety Check', at: '2099-01-02T09:00:00', byId: '2', byName: 'Priya' },
        { from: 'Pending Safety Check', to: 'Planning', at: '2099-01-02T10:00:00', byId: '5', byName: 'Alex' },
        { from: 'Planning', to: 'Pending Safety Check', at: '2099-01-03T09:00:00', byId: '2', byName: 'Priya' },
      ],
    }),
    waiting('1', { title: '', startsAt: '', expectedAttendance: null }),
  ])

  render(<SafetyReviewPage session={officer} />)

  expect(screen.getByRole('heading', { name: 'Safety Review' })).toBeInTheDocument()
  expect(screen.getByText('Loading the safety review queue…')).toBeInTheDocument()
  const list = await screen.findByRole('list', { name: 'Events pending safety check' })
  const items = within(list).getAllByRole('listitem')
  expect(items).toHaveLength(2)

  // Waiting since the most recent time it was sent.
  expect(within(items[0]).getByRole('link', { name: 'Event 2' })).toHaveAttribute('href', '#/events/2')
  expect(items[0]).toHaveTextContent('Waiting since: 03 Jan 2099, 17:00')
  expect(within(items[0]).getByText('2', { selector: '.safety-date-day' })).toBeInTheDocument()
  expect(within(items[0]).getByText('Nov', { selector: '.safety-date-month' })).toBeInTheDocument()
  expect(
    within(items[0]).getByText('09:00 AM', { selector: '.safety-date-time' }),
  ).toBeInTheDocument()
  expect(items[0]).toHaveTextContent('Expected attendance: 30 people')
  expect(within(items[0]).getByText('Pending Safety Check')).toBeInTheDocument()

  // No entry for the move: falls back to when the event last changed.
  expect(items[1]).toHaveTextContent('Waiting since: 01 Jan 2099, 17:00')
  expect(within(items[1]).getByText('TBD')).toBeInTheDocument()
  expect(items[1]).toHaveTextContent('Expected attendance: Not estimated')
  expect(queueMock).toHaveBeenCalledWith(officer)
})

it('opens an event from the queue', async () => {
  const user = userEvent.setup()
  queueMock.mockResolvedValue([waiting('7')])

  render(<SafetyReviewPage session={officer} />)
  await user.click(await screen.findByRole('link', { name: 'Event 7' }))

  expect(window.location.hash).toBe('#/events/7')
})

it('says when nothing is waiting', async () => {
  queueMock.mockResolvedValue([])

  render(<SafetyReviewPage session={officer} />)

  expect(
    await screen.findByRole('heading', { name: 'No events waiting for a safety check' }),
  ).toBeInTheDocument()
})

it('says when the queue cannot be loaded', async () => {
  queueMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))

  render(<SafetyReviewPage session={officer} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /^Could not load the safety review queue\./,
  )
})

it('ignores an answer that arrives after the page has gone', async () => {
  let resolve!: (events: EventRecord[]) => void
  queueMock.mockReturnValue(new Promise((res) => (resolve = res)))
  const first = render(<SafetyReviewPage session={officer} />)
  first.unmount()
  resolve([waiting('1')])

  let reject!: (error: unknown) => void
  const failing = new Promise<EventRecord[]>((_res, rej) => (reject = rej))
  queueMock.mockReturnValue(failing)
  const second = render(<SafetyReviewPage session={officer} />)
  second.unmount()
  reject(new Error('gone'))
  await expect(failing).rejects.toThrow('gone')
})
