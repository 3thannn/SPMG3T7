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
  listBookings,
  searchReplacementVenues,
  type BookingRecord,
  type EventRecord,
} from '../eventsStore'
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
