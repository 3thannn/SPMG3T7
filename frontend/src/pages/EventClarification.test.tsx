/**
 * US7.3 on the event detail page — requesting clarification, and reading it.
 *
 * Who may ask, and whether the status is allowed to move, are the server's call
 * and are tested in backend/tests/test_event_clarification.py. What is this
 * page's job is offering the form to the right role, sending what was typed,
 * and — the half that makes the feature worth anything — showing the message to
 * the Organiser it was written for.
 */

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


afterEach(() => {
  vi.resetAllMocks()
})

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })



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

// --- the Organiser reads it -------------------------------------------------

it('shows the request to the Organiser it was written for', async () => {
  getEventMock.mockResolvedValue(withRequest())

  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByText('Faculty Welcome Night')

  expect(screen.getByText(MESSAGE)).toBeInTheDocument()
})
