/**
 * Event page paths EventDetailPage.test.tsx does not reach: US8.4 reassignment
 * by the Coordinator Lead, US4.5 completion failing, the event refreshed after
 * a US14.1 booking request, and the save and submit refusals the browser
 * catches before anything is sent.
 *
 * The cards the page hosts load their own data and have their own tests, so
 * here they are stand-ins: the bookings card can announce a request, and the
 * cancel panel can report a failure, which is all the page reacts to.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  EventRuleError,
  completeEvent,
  getEvent,
  recheckArrangements,
  saveEvent,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import { listCoordinators, reassignCoordinator } from '../unassignedQueueStore'
import { ApiError } from '../api'
import { ANSWERED_NEEDS } from '../test/eventNeeds'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getEvent: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
  completeEvent: vi.fn(),
  recheckArrangements: vi.fn(),
}))

vi.mock('../unassignedQueueStore', () => ({
  listCoordinators: vi.fn(),
  reassignCoordinator: vi.fn(),
}))

vi.mock('../components/EventBookings', () => ({
  default: ({ onBookingRequested }: { onBookingRequested?: () => void }) => (
    <button type="button" onClick={() => onBookingRequested?.()}>
      Stand-in: a venue was requested
    </button>
  ),
}))

vi.mock('../components/CancelEventPanel', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../components/CancelEventPanel')>()),
  default: ({ onError }: { onError: (message: string) => void }) => (
    <button type="button" onClick={() => onError('Could not cancel the event.')}>
      Stand-in: cancelling failed
    </button>
  ),
}))

vi.mock('../components/EventEquipment', () => ({ default: () => null }))
vi.mock('../components/EventRegistration', () => ({ default: () => null }))
vi.mock('../components/SafetyCheckPanel', () => ({ default: () => null }))
vi.mock('../components/SafetyReviewDetails', () => ({ default: () => null }))

const getEventMock = vi.mocked(getEvent)
const saveEventMock = vi.mocked(saveEvent)
const submitEventMock = vi.mocked(submitEvent)
const completeEventMock = vi.mocked(completeEvent)
const listCoordinatorsMock = vi.mocked(listCoordinators)
const reassignMock = vi.mocked(reassignCoordinator)

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })
const lead = buildSession({ role: 'Event Coordinator Lead', id: '3', name: 'Jordan' })

const DRAFT: EventRecord = {
  id: '101',
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks.',
  startsAt: '2026-11-02T18:00',
  endsAt: '2026-11-02T21:00',
  expectedAttendance: 120,
  status: 'Draft',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:00:00',
  history: [],
  ...ANSWERED_NEEDS,
}

const ASSIGNED: EventRecord = {
  ...DRAFT,
  status: 'Under Review',
  coordinatorId: '2',
  coordinatorName: 'Priya Nair',
}

const COORDINATORS = [
  { id: '2', name: 'Priya Nair', email: 'priya@spmg3t7.edu' },
  { id: '9', name: 'Sam Tan', email: 'sam@spmg3t7.edu' },
]

// Fixture events are dated November 2026; today is pinned before them, as in
// EventDetailPage.test.tsx. Only Date is faked, so user-event's timers stay real.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-01T09:00:00') })
})

afterEach(() => {
  vi.useRealTimers()
  vi.resetAllMocks()
})

it('ignores an event that arrives after the page has gone', async () => {
  let arrive!: (event: EventRecord) => void
  getEventMock.mockReturnValue(new Promise((resolve) => (arrive = resolve)))
  const { unmount } = render(<EventDetailPage eventId="101" session={organiser} />)

  unmount()
  arrive(DRAFT)
  await Promise.resolve()

  expect(getEventMock).toHaveBeenCalledTimes(1)
})

describe('US8.4 — the Lead reassigns an event', () => {
  async function openModal() {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(ASSIGNED)
    listCoordinatorsMock.mockResolvedValue(COORDINATORS)
    render(<EventDetailPage eventId="101" session={lead} />)
    await user.click(await screen.findByRole('button', { name: 'Reassign Coordinator' }))
    await screen.findByText('Select a coordinator to reassign this event to:')
    return user
  }

  it('lists the coordinators by name, email and initials', async () => {
    await openModal()

    expect(await screen.findByText('sam@spmg3t7.edu')).toBeTruthy()
    expect(screen.getByText('ST')).toBeTruthy()
  })

  it('reassigns, reloads the event and says who has it now', async () => {
    const user = await openModal()
    reassignMock.mockResolvedValue()
    getEventMock.mockResolvedValue({ ...ASSIGNED, coordinatorId: '9', coordinatorName: 'Sam Tan' })

    await user.click(await screen.findByRole('button', { name: /Sam Tan/ }))

    expect(reassignMock).toHaveBeenCalledWith(lead, '101', '9')
    expect(
      await screen.findByText('Reassigned to Sam Tan. They can now access this event.'),
    ).toBeTruthy()
    expect(screen.queryByText('Select a coordinator to reassign this event to:')).toBeNull()
  })

  it('closes quietly when the event cannot be read back', async () => {
    const user = await openModal()
    reassignMock.mockResolvedValue()
    getEventMock.mockResolvedValue(null)

    await user.click(await screen.findByRole('button', { name: /Sam Tan/ }))

    await waitFor(() =>
      expect(screen.queryByText('Select a coordinator to reassign this event to:')).toBeNull(),
    )
    expect(screen.queryByText(/Reassigned to/)).toBeNull()
  })

  it('says why a reassignment failed and keeps the list open', async () => {
    const user = await openModal()
    reassignMock.mockRejectedValue(new ApiError('Internal error', 'unknown', 500))

    await user.click(await screen.findByRole('button', { name: /Sam Tan/ }))

    expect(
      await screen.findByText(
        'Could not reassign coordinator. The API answered HTTP 500 — check the backend log for the cause.',
      ),
    ).toBeTruthy()
    expect(screen.getByText('Select a coordinator to reassign this event to:')).toBeTruthy()
  })

  it('shows the server’s reason when a reassignment is refused', async () => {
    const user = await openModal()
    reassignMock.mockRejectedValue(
      new EventRuleError('This event was changed since you opened it. Reload and try again.'),
    )

    await user.click(await screen.findByRole('button', { name: /Sam Tan/ }))

    expect(
      await screen.findByText('This event was changed since you opened it. Reload and try again.'),
    ).toBeTruthy()
  })

  it.each(['Completed', 'Cancelled', 'Rejected'] as const)(
    'does not offer to reassign a %s event',
    async (status) => {
      getEventMock.mockResolvedValue({ ...ASSIGNED, status })
      render(<EventDetailPage eventId="101" session={lead} />)

      await screen.findByText(ASSIGNED.title)
      expect(screen.queryByRole('button', { name: 'Reassign Coordinator' })).toBeNull()
    },
  )

  it('does not open when the coordinators cannot be loaded', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(ASSIGNED)
    listCoordinatorsMock.mockRejectedValue(new TypeError('Failed to fetch'))
    render(<EventDetailPage eventId="101" session={lead} />)

    await user.click(await screen.findByRole('button', { name: 'Reassign Coordinator' }))

    expect(
      await screen.findByText(
        'Could not load coordinators. The API could not be reached; check it is running and try again.',
      ),
    ).toBeTruthy()
    expect(screen.queryByText('Select a coordinator to reassign this event to:')).toBeNull()
  })

  it.each([
    ['the close button', (user: ReturnType<typeof userEvent.setup>) =>
      user.click(screen.getByRole('button', { name: 'Close' }))],
    ['Cancel', (user: ReturnType<typeof userEvent.setup>) =>
      user.click(screen.getByRole('button', { name: 'Cancel' }))],
    ['a click outside it', (user: ReturnType<typeof userEvent.setup>) =>
      user.click(document.querySelector('.modal-overlay')!)],
  ])('closes from %s, and not from a click inside it', async (_how, close) => {
    const user = await openModal()

    await user.click(screen.getByText('Select a coordinator to reassign this event to:'))
    expect(screen.getByText('Select a coordinator to reassign this event to:')).toBeTruthy()

    await close(user)

    expect(screen.queryByText('Select a coordinator to reassign this event to:')).toBeNull()
    expect(reassignMock).not.toHaveBeenCalled()
  })
})

describe('US4.5 — completing an event that has ended', () => {
  const ENDED: EventRecord = {
    ...ASSIGNED,
    status: 'Confirmed',
    startsAt: '2026-09-01T09:00',
    endsAt: '2026-09-01T17:00',
  }

  it.each([
    [new EventRuleError('This event has already been completed.'), 'This event has already been completed.'],
    [
      new ApiError('Internal error', 'unknown', 500),
      'Could not complete the event. The API answered HTTP 500 — check the backend log for the cause.',
    ],
  ])('says why it could not be completed: %s', async (error, message) => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(ENDED)
    completeEventMock.mockRejectedValue(error)
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Mark Completed' }))

    expect(await screen.findByText(message)).toBeTruthy()
  })
})

describe('US14.1 — after a venue is requested', () => {
  it('reloads the event, whose status the request may have moved', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Approved' })
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Planning' })
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Stand-in: a venue was requested' }))

    expect(await screen.findAllByText('Planning')).not.toHaveLength(0)
    expect(getEventMock).toHaveBeenCalledTimes(2)
  })

  it('keeps the page when the event cannot be read back', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Approved' })
    getEventMock.mockResolvedValueOnce(null)
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Stand-in: a venue was requested' }))

    await waitFor(() => expect(getEventMock).toHaveBeenCalledTimes(2))
    expect(screen.getAllByText('Approved')).not.toHaveLength(0)
  })

  it('US12.4 says so when a replacement sent a Confirmed event back to Planning', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Confirmed' })
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Planning' })
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Stand-in: a venue was requested' }))

    expect(
      await screen.findByText(
        'This event is back in Planning. The replacement venue needs Venue Staff’s approval and a new safety check, then you confirm the event again.',
      ),
    ).toBeTruthy()
  })

  it('says the request was saved even when the refresh fails', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValueOnce({ ...ASSIGNED, status: 'Approved' })
    getEventMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Stand-in: a venue was requested' }))

    expect(
      await screen.findByText('The venue request was saved. Refresh to see the latest event status.'),
    ).toBeTruthy()
  })
})

describe('the Organiser saving and submitting a draft', () => {
  async function editDraft(field: string, value: string) {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(DRAFT)
    render(<EventDetailPage eventId="101" session={organiser} />)
    const input = await screen.findByLabelText(field)
    await user.clear(input)
    if (value) await user.type(input, value)
    return user
  }

  it('refuses an end before the start without sending it', async () => {
    const user = await editDraft('Ends', '2026-11-02T17:00')

    await user.click(screen.getByRole('button', { name: 'Save draft' }))

    expect(await screen.findByText('The end date must be after the start date.')).toBeTruthy()
    expect(saveEventMock).not.toHaveBeenCalled()
  })

  it('refuses an attendance that is not a whole number without sending it', async () => {
    const user = await editDraft('Expected attendance', '2.5')

    await user.click(screen.getByRole('button', { name: 'Save draft' }))

    expect(
      await screen.findByText('Enter a whole number for expected attendance, or leave it blank.'),
    ).toBeTruthy()
    expect(saveEventMock).not.toHaveBeenCalled()
  })

  it('says a save failed without blaming the Organiser', async () => {
    const user = await editDraft('Title', 'Faculty Welcome Evening')
    saveEventMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await user.click(screen.getByRole('button', { name: 'Save draft' }))

    expect(await screen.findByText('Could not save the event.')).toBeTruthy()
  })

  it('says a submission failed without blaming the Organiser', async () => {
    const user = await editDraft('Title', 'Faculty Welcome Evening')
    saveEventMock.mockResolvedValue(DRAFT)
    submitEventMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await user.click(screen.getByRole('button', { name: 'Submit event' }))

    expect(await screen.findByText('Could not submit the event.')).toBeTruthy()
  })
})

describe('US11.2 — the review trail and the arrangement checks', () => {
  const REVIEWED: EventRecord = {
    ...ASSIGNED,
    status: 'Planning',
    reviewHistory: [
      {
        revision: 1,
        kind: 'proposal',
        at: '2026-10-01T09:00:00',
        byId: '1',
        byName: '',
        message: 'More people are coming.',
        changes: [
          { changed_field: 'expected_attendance', old_value: '120', new_value: '150' },
          { field: 'name', oldValue: 'Old title', newValue: 'New title' },
        ],
      },
    ],
    arrangementReviewPending: true,
    arrangementReview: [
      { kind: 'venue', id: '1', label: 'Venue booking #1', reason: 'Too small now.', error: false },
    ],
  }

  it('lists each proposal with who made it and what it changes', async () => {
    getEventMock.mockResolvedValue(REVIEWED)
    render(<EventDetailPage eventId="101" session={coordinator} />)

    const trail = await screen.findByRole('region', { name: 'Change and clarification history' })

    expect(within(trail).getByText(/by User #1/)).toBeTruthy()
    expect(within(trail).getByText('More people are coming.')).toBeTruthy()
    expect(within(trail).getByText('expected_attendance: 120 to 150')).toBeTruthy()
    expect(within(trail).getByText('name: Old title to New title')).toBeTruthy()
  })

  it('rechecks the arrangements and shows the new result', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(REVIEWED)
    vi.mocked(recheckArrangements).mockResolvedValue({
      ...REVIEWED,
      arrangementReviewPending: false,
      arrangementReview: [
        { kind: 'venue', id: '1', label: 'Venue booking #1', reason: '', error: false },
      ],
    })
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Recheck arrangements' }))

    expect(recheckArrangements).toHaveBeenCalledWith('101', coordinator)
    expect(await screen.findByText(/Checks passed/)).toBeTruthy()
  })

  it('says when the recheck itself failed', async () => {
    const user = userEvent.setup()
    getEventMock.mockResolvedValue(REVIEWED)
    vi.mocked(recheckArrangements).mockRejectedValue(new TypeError('Failed to fetch'))
    render(<EventDetailPage eventId="101" session={coordinator} />)

    await user.click(await screen.findByRole('button', { name: 'Recheck arrangements' }))

    expect(
      await screen.findByText(
        'Could not recheck arrangements. The API could not be reached; check it is running and try again.',
      ),
    ).toBeTruthy()
  })
})

it('shows what the cancel panel reports going wrong', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue(ASSIGNED)
  render(<EventDetailPage eventId="101" session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Stand-in: cancelling failed' }))

  expect(await screen.findByText('Could not cancel the event.')).toBeTruthy()
})
