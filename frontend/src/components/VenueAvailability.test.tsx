/**
 * US12.3: what is taking up a venue over a date range.
 *
 * The server decides what is listed and in what order (see
 * backend/tests/test_venue_availability_us12_3.py); this card asks for the
 * range picked and shows each entry by type.
 */

import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import VenueAvailability from './VenueAvailability'
import {
  getAvailability,
  type AvailabilityEntry,
  type VenueAvailability as Availability,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getAvailability: vi.fn(),
}))

const getAvailabilityMock = vi.mocked(getAvailability)

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const session = buildSession({ role: 'Venue Staff', id: '3', name: 'Sam', email: 'sam@example.edu' })
const TODAY = '2027-03-01'

function entry(overrides: Partial<AvailabilityEntry>): AvailabilityEntry {
  return {
    kind: 'confirmed',
    startsAt: '2027-03-03T09:30',
    endsAt: '2027-03-03T12:45',
    bookingId: '1',
    eventId: '1',
    eventTitle: 'Faculty Welcome Night',
    eventStartsAt: '2027-03-03T10:00',
    eventEndsAt: '2027-03-03T12:00',
    holdExpiresAt: '',
    periodId: '',
    startDate: '',
    endDate: '',
    reasonType: '',
    otherReason: '',
    ...overrides,
  }
}

function answer(entries: AvailabilityEntry[], overrides: Partial<Availability> = {}) {
  getAvailabilityMock.mockResolvedValue({
    venueId: '1',
    from: '2027-03-01',
    to: '2027-03-14',
    setupMinutes: 30,
    turnaroundMinutes: 45,
    entries,
    ...overrides,
  })
}

const EVERY_KIND = [
  entry({}),
  entry({
    kind: 'requested',
    bookingId: '2',
    eventTitle: '',
    eventId: '',
    startsAt: '2027-03-04T09:30',
    endsAt: '2027-03-04T12:45',
  }),
  entry({
    kind: 'unavailable',
    bookingId: '',
    eventId: '',
    eventTitle: '',
    eventStartsAt: '',
    eventEndsAt: '',
    startsAt: '2027-03-05T00:00',
    endsAt: '2027-03-07T00:00',
    periodId: '7',
    startDate: '2027-03-05',
    endDate: '2027-03-06',
    reasonType: 'other',
    otherReason: 'Floor polishing',
  }),
  entry({
    kind: 'hold',
    bookingId: '3',
    eventTitle: 'Open Day',
    startsAt: '2027-03-08T13:30',
    endsAt: '2027-03-08T16:45',
    eventStartsAt: '2027-03-08T14:00',
    eventEndsAt: '2027-03-08T16:00',
    holdExpiresAt: '2027-03-04T17:00',
  }),
]

async function rows() {
  const list = await screen.findByRole('list', { name: /What is taking up this venue/ })
  return within(list).getAllByRole('listitem')
}

describe('AC1: the range', () => {
  it('asks for the next 14 days to start with', async () => {
    answer([])

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(screen.getByLabelText('From')).toHaveValue('2027-03-01')
    expect(screen.getByLabelText('To')).toHaveValue('2027-03-14')
    await screen.findByText(/Showing/)
    expect(getAvailabilityMock).toHaveBeenCalledWith(
      '1',
      { from: '2027-03-01', to: '2027-03-14' },
      session,
    )
  })
})

describe('AC2: everything taking up the venue, labelled by type', () => {
  it('lists the entries in the order the server sends, each with its type', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const labels = (await rows()).map((row) => row.querySelector('.availability-tag')?.textContent)
    expect(labels).toEqual(['Confirmed booking', 'Requested booking', 'Unavailable', 'Tentative hold'])
  })
})
