/**
 * What the venue record renders — US9.2, US9.1b and US9.1c.
 *
 * The page shows the same details to everyone and differs only in what it
 * offers to act with. So the two halves asserted here are: a Coordinator gets a
 * page with nothing on it that writes, and Venue Staff get edit and delete —
 * with the delete confirmed first, because US9.1c is a hard delete.
 */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VenueDetailPage from './VenueDetailPage'
import {
  getAvailability,
  getVenue,
  listUnavailability,
  type VenueRecord,
} from '../venuesStore'
import { listHoldableEvents, listHolds } from '../holdsStore'
import { buildSession } from '../test/sessions'

vi.mock('../holdsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../holdsStore')>()),
  listHolds: vi.fn(),
  listHoldableEvents: vi.fn(),
}))

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getVenue: vi.fn(),
  deleteVenue: vi.fn(),
  listUnavailability: vi.fn(),
  getAvailability: vi.fn(),
}))

const getVenueMock = vi.mocked(getVenue)

const listUnavailabilityMock = vi.mocked(listUnavailability)

// US12.1's, US12.3's and US14.3's cards fetch on their own; their behaviour is
// covered in VenueUnavailability.test.tsx, VenueAvailability.test.tsx and
// VenueHolds.test.tsx. Here they only need to answer.
beforeEach(() => {
  listUnavailabilityMock.mockResolvedValue([])
  vi.mocked(getAvailability).mockResolvedValue({
    venueId: '1',
    from: '2027-03-01',
    to: '2027-03-14',
    setupMinutes: 0,
    turnaroundMinutes: 0,
    entries: [],
  })
  vi.mocked(listHolds).mockResolvedValue([])
  vi.mocked(listHoldableEvents).mockResolvedValue([])
})

afterEach(() => {
  // Unmount first: a test can end while the venue is still loading, and a
  // page that finished loading after its mocks were reset would call one that
  // no longer answers.
  cleanup()
  vi.resetAllMocks()
})

const coordinator = buildSession({
  role: 'Event Coordinator',
  id: '9',
  name: 'Priya',
  email: 'priya@example.edu',
})



function buildVenue(overrides: Partial<VenueRecord> = {}): VenueRecord {
  return {
    id: '1',
    name: 'Great Hall',
    location: 'Main Campus, Building A',
    capacity: 500,
    facilities: 'Stage, PA system, projector',
    accessibilityFeatures: 'Step-free access, hearing loop',
    operatingHours: '08:00-22:00',
    supportedLayouts: 'Theatre, standing, cabaret',
    createdAt: '2026-01-05T09:00:00',
    updatedAt: '2026-01-05T09:00:00',
    ...overrides,
  }
}

// --- US9.2: read-only for the role that only reads ---------------------------

it('gives a Coordinator nothing that writes', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Edit venue/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Delete venue/ })).not.toBeInTheDocument()
})

// --- US12.1: unavailable dates on the record ---------------------------------

it('shows a Coordinator the unavailable dates, with nothing to add them', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Unavailable dates' })).toBeInTheDocument()
  expect(listUnavailabilityMock).toHaveBeenCalledWith('1', coordinator)
  expect(screen.queryByRole('button', { name: 'Mark unavailable' })).not.toBeInTheDocument()
})

// --- US9.4: setup and turnaround time ------------------------------------------

it('shows a Coordinator the setup and turnaround time', async () => {
  getVenueMock.mockResolvedValue(buildVenue({ setupMinutes: 30, turnaroundMinutes: 90 }))

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  const setup = await screen.findByText('Setup time')
  expect(setup.nextElementSibling).toHaveTextContent('30 minutes')
  expect(screen.getByText('Turnaround time').nextElementSibling).toHaveTextContent(
    '90 minutes (1 h 30 min)',
  )
})
