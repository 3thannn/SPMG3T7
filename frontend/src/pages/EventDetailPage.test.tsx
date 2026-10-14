import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import { completeEvent, getEvent, listBookings, saveEvent, submitEvent, type EventRecord } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  getEvent: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
  completeEvent: vi.fn(),
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

const getEventMock = vi.mocked(getEvent)
const saveEventMock = vi.mocked(saveEvent)
const submitEventMock = vi.mocked(submitEvent)
const completeEventMock = vi.mocked(completeEvent)
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

const event: EventRecord = {
  id: '101',
  title: 'Working title',
  purpose: 'Purpose',
  description: 'Notes',
  startsAt: '2026-11-02T18:00',
  endsAt: undefined,
  expectedAttendance: 20,
  status: 'Draft',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:00:00',
  history: [],
}

afterEach(() => {
  vi.resetAllMocks()
})

it('saves a description-only edit without trimming its whitespace', async () => {
  const user = userEvent.setup()
  const saved = {
    ...event,
    title: '',
    purpose: '',
    description: '  Continue planning here.  ',
    startsAt: '',
    expectedAttendance: null,
  }
  getEventMock.mockResolvedValue(event)
  saveEventMock.mockResolvedValue(saved)

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.clear(await screen.findByLabelText('Title'))
  await user.clear(screen.getByLabelText('Purpose'))
  await user.clear(screen.getByLabelText('Description'))
  await user.clear(screen.getByLabelText('Starts'))
  await user.clear(screen.getByLabelText('Expected attendance'))
  await user.type(screen.getByLabelText('Description'), '  Continue planning here.  ')
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(saveEventMock).toHaveBeenCalled())
  expect(saveEventMock).toHaveBeenCalledWith(
    '101',
    {
      title: '',
      purpose: '',
      description: '  Continue planning here.  ',
      startsAt: '',
      endsAt: null,
      expectedAttendance: null,
    },
    organiser,
  )
})

it('rejects punctuation-only edits as an empty draft', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({
    ...event,
    title: '',
    purpose: '',
    description: '',
    startsAt: '',
    expectedAttendance: null,
  })

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.type(await screen.findByLabelText('Description'), '---')
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/at least one letter or number/i)
  expect(saveEventMock).not.toHaveBeenCalled()
})

it('keeps submission strict for a titleless partial draft', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({
    ...event,
    title: '',
    description: 'Planning notes',
  })

  render(<EventDetailPage eventId="101" session={organiser} />)

  expect(await screen.findByRole('heading', { name: 'Untitled event' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Submit event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the event a title.')
  expect(saveEventMock).not.toHaveBeenCalled()
  expect(submitEventMock).not.toHaveBeenCalled()
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

it('does not render a Draft if an invalid API response returns one to a Coordinator', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Draft' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Not available for your role')).toBeInTheDocument()
  expect(screen.queryByText('Faculty Welcome Night')).not.toBeInTheDocument()
})

it('offers no edit actions to a Coordinator, who does not own the event', async () => {
  // Narrowed by US7.3: a Coordinator does now get one input on this page, the
  // clarification box. What they still cannot do is edit or submit the event.
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('button', { name: /save draft/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /submit event/i })).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/^title$/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/^purpose$/i)).not.toBeInTheDocument()
  expect(
    screen.getByText(/only the owning Organiser can edit or submit it/i),
  ).toBeInTheDocument()
})

it('shows the full status history, not just the current status', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.getByText('Created as')).toBeInTheDocument()
  expect(screen.getAllByText('Submitted').length).toBeGreaterThan(0)
})

it.each([coordinator, organiser])('keeps status history about event transitions for %s', async (session) => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Planning', coordinatorId: coordinator.id })
  render(<EventDetailPage eventId="101" session={session} />)
  expect(await screen.findByRole('heading', { name: 'Status history' })).toBeInTheDocument()
  expect(screen.getByText('Event status transitions and requested changes.')).toBeInTheDocument()
  const entries = document.querySelectorAll('ol.timeline > li')
  expect(entries[0]).toHaveTextContent('Created as')
  expect(entries[0]).toHaveTextContent('Status: Draft')
  expect(screen.queryByText(/Microphone request/)).not.toBeInTheDocument()
})

it('shows the venue bookings for a submitted event under its details (US14.1)', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Venue bookings' })).toBeInTheDocument()
  await waitFor(() => expect(vi.mocked(listBookings)).toHaveBeenCalledWith('101', coordinator))
})

it('shows no venue bookings card on a Draft, which cannot have any', async () => {
  getEventMock.mockResolvedValue(event)

  render(<EventDetailPage eventId="101" session={organiser} />)

  await screen.findByLabelText('Title')
  expect(screen.queryByRole('heading', { name: 'Venue bookings' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Equipment requests' })).not.toBeInTheDocument()
  expect(vi.mocked(listBookings)).not.toHaveBeenCalled()
})

it('lets the assigned Coordinator complete an ended Confirmed event', async () => {
  const user = userEvent.setup()
  const confirmed = {
    ...submittedEvent, status: 'Confirmed' as const,
    coordinatorId: coordinator.id, endsAt: '2020-01-01T17:00',
  }
  getEventMock.mockResolvedValue(confirmed)
  completeEventMock.mockResolvedValue({ ...confirmed, status: 'Completed' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Mark Completed' }))
  expect(completeEventMock).toHaveBeenCalledWith('101', coordinator)
  expect(await screen.findByRole('status')).toHaveTextContent('Completed.')
  expect(screen.queryByRole('button', { name: 'Mark Completed' })).not.toBeInTheDocument()
})

it('does not offer completion before the end time or to another Coordinator', async () => {
  const future = {
    ...submittedEvent, status: 'Confirmed' as const,
    coordinatorId: coordinator.id, endsAt: '2099-01-01T17:00',
  }
  getEventMock.mockResolvedValue(future)
  const view = render(<EventDetailPage eventId="101" session={coordinator} />)
  expect(await screen.findByRole('button', { name: 'Mark Completed' })).toBeDisabled()

  view.unmount()
  getEventMock.mockResolvedValue({ ...future, coordinatorId: 'someone-else' })
  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('button', { name: 'Mark Completed' })).not.toBeInTheDocument()
})
