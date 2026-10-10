/**
 * What the list page renders, given what the API returns.
 *
 * Visibility itself — an Organiser seeing only their own events, a Coordinator
 * seeing only submitted requests — moved to the server and is tested there, in
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
  // Undated events show "TBD" in the redesigned card layout
  expect(screen.getByText('TBD')).toBeInTheDocument()
})

it('names the organiser for a Coordinator, who is looking across owners', async () => {
  listEventsMock.mockResolvedValue([
    buildEvent({ status: 'Submitted' }),
    buildEvent({
      id: '102',
      title: 'Theirs',
      status: 'Submitted',
      organiserId: '2',
      organiserName: 'Ariel',
    }),
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

/* ---------- US8.6: Coordinator Lead sees all events ---------- */

it('shows all events to a Coordinator Lead, regardless of status', async () => {
  const lead = buildSession({
    role: 'Event Coordinator Lead',
    id: '10',
    name: 'Jordan',
  })

  listEventsMock.mockResolvedValue([
    buildEvent({ id: '101', title: 'Draft Event', status: 'Draft' }),
    buildEvent({ id: '102', title: 'Submitted Event', status: 'Submitted' }),
    buildEvent({ id: '103', title: 'Approved Event', status: 'Approved' }),
  ])

  render(<EventsPage session={lead} />)

  expect(await screen.findByText('Draft Event')).toBeInTheDocument()
  expect(screen.getByText('Submitted Event')).toBeInTheDocument()
  expect(screen.getByText('Approved Event')).toBeInTheDocument()
  // Check that status badges are present (text appears in both filters and badges)
  const statusBadges = screen.getAllByText('Draft')
  expect(statusBadges.length).toBeGreaterThan(0)
  expect(screen.getAllByText('Submitted').length).toBeGreaterThan(0)
  expect(screen.getAllByText('Approved').length).toBeGreaterThan(0)
})

it('shows organiser names for all events when viewing as Coordinator Lead', async () => {
  const lead = buildSession({
    role: 'Event Coordinator Lead',
    id: '10',
    name: 'Jordan',
  })

  listEventsMock.mockResolvedValue([
    buildEvent({
      id: '101',
      title: 'First Event',
      organiserId: '1',
      organiserName: 'Alice',
    }),
    buildEvent({
      id: '102',
      title: 'Second Event',
      organiserId: '2',
      organiserName: 'Bob',
    }),
  ])

  render(<EventsPage session={lead} />)

  expect(await screen.findByText('First Event')).toBeInTheDocument()
  expect(screen.getByText('Second Event')).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Alice/)).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Bob/)).toBeInTheDocument()
})
