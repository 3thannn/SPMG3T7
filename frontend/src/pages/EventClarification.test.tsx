/**
 * US7.3 on the event detail page — requesting clarification, and reading it.
 *
 * Who may ask, and whether the status is allowed to move, are the server's call
 * and are tested in backend/tests/test_event_clarification.py. What is this
 * page's job is offering the form to the right role, sending what was typed,
 * and — the half that makes the feature worth anything — showing the message to
 * the Organiser it was written for.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  EventRuleError,
  getEvent,
  requestClarification,
  type EventRecord,
} from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  getEvent: vi.fn(),
  requestClarification: vi.fn(),
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

// US20.1: the registration card loads its own data and is not what these test.
vi.mock('../components/EventRegistration', () => ({ default: () => null }))

const getEventMock = vi.mocked(getEvent)
const requestClarificationMock = vi.mocked(requestClarification)

afterEach(() => {
  vi.resetAllMocks()
})

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const coordinator = buildSession({
  role: 'Event Coordinator',
  id: '2',
  name: 'Priya',
  email: 'priya@example.edu',
})
const venueStaff = buildSession({ role: 'Venue Staff', id: '3', name: 'Sam' })

const MESSAGE = 'Please confirm the catering budget.'

function buildEvent(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Faculty Welcome Night',
    purpose: 'Welcome the new intake.',
    description: 'Talks.',
    startsAt: '2026-11-02T18:00',
    expectedAttendance: 120,
    status: 'Submitted',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-01-01T09:00:00',
    updatedAt: '2026-01-02T09:00:00',
    history: [
      {
        from: null,
        to: 'Draft',
        at: '2026-01-01T09:00:00',
        byId: '1',
        byName: 'Dylan',
        notes: '',
      },
      {
        from: 'Draft',
        to: 'Submitted',
        at: '2026-01-02T09:00:00',
        byId: '1',
        byName: 'Dylan',
        notes: '',
      },
    ],
    ...overrides,
  }
}

/** The same event after a Coordinator has asked a question about it. */
function withRequest(message = MESSAGE): EventRecord {
  const base = buildEvent()
  return {
    ...base,
    status: 'Under Review',
    history: [
      ...base.history,
      {
        from: 'Submitted',
        to: 'Under Review',
        at: '2026-01-03T09:00:00',
        byId: '2',
        byName: 'Priya',
        notes: message,
      },
    ],
  }
}

// --- who is offered the form ------------------------------------------------

it('offers a Coordinator the request form on a submitted event', async () => {
  getEventMock.mockResolvedValue(buildEvent())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByRole('heading', { name: 'Request clarification' })).toBeInTheDocument()
  expect(screen.getByLabelText('What do you need from them?')).toBeInTheDocument()
})

it('does not offer the form to the Organiser, who answers rather than asks', async () => {
  // Their reply is US11.1, and is deliberately not this page.
  getEventMock.mockResolvedValue(buildEvent())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(
    screen.queryByRole('heading', { name: 'Request clarification' }),
  ).not.toBeInTheDocument()
})

it('offers it on an event already under review, so a second question is possible', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByLabelText('What do you need from them?')).toBeInTheDocument()
})

it('explains rather than offers when the event is already decided', async () => {
  getEventMock.mockResolvedValue(buildEvent({ status: 'Approved' }))

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText(/already been decided/)).toBeInTheDocument()
  expect(screen.queryByLabelText('What do you need from them?')).not.toBeInTheDocument()
})

// --- sending the request ----------------------------------------------------

it('sends what was typed', async () => {
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), MESSAGE)
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  await waitFor(() => {
    expect(requestClarificationMock).toHaveBeenCalledWith('101', MESSAGE, coordinator, undefined)
  })
})

it('will not send an empty request', async () => {
  getEventMock.mockResolvedValue(buildEvent())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByRole('button', { name: 'Send request' })).toBeDisabled()
})

it('will not send a request of only spaces', async () => {
  getEventMock.mockResolvedValue(buildEvent())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), '    ')

  expect(screen.getByRole('button', { name: 'Send request' })).toBeDisabled()
  expect(requestClarificationMock).not.toHaveBeenCalled()
})

it('trims the message rather than sending the spaces', async () => {
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(
    screen.getByLabelText('What do you need from them?'),
    `  ${MESSAGE}  `,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  await waitFor(() => {
    expect(requestClarificationMock).toHaveBeenCalledWith('101', MESSAGE, coordinator, undefined)
  })
})

it('says the request was sent and names the new status', async () => {
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), MESSAGE)
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  expect(await screen.findByText(/Request sent/)).toBeInTheDocument()
  expect(screen.getByText(/now Under Review/)).toBeInTheDocument()
})

it('clears the box once the request is away', async () => {
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), MESSAGE)
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  await waitFor(() => {
    expect(screen.getByLabelText('What do you need from them?')).toHaveValue('')
  })
})

it('keeps what was typed when the server refuses', async () => {
  // Otherwise a refusal costs the Coordinator the message they just wrote.
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockRejectedValue(
    new EventRuleError('This event has already been decided.'),
  )

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), MESSAGE)
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  expect(await screen.findByText('This event has already been decided.')).toBeInTheDocument()
  expect(screen.getByLabelText('What do you need from them?')).toHaveValue(MESSAGE)
})

it('says something useful when the request fails for another reason', async () => {
  getEventMock.mockResolvedValue(buildEvent())
  requestClarificationMock.mockRejectedValue(new Error('network down'))

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')

  await userEvent.type(screen.getByLabelText('What do you need from them?'), MESSAGE)
  await userEvent.click(screen.getByRole('button', { name: 'Send request' }))

  expect(await screen.findByText(/Could not send the request/)).toBeInTheDocument()
})

// --- the Organiser reads it -------------------------------------------------

it('shows the request to the Organiser it was written for', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText(MESSAGE)).toBeInTheDocument()
})

it('names it as a request rather than leaving it as loose text', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText('Requested by Coordinator')).toBeInTheDocument()
})

it('attributes the request to the Coordinator who asked', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText(/Priya/)).toBeInTheDocument()
})

it('shows the Organiser the event is now under review', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getAllByText('Under Review').length).toBeGreaterThan(0)
})

it('leaves automatic entries without a message block', async () => {
  // So a request is distinguishable from a plain status change.
  getEventMock.mockResolvedValue(buildEvent())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.queryByText('Requested by Coordinator')).not.toBeInTheDocument()
})

it('shows more than one request when a second question was asked', async () => {
  const twice = withRequest('First question.')
  getEventMock.mockResolvedValue({
    ...twice,
    history: [
      ...twice.history,
      {
        from: 'Under Review',
        to: 'Under Review',
        at: '2026-01-04T09:00:00',
        byId: '2',
        byName: 'Priya',
        notes: 'Second question.',
      },
    ],
  })

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText('First question.')).toBeInTheDocument()
  expect(screen.getByText('Second question.')).toBeInTheDocument()
})

// --- other roles ------------------------------------------------------------

it('shows Venue Staff none of this, since the event is not theirs to see', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={venueStaff} />)

  expect(await screen.findByText('Not available for your role')).toBeInTheDocument()
  expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument()
})
