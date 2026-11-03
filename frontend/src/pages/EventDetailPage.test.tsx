import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  getEvent,
  saveEvent,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import { buildSession } from '../test/sessions'
import { ANSWERED_NEEDS } from '../test/eventNeeds'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  getEvent: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
  completeEvent: vi.fn(),
  // US4.6: cancelling from the page.
  cancelEvent: vi.fn(),
  // US4.4: the safety check panel loads its own readiness.
  getSafetyReadiness: vi.fn(async () => ({ ready: true, reason: '', message: '' })),
  sendForSafetyCheck: vi.fn(),
  approveSafetyCheck: vi.fn(),
  // US17.1: the Safety Officer's review loads its own data; left pending here.
  getSafetyReview: vi.fn(() => new Promise(() => {})),
  // US17.2: the panel reads the earlier decisions. None, unless a test says so.
  listSafetyDecisions: vi.fn(async () => []),
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

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEventEquipmentRequests: vi.fn(async () => []),
  listEquipment: vi.fn(async () => []),
}))

// US20.1: the registration card loads its own settings. Off, as on a new event,
// for the same reason the cards above get empty answers.
vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  getRegistrationSettings: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    defaultCapacity: 20,
  })),
  // US20.3: and, for the Organiser and the assigned Coordinator, who registered.
  listEventRegistrations: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    registrations: [],
  })),
}))

const getEventMock = vi.mocked(getEvent)

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

// Fixture events are dated November 2026. Against the real clock they would
// start failing as "in the past" once those days went by, so today is pinned
// before all of them. Only Date is faked: timers stay real for user-event.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-01T09:00:00') })
})

afterEach(() => {
  vi.useRealTimers()
  vi.resetAllMocks()
})

const coordinator = buildSession({ role: 'Event Coordinator', id: '9', name: 'Priya' })

const submittedEvent: EventRecord = {
  id: '101',
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks.',
  startsAt: '2026-11-02T18:00',
  expectedAttendance: 120,
  status: 'Submitted',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:05:00',
  history: [
    { from: null, to: 'Draft', at: '2026-09-08T10:00:00', byId: '1', byName: 'Dylan' },
    { from: 'Draft', to: 'Submitted', at: '2026-09-08T10:05:00', byId: '1', byName: 'Dylan' },
  ],
}

it('shows every captured field as read-only text to a Coordinator', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Faculty Welcome Night')).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Dylan/)).toBeInTheDocument()
  expect(screen.getByText('Welcome the new intake.')).toBeInTheDocument()
  expect(screen.getByText('Talks.')).toBeInTheDocument()
  expect(screen.getByText('120 people')).toBeInTheDocument()
})

// --- US5.3: a Confirmed event's details are locked -------------------------------

describe('US5.3: a Confirmed event is locked', () => {
  // The server gives Coordinators events:edit (US5.2); test/sessions.ts does not
  // yet, so these tests add it.
  const editor = { ...coordinator, permissions: [...coordinator.permissions, 'events:edit' as const] }
  const confirmedEvent = {
    ...submittedEvent,
    status: 'Confirmed' as const,
    coordinatorId: coordinator.id,
    endsAt: '2099-01-01T17:00',
  }

  it('shows a Coordinator the details read-only, with no Save, and says why', async () => {
    getEventMock.mockResolvedValue(confirmedEvent)

    render(<EventDetailPage eventId="101" session={editor} />)

    expect(
      await screen.findByText(
        'This event is confirmed. Changes need to go through a change request. The Organiser requests them, and you review them here.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    expect(screen.queryByText(/You are editing this event/)).not.toBeInTheDocument()
  })

  it('points the Organiser to a change request', async () => {
    getEventMock.mockResolvedValue(confirmedEvent)

    render(<EventDetailPage eventId="101" session={organiser} />)

    expect(
      await screen.findByText(
        'This event is confirmed. Changes need to go through a change request. Request changes and the Coordinator will review them.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeInTheDocument()
  })
})

// D2 (CODE_AUDIT.md): "Rejected events may be resubmitted after appropriate
// changes are made" (Week 4 customer answers).
describe('D2: a Rejected event can be revised and resubmitted', () => {
  const rejected: EventRecord = {
    ...submittedEvent,
    ...ANSWERED_NEEDS,
    endsAt: '2026-11-02T21:00',
    status: 'Rejected',
  }

  it('lets the owner edit it and resubmit it', async () => {
    getEventMock.mockResolvedValue(rejected)
    vi.mocked(saveEvent).mockResolvedValue(rejected)
    vi.mocked(submitEvent).mockResolvedValue({ ...rejected, status: 'Submitted' })
    const user = userEvent.setup()
    render(<EventDetailPage eventId="101" session={organiser} />)

    const title = await screen.findByLabelText('Title')
    await user.clear(title)
    await user.type(title, 'Welcome Night')
    await user.click(screen.getByRole('button', { name: 'Resubmit event' }))

    await waitFor(() => expect(vi.mocked(submitEvent)).toHaveBeenCalledWith('101', organiser))
    expect(vi.mocked(saveEvent).mock.calls[0][1]).toMatchObject({ title: 'Welcome Night' })
  })

  it('gives a Coordinator nothing to resubmit', async () => {
    getEventMock.mockResolvedValue({ ...rejected, organiserId: '1' })
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('button', { name: 'Resubmit event' })).not.toBeInTheDocument()
  })
})
