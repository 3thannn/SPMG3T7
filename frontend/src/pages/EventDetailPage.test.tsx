// New file — added for SPMG3T7-33 (US5.1)
/**
 * What the detail page shows a viewer who does not own the event — US5.1
 * (SPMG3T7-33): a Coordinator opens a submitted event and sees every captured field,
 * read-only.
 *
 * Ownership and the server's visibility rule are already covered in
 * backend/tests/test_events.py. What is this page's job is rendering every
 * field as plain text, with no inputs or edit/submit actions, when the
 * viewer is not the owning Organiser.
 */

import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import { getEvent, type EventRecord } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getEvent: vi.fn(),
}))

const getEventMock = vi.mocked(getEvent)

afterEach(() => {
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

it('does not render a Draft if an invalid API response returns one to a Coordinator', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Draft' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Not available for your role')).toBeInTheDocument()
  expect(screen.queryByText('Faculty Welcome Night')).not.toBeInTheDocument()
})

it('offers no inputs or edit actions to a Coordinator, who does not own the event', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /save draft/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /submit event/i })).not.toBeInTheDocument()
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
