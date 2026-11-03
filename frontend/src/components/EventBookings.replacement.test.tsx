/**
 * US14.5: finding and requesting a replacement for a booking flagged as needing one.
 *
 * Which venues are free at the same time is the server's call (US15.1), tested in
 * backend/tests/test_replacement_venue_us14_5.py. This card's job is offering the
 * search to the assigned Coordinator, showing what came back, and, once one is
 * requested, keeping the old booking as history beside the new request.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import EventBookings from './EventBookings'
import {
  EventRuleError,
  listBookings,
  requestReplacementVenue,
  searchReplacementVenues,
  type BookingRecord,
  type EventRecord,
} from '../eventsStore'
import { ApiError } from '../api'
import type { VenueRecord } from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  searchReplacementVenues: vi.fn(async () => []),
  requestReplacementVenue: vi.fn(),
}))

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(async () => []),
}))

const listBookingsMock = vi.mocked(listBookings)
const searchMock = vi.mocked(searchReplacementVenues)
const requestMock = vi.mocked(requestReplacementVenue)

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })

const EVENT: EventRecord = {
  id: '900',
  title: 'Open Day',
  purpose: 'Show prospective students around.',
  description: '',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
  expectedAttendance: 300,
  status: 'Planning',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-10-01T09:00:00',
  updatedAt: '2026-10-01T09:00:00',
  history: [],
}

function booking(overrides: Partial<BookingRecord> = {}): BookingRecord {
  return {
    id: '101',
    eventId: '900',
    venueId: '1',
    venueName: 'Great Hall',
    startsAt: '2027-11-02T09:00:00',
    endsAt: '2027-11-02T17:00:00',
    status: 'Needs replacement',
    replacementReason: 'Closed for repairs.',
    requestedAt: '2026-10-07T09:00:00',
    headcount: 300,
    requiredLayout: '',
    requiredFacilities: [],
    accessibilityNeeds: [],
    cancellation: null,
    ...overrides,
  } as BookingRecord
}

function venue(id: string, name: string, capacity: number): VenueRecord {
  return {
    id,
    name,
    location: 'Main Campus',
    capacity,
    facilities: '',
    accessibilityFeatures: '',
    operatingHours: '',
    supportedLayouts: '',
    createdAt: '2026-01-05T09:00:00',
    updatedAt: '2026-01-05T09:00:00',
  }
}

const FREE = [venue('3', 'Seminar Room 4', 320), venue('4', 'Lecture Theatre', 400)]

beforeEach(() => {
  vi.resetAllMocks()
  listBookingsMock.mockResolvedValue([booking()])
  searchMock.mockResolvedValue(FREE)
})

async function openSearch(onBookingRequested?: () => void, event: EventRecord = EVENT) {
  const user = userEvent.setup()
  render(
    <EventBookings event={event} session={coordinator} onBookingRequested={onBookingRequested} />,
  )
  await user.click(
    await screen.findByRole('button', { name: 'Find a replacement venue for Great Hall' }),
  )
  return user
}

it('searches the same time slot, unfiltered, from the flagged booking', async () => {
  await openSearch()

  expect(searchMock).toHaveBeenCalledWith('101', coordinator, {
    minCapacity: '',
    location: '',
    accessibility: '',
  })
  const choices = await screen.findByLabelText('Choose a replacement venue')
  expect(within(choices).getByRole('option', { name: 'Seminar Room 4 — holds 320' })).toBeTruthy()
})

it('requests the chosen venue and keeps the old booking as Replaced history', async () => {
  const onBookingRequested = vi.fn()
  requestMock.mockResolvedValue(
    booking({ id: '102', venueId: '3', venueName: 'Seminar Room 4', status: 'Requested' }),
  )
  const user = await openSearch(onBookingRequested)

  await user.selectOptions(await screen.findByLabelText('Choose a replacement venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request replacement' }))

  expect(requestMock).toHaveBeenCalledWith('101', '3', coordinator)
  expect(
    await screen.findByText(
      'Requested Seminar Room 4 as a replacement. It is waiting for Venue Staff to approve it.',
    ),
  ).toBeTruthy()
  const oldRow = screen.getByText('Great Hall').closest('li')!
  expect(within(oldRow).getByText('Replaced')).toBeTruthy()
  expect(screen.getByText('Seminar Room 4')).toBeTruthy()
  expect(onBookingRequested).toHaveBeenCalledTimes(1)
  // US12.4: not Confirmed, so nothing about going back to Planning.
  expect(screen.queryByText(/moves it back to Planning/)).toBeNull()
})

it('US12.4 warns that a Confirmed event goes back to Planning, and says it did', async () => {
  const onBookingRequested = vi.fn()
  requestMock.mockResolvedValue(
    booking({ id: '102', venueId: '3', venueName: 'Seminar Room 4', status: 'Requested' }),
  )
  const user = await openSearch(onBookingRequested, { ...EVENT, status: 'Confirmed' })

  expect(
    await screen.findByText(
      "This event is Confirmed. Requesting a replacement moves it back to Planning: the new venue needs Venue Staff's approval and a new safety check, and you confirm the event again. Its other bookings are kept.",
    ),
  ).toBeTruthy()
  await user.selectOptions(await screen.findByLabelText('Choose a replacement venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request replacement' }))

  expect(
    await screen.findByText(
      'Requested Seminar Room 4 as a replacement. It is waiting for Venue Staff to approve it.',
    ),
  ).toBeTruthy()
  // The page reloads the event, which now reads Planning, and says so
  // (EventDetailPage.paths.test.tsx).
  expect(onBookingRequested).toHaveBeenCalledTimes(1)
})

it('narrows the search by the filters typed, and clears them again', async () => {
  const user = await openSearch()
  await screen.findByLabelText('Choose a replacement venue')

  await user.type(screen.getByLabelText('Minimum capacity'), '350')
  await user.type(screen.getByLabelText('Location'), 'Main')
  await user.type(screen.getByLabelText('Accessibility'), 'Lift')
  await user.click(screen.getByRole('button', { name: 'Apply filters' }))

  expect(searchMock).toHaveBeenLastCalledWith('101', coordinator, {
    minCapacity: '350',
    location: 'Main',
    accessibility: 'Lift',
  })

  await user.click(await screen.findByRole('button', { name: 'Clear filters' }))

  expect(searchMock).toHaveBeenLastCalledWith('101', coordinator, {
    minCapacity: '',
    location: '',
    accessibility: '',
  })
})

it('says so when nothing is free, and closes', async () => {
  searchMock.mockResolvedValue([])
  const user = await openSearch()

  expect(
    await screen.findByText(
      'No replacement venues are available for the same time slot and filters.',
    ),
  ).toBeTruthy()

  await user.click(screen.getByRole('button', { name: 'Close' }))

  expect(screen.queryByText('Find a replacement venue')).toBeNull()
  expect(
    screen.getByRole('button', { name: 'Find a replacement venue for Great Hall' }),
  ).toBeTruthy()
})

it('cancelling the search leaves the booking as it was', async () => {
  const user = await openSearch()
  await screen.findByLabelText('Choose a replacement venue')

  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.queryByLabelText('Choose a replacement venue')).toBeNull()
  expect(requestMock).not.toHaveBeenCalled()
})

it.each([
  [new EventRuleError('This booking no longer needs a replacement.'), 'This booking no longer needs a replacement.'],
  [
    new ApiError('Internal error', 'unknown', 500),
    'Could not search for replacement venues. The API answered HTTP 500 — check the backend log for the cause.',
  ],
])('a failed search says why: %s', async (error, message) => {
  searchMock.mockRejectedValue(error)
  await openSearch()

  expect(await screen.findByText(message)).toBeTruthy()
})

it.each([
  [new EventRuleError('Seminar Room 4 was just taken.'), 'Seminar Room 4 was just taken.'],
  [
    new ApiError('Internal error', 'unknown', 500),
    'Could not request the replacement venue. The API answered HTTP 500 — check the backend log for the cause.',
  ],
])('a refused request says why and keeps the choice: %s', async (error, message) => {
  requestMock.mockRejectedValue(error)
  const user = await openSearch()

  await user.selectOptions(await screen.findByLabelText('Choose a replacement venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request replacement' }))

  expect(await screen.findByText(message)).toBeTruthy()
  expect(screen.getByLabelText<HTMLSelectElement>('Choose a replacement venue').value).toBe('3')
})
