/**
 * What the catalogue page renders — US9.2, US9.3, US12.1's planning dates and
 * the US9.1a entry point.
 *
 * Who may reach the page, and what the filters actually match, are the server's
 * call and are tested in backend/tests/test_venues.py. What is this page's job
 * is listing venues, sending the filters it was given, telling an empty
 * catalogue apart from an unreachable one, and offering the add action to the
 * one role that holds it.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import VenuesPage from './VenuesPage'
import {
  NO_FILTERS,
  listVenues,
  type VenueRecord,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(),
}))

const listVenuesMock = vi.mocked(listVenues)

afterEach(() => {
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
    facilities: 'Stage, PA system',
    accessibilityFeatures: 'Step-free access',
    operatingHours: '08:00-22:00',
    supportedLayouts: 'Theatre, standing',
    createdAt: '2026-01-05T09:00:00',
    updatedAt: '2026-01-05T09:00:00',
    ...overrides,
  }
}

/** The filters the page sent on its most recent fetch. */
function lastFilters() {
  return listVenuesMock.mock.calls.at(-1)?.[1]
}

it('sends all three filters together', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  await userEvent.type(screen.getByLabelText('Minimum capacity'), '200')
  await userEvent.type(screen.getByLabelText('Location'), 'Library')
  await userEvent.type(screen.getByLabelText('Accessibility'), 'Step-free')
  await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  await waitFor(() => {
    expect(lastFilters()).toEqual({
      ...NO_FILTERS,
      minCapacity: '200',
      location: 'Library',
      accessibility: 'Step-free',
    })
  })
})
