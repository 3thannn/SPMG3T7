/**
 * What the venue record renders — US9.2, US9.1b and US9.1c.
 *
 * The page shows the same details to everyone and differs only in what it
 * offers to act with. So the two halves asserted here are: a Coordinator gets a
 * page with nothing on it that writes, and Venue Staff get edit and delete —
 * with the delete confirmed first, because US9.1c is a hard delete.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import VenueDetailPage from './VenueDetailPage'
import { VenueRuleError, deleteVenue, getVenue, type VenueRecord } from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getVenue: vi.fn(),
  deleteVenue: vi.fn(),
}))

const getVenueMock = vi.mocked(getVenue)
const deleteVenueMock = vi.mocked(deleteVenue)

afterEach(() => {
  vi.resetAllMocks()
})

const coordinator = buildSession({
  role: 'Event Coordinator',
  id: '9',
  name: 'Priya',
  email: 'priya@example.edu',
})

const venueStaff = buildSession({
  role: 'Venue Staff',
  id: '3',
  name: 'Sam',
  email: 'sam@example.edu',
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

it('shows the venue and every recorded detail', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Great Hall' })).toBeInTheDocument()
  expect(screen.getByText('500 people')).toBeInTheDocument()
  expect(screen.getByText('Stage, PA system, projector')).toBeInTheDocument()
  expect(screen.getByText('Step-free access, hearing loop')).toBeInTheDocument()
  expect(screen.getByText('Theatre, standing, cabaret')).toBeInTheDocument()
  expect(screen.getByText('08:00-22:00')).toBeInTheDocument()
})

it('labels every detail, so an empty one is still accounted for', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  for (const label of [
    'Location',
    'Capacity',
    'Facilities',
    'Accessibility features',
    'Supported layouts',
    'Operating hours',
  ]) {
    expect(screen.getByText(label)).toBeInTheDocument()
  }
})

it('says a detail is not recorded rather than leaving it blank', async () => {
  // Four of the columns are nullable, and "no accessibility features recorded"
  // is something a Coordinator needs to see, not an empty row.
  getVenueMock.mockResolvedValue(
    buildVenue({
      facilities: '',
      accessibilityFeatures: '',
      operatingHours: '',
      supportedLayouts: '',
    }),
  )

  render(<VenueDetailPage venueId="1" session={coordinator} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.getAllByText('Not recorded')).toHaveLength(4)
})

it('offers a way back to the catalogue', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  expect(await screen.findByRole('link', { name: /Back to venues/ })).toHaveAttribute(
    'href',
    '#/venues',
  )
})

it('says when a venue is not in the catalogue', async () => {
  getVenueMock.mockResolvedValue(null)

  render(<VenueDetailPage venueId="404" session={coordinator} />)

  expect(await screen.findByText('Venue not found')).toBeInTheDocument()
})

it('distinguishes an unreachable API from a missing venue', async () => {
  getVenueMock.mockRejectedValue(new Error('network down'))

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not load this venue/)
  expect(screen.queryByText('Venue not found')).not.toBeInTheDocument()
})

// --- US9.2: read-only for the role that only reads ---------------------------

it('gives a Coordinator nothing that writes', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Edit venue/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Delete venue/ })).not.toBeInTheDocument()
})

it('tells a Coordinator the record is read-only to them', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={coordinator} />)

  expect(await screen.findByText('Read-only')).toBeInTheDocument()
})

it('does not call the record read-only to someone who can change it', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.queryByText('Read-only')).not.toBeInTheDocument()
})

// --- US9.1b: editing --------------------------------------------------------

it('offers Venue Staff the edit form for this venue', async () => {
  getVenueMock.mockResolvedValue(buildVenue({ id: '7' }))

  render(<VenueDetailPage venueId="7" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.getByRole('button', { name: 'Edit venue' })).toBeInTheDocument()
})

it('never edits in place — the detail page has no inputs for anyone', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

// --- US9.1c: deleting -------------------------------------------------------

it('does not delete on the first click', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))

  expect(deleteVenueMock).not.toHaveBeenCalled()
})

it('asks first, naming the venue and saying it cannot be undone', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))

  expect(screen.getByText(/cannot be\s+undone/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Yes, delete it' })).toBeInTheDocument()
})

it('deletes once confirmed', async () => {
  getVenueMock.mockResolvedValue(buildVenue())
  deleteVenueMock.mockResolvedValue(undefined)

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))
  await userEvent.click(screen.getByRole('button', { name: 'Yes, delete it' }))

  await waitFor(() => {
    expect(deleteVenueMock).toHaveBeenCalledWith('1', venueStaff)
  })
})

it('backs out without deleting', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))
  await userEvent.click(screen.getByRole('button', { name: 'Keep it' }))

  expect(deleteVenueMock).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Delete venue' })).toBeInTheDocument()
})

it('shows the reason when the server refuses a delete', async () => {
  getVenueMock.mockResolvedValue(buildVenue())
  deleteVenueMock.mockRejectedValue(new VenueRuleError('That venue is still booked.'))

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))
  await userEvent.click(screen.getByRole('button', { name: 'Yes, delete it' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('That venue is still booked.')
})

it('says something useful when a delete fails for another reason', async () => {
  getVenueMock.mockResolvedValue(buildVenue())
  deleteVenueMock.mockRejectedValue(new Error('network down'))

  render(<VenueDetailPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Great Hall' })

  await userEvent.click(screen.getByRole('button', { name: 'Delete venue' }))
  await userEvent.click(screen.getByRole('button', { name: 'Yes, delete it' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not delete this venue/)
})
