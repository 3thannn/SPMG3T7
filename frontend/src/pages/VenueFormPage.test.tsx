/**
 * The create and edit form — US9.1a and US9.1b.
 *
 * One page serves both, so most of these assert that it behaves as the right
 * one of the two: which fields it starts with, which call it makes on submit,
 * and where it goes afterwards. The validation is checked here as messages on
 * screen; the same rules are enforced again by the server, and that is where
 * they are the rule.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import VenueFormPage from './VenueFormPage'
import {
  createVenue,
  type VenueRecord,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getVenue: vi.fn(),
  createVenue: vi.fn(),
  saveVenue: vi.fn(),
}))

const createVenueMock = vi.mocked(createVenue)

afterEach(() => {
  vi.resetAllMocks()
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
    facilities: 'Stage, PA system',
    accessibilityFeatures: 'Step-free access',
    operatingHours: '08:00-22:00',
    supportedLayouts: 'Theatre, standing',
    createdAt: '2026-01-05T09:00:00',
    updatedAt: '2026-01-05T09:00:00',
    ...overrides,
  }
}

/** Fill the three required fields, which every valid submit needs. */
async function fillRequired(
  values: { name?: string; location?: string; capacity?: string } = {},
) {
  await userEvent.type(screen.getByLabelText('Name'), values.name ?? 'Atrium')
  await userEvent.type(screen.getByLabelText('Location'), values.location ?? 'Science Quarter')
  await userEvent.type(screen.getByLabelText('Capacity'), values.capacity ?? '90')
}

it('creates a venue from the three required fields alone', async () => {
  createVenueMock.mockResolvedValue(buildVenue({ id: '42' }))

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired()
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(createVenueMock).toHaveBeenCalledWith(
      {
        name: 'Atrium',
        location: 'Science Quarter',
        capacity: 90,
        facilities: '',
        accessibilityFeatures: '',
        operatingHours: '',
        supportedLayouts: '',
        // US9.4: untouched, both go as the default of 0.
        setupMinutes: 0,
        turnaroundMinutes: 0,
      },
      venueStaff,
    )
  })
})
