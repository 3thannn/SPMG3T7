/**
 * What the catalogue page renders — US9.2, US9.3 and the US9.1a entry point.
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
import { NO_FILTERS, VenueRuleError, listVenues, type VenueRecord } from '../venuesStore'
import { buildSession } from '../test/sessions'
import { ApiError } from '../api'

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

/** The filters the page sent on its most recent fetch. */
function lastFilters() {
  return listVenuesMock.mock.calls.at(-1)?.[1]
}

it('lists every venue in the catalogue', async () => {
  listVenuesMock.mockResolvedValue([
    buildVenue({ id: '1', name: 'Great Hall' }),
    buildVenue({ id: '2', name: 'Bertha Room', capacity: 40 }),
  ])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText('Great Hall')).toBeInTheDocument()
  expect(screen.getByText('Bertha Room')).toBeInTheDocument()
})

it('shows where a venue is and how many it holds', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText('Main Campus, Building A')).toBeInTheDocument()
  expect(screen.getByText('500 people')).toBeInTheDocument()
})

it('links each row to that venue record', async () => {
  listVenuesMock.mockResolvedValue([buildVenue({ id: '7', name: 'Studio One' })])

  render(<VenuesPage session={coordinator} />)

  const link = await screen.findByRole('link', { name: /Studio One/ })
  expect(link).toHaveAttribute('href', '#/venues/7')
})

it('counts what is on screen', async () => {
  listVenuesMock.mockResolvedValue([
    buildVenue({ id: '1' }),
    buildVenue({ id: '2', name: 'Bertha Room' }),
  ])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText(/^2 venues/)).toBeInTheDocument()
})

it('says venue rather than venues when there is one', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText(/^1 venue/)).toBeInTheDocument()
})

it('asks for the whole catalogue before anything is filtered', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  expect(lastFilters()).toEqual(NO_FILTERS)
})

it('says the catalogue is empty when it is', async () => {
  listVenuesMock.mockResolvedValue([])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText('No venues yet')).toBeInTheDocument()
})

it('distinguishes an unreachable API from an empty catalogue', async () => {
  listVenuesMock.mockRejectedValue(new Error('network down'))

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /Could not load the venue catalogue.*could not be reached/,
  )
  expect(screen.queryByText('No venues yet')).not.toBeInTheDocument()
})

it('sends a server fault to the backend log rather than to the API switch', async () => {
  // The API answered, so telling the reader to check it is running would send
  // them looking in exactly the wrong place.
  listVenuesMock.mockRejectedValue(new ApiError('Request failed.', 'unknown', 500))

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(/HTTP 500/)
  expect(screen.getByRole('alert')).not.toHaveTextContent(/could not be reached/)
})

it('says what was wrong with a filter instead of blaming the API', async () => {
  // A capacity of "abcdef" is refused by the server with a sentence naming the
  // field. The reader fixes it in the box above, not by restarting anything.
  listVenuesMock.mockRejectedValue(
    new VenueRuleError('Give a whole number of people for the minimum capacity.'),
  )

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Give a whole number of people for the minimum capacity.',
  )
  expect(screen.getByRole('alert')).not.toHaveTextContent(/Check the API is running/)
})

// --- US9.3: the filters ------------------------------------------------------

it('offers a filter for each of the three criteria', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  expect(screen.getByLabelText('Minimum capacity')).toBeInTheDocument()
  expect(screen.getByLabelText('Location')).toBeInTheDocument()
  expect(screen.getByLabelText('Accessibility')).toBeInTheDocument()
})

it('sends the filters only once they are applied', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  await userEvent.type(screen.getByLabelText('Location'), 'Library')

  // Typing alone must not refetch: each apply is a request, and the page says
  // when it is making one.
  expect(lastFilters()).toEqual(NO_FILTERS)

  await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  await waitFor(() => {
    expect(lastFilters()).toEqual({ ...NO_FILTERS, location: 'Library' })
  })
})

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
      minCapacity: '200',
      location: 'Library',
      accessibility: 'Step-free',
    })
  })
})

it('says that the filters combine rather than leaving it ambiguous', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText('All filters must match.')).toBeInTheDocument()
})

it('describes the list as filtered once it is', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  await userEvent.type(screen.getByLabelText('Location'), 'Main')
  await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  expect(await screen.findByText(/matching your filters/)).toBeInTheDocument()
})

it('tells an empty result apart from an empty catalogue', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  listVenuesMock.mockResolvedValue([])
  await userEvent.type(screen.getByLabelText('Location'), 'Nowhere')
  await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

  expect(await screen.findByText('Nothing matches those filters')).toBeInTheDocument()
  expect(screen.queryByText('No venues yet')).not.toBeInTheDocument()
})

it('clears the filters back to the whole catalogue', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  await userEvent.type(screen.getByLabelText('Location'), 'Library')
  await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
  await waitFor(() => expect(lastFilters()?.location).toBe('Library'))

  await userEvent.click(screen.getByRole('button', { name: 'Clear' }))

  await waitFor(() => expect(lastFilters()).toEqual(NO_FILTERS))
  expect(screen.getByLabelText('Location')).toHaveValue('')
})

it('has nothing to clear before a filter is typed', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  expect(screen.getByRole('button', { name: 'Clear' })).toBeDisabled()
})

// --- US9.1a: who is offered the add action -----------------------------------

it('offers Venue Staff a way to add a venue', async () => {
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={venueStaff} />)
  await screen.findByText('Great Hall')

  expect(screen.getByRole('button', { name: 'Add venue' })).toBeInTheDocument()
})

it('does not offer a Coordinator an action they do not hold', async () => {
  // A hidden button is a courtesy — the API refuses a Coordinator's POST
  // regardless — but leading them to a form that will turn them away is not
  // how to tell them what their role is for.
  listVenuesMock.mockResolvedValue([buildVenue()])

  render(<VenuesPage session={coordinator} />)
  await screen.findByText('Great Hall')

  expect(screen.queryByRole('button', { name: 'Add venue' })).not.toBeInTheDocument()
})

it('invites Venue Staff to fill an empty catalogue', async () => {
  listVenuesMock.mockResolvedValue([])

  render(<VenuesPage session={venueStaff} />)

  expect(await screen.findByText('No venues yet')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Add venue' })).toHaveLength(2)
})

it('tells a Coordinator an empty catalogue is not theirs to fill', async () => {
  listVenuesMock.mockResolvedValue([])

  render(<VenuesPage session={coordinator} />)

  expect(await screen.findByText(/Once venues are added to ConnectSphere/)).toBeInTheDocument()
})
