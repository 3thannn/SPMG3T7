import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  getEvent,
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

vi.mock('../components/EventEquipment', () => ({ default: () => null }))
vi.mock('../components/EventRegistration', () => ({ default: () => null }))

const getEventMock = vi.mocked(getEvent)

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })

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
