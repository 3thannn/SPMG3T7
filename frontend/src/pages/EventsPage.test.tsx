/**
 * What the list page renders, given what the API returns.
 *
 * Visibility itself — an Organiser seeing only their own events, a Coordinator
 * seeing every one — moved to the server with US6.3 and is tested there, in
 * backend/tests/test_events.py. What is still this page's job is showing a
 * status on every row, naming the organiser when the viewer is a Coordinator,
 * and saying something useful when there is nothing to show.
 */

import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import EventsPage from './EventsPage'
import { listEvents, type EventRecord } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listEvents: vi.fn(),
}))

const listEventsMock = vi.mocked(listEvents)

afterEach(() => {
  vi.resetAllMocks()
})

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

const coordinator = buildSession({
  role: 'Event Coordinator',
  id: '9',
  name: 'Ethan',
  email: 'ethan@example.edu',
})

function buildEvent(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Mine',
    purpose: '',
    description: '',
    startsAt: '2026-11-02T18:00',
    expectedAttendance: null,
    status: 'Draft',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-09-08T10:00:00',
    updatedAt: '2026-09-08T10:00:00',
    history: [],
    ...overrides,
  }
}

it('shows a status badge on every event in the list', async () => {
  listEventsMock.mockResolvedValue([buildEvent()])

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('Mine')).toBeInTheDocument()
  expect(screen.getByText('Draft')).toBeInTheDocument()
})

it('labels an untitled and undated draft without inventing stored details', async () => {
  listEventsMock.mockResolvedValue([buildEvent({ title: '---', startsAt: '' })])

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('Untitled event')).toBeInTheDocument()
  expect(screen.getByText('Not set')).toBeInTheDocument()
})

it('names the organiser for a Coordinator, who is looking across owners', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent(),
    buildEvent({ id: '102', title: 'Theirs', organiserId: '2', organiserName: 'Ariel' }),
  ])

  render(<EventsPage session={coordinator} />)

  expect(await screen.findByText('Mine')).toBeInTheDocument()
  expect(screen.getByText('Theirs')).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Ariel/)).toBeInTheDocument()
})

it('asks the API without telling it which role is asking', async () => {
  listEventsMock.mockResolvedValue([])

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('No events yet')).toBeInTheDocument()
  expect(listEventsMock).toHaveBeenCalledWith(organiser)
})

it('tells an Organiser with no events what to do next', async () => {
  listEventsMock.mockResolvedValue([])

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('No events yet')).toBeInTheDocument()
})

it('says the list could not be loaded rather than showing "no events"', async () => {
  // An empty list and an unreachable API mean very different things to the
  // person reading the page.
  listEventsMock.mockRejectedValue(new Error('network down'))

  render(<EventsPage session={organiser} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not load your events/i)
  expect(screen.queryByText('No events yet')).not.toBeInTheDocument()
})
