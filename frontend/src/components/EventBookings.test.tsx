/**
 * The venue bookings card on an event — US14.1, US14.2 and US18.1.
 *
 * Who may request or cancel, for which events, and whether a venue suits a
 * booking, are the server's calls, tested in backend/tests. This card's job is
 * showing every booking for the event together, offering the forms to the
 * assigned Coordinator, showing the server's suitability verdict as a venue is
 * picked, and keeping each request and cancellation to the one booking it is
 * about.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EventBookings from './EventBookings'
import {
  cancelBooking,
  checkSuitability,
  formatBookingTimes,
  listBookings,
  requestBooking,
  type BookingRecord,
  type EventRecord,
  type Suitability,
} from '../eventsStore'
import { listVenues, type VenueRecord } from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  requestBooking: vi.fn(),
  requestHeldBooking: vi.fn(),
  cancelBooking: vi.fn(),
  // US18.1: Suitable unless a test says otherwise, so the US14.1 tests below
  // are about requesting rather than about the check.
  checkSuitability: vi.fn(
    async (): Promise<Suitability> => ({ venueId: '1', suitable: true, reasons: [], notes: [] }),
  ),
}))

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(async () => []),
}))

const listBookingsMock = vi.mocked(listBookings)
const requestBookingMock = vi.mocked(requestBooking)
const cancelBookingMock = vi.mocked(cancelBooking)
const checkSuitabilityMock = vi.mocked(checkSuitability)
const listVenuesMock = vi.mocked(listVenues)

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })

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

const VENUES = [venue('1', 'Great Hall', 500), venue('3', 'Seminar Room 4', 60)]

function booking(overrides: Partial<BookingRecord> = {}): BookingRecord {
  return {
    id: '101',
    eventId: '900',
    venueId: '1',
    venueName: 'Great Hall',
    startsAt: '2027-11-02T09:00:00',
    endsAt: '2027-11-02T17:00:00',
    status: 'Requested',
    requestedAt: '2026-10-07T09:00:00',
    headcount: 300,
    requiredLayout: '',
    requiredFacilities: [],
    accessibilityNeeds: [],
    cancellation: null,
    ...overrides,
  }
}

const REASON = 'Numbers dropped, so the hall is too big.'

function cancelled(overrides: Partial<BookingRecord> = {}): BookingRecord {
  return booking({
    status: 'Cancelled',
    cancellation: {
      at: '2026-10-08T10:00:00',
      byId: '2',
      byName: 'Priya',
      reason: REASON,
    },
    ...overrides,
  })
}

const BREAKOUT = booking({
  id: '102',
  venueId: '3',
  venueName: 'Seminar Room 4',
  startsAt: '2027-11-02T13:00:00',
  endsAt: '2027-11-02T15:00:00',
})

function event(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '900',
    title: 'Open Day',
    purpose: 'Show prospective students around.',
    description: '',
    startsAt: '2027-11-02T09:00:00',
    endsAt: '2027-11-02T17:00:00',
    expectedAttendance: 300,
    status: 'Approved',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-10-01T09:00:00',
    updatedAt: '2026-10-01T09:00:00',
    history: [],
    ...overrides,
  }
}

beforeEach(() => {
  listBookingsMock.mockResolvedValue([])
  listVenuesMock.mockResolvedValue(VENUES)
})

afterEach(() => {
  vi.resetAllMocks()
})

function bookingList() {
  return screen.getByRole('list', { name: 'Venue bookings for this event' })
}

async function formReady() {
  await screen.findByRole('option', { name: 'Great Hall — holds 500' })
}

it('shows the replacement reason and actionable guidance for a flagged booking', async () => {
  listBookingsMock.mockResolvedValue([
    booking({
      status: 'Needs replacement',
      replacementReason: 'Unexpected flooding',
      flaggedByUnavailabilityId: 42,
    }),
  ])
  render(<EventBookings event={event()} session={coordinator} />)

  const notice = await screen.findByRole('note')
  expect(notice).toHaveTextContent('Needs replacement')
  expect(notice).toHaveTextContent('Unexpected flooding')
  expect(notice).toHaveTextContent('Contact Venue Staff to find an alternative.')
})

// D7 (CODE_AUDIT.md): a flag clears when the booking is cancelled (US12.2 AC5,
// US15.2 AC4), so a Confirmed or flagged booking offers Cancel too.
it.each(['Confirmed', 'Needs replacement'] as const)(
  'offers the Coordinator a cancel on a %s booking',
  async (status) => {
    listBookingsMock.mockResolvedValue([booking({ status })])
    render(<EventBookings event={event()} session={coordinator} />)

    expect(
      await screen.findByRole('button', { name: 'Cancel the Great Hall booking' }),
    ).toBeInTheDocument()
  },
)

it.each(['Rejected', 'Replaced', 'Cancelled'] as const)(
  'offers no cancel on a %s booking',
  async (status) => {
    listBookingsMock.mockResolvedValue([
      status === 'Cancelled' ? cancelled() : booking({ status }),
    ])
    render(<EventBookings event={event()} session={coordinator} />)

    await screen.findByText('Great Hall')
    expect(
      screen.queryByRole('button', { name: 'Cancel the Great Hall booking' }),
    ).not.toBeInTheDocument()
  },
)

// -- AC4: every booking for the event, together -------------------------------

it('lists every booking for the event with its venue, times and status', async () => {
  listBookingsMock.mockResolvedValue([
    booking(),
    booking({
      id: '102',
      venueId: '3',
      venueName: 'Seminar Room 4',
      startsAt: '2027-11-02T13:00:00',
      endsAt: '2027-11-02T15:00:00',
    }),
  ])

  render(<EventBookings event={event()} session={organiser} />)

  const rows = within(await screen.findByRole('list')).getAllByRole('listitem')
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Great Hall')
  expect(rows[0]).toHaveTextContent(formatBookingTimes('2027-11-02T09:00:00', '2027-11-02T17:00:00'))
  expect(rows[0]).toHaveTextContent('Requested')
  expect(rows[1]).toHaveTextContent('Seminar Room 4')
  expect(listBookingsMock).toHaveBeenCalledWith('900', organiser)
})

it('requests several venues for one event, one after another', async () => {
  const user = userEvent.setup()
  requestBookingMock
    .mockResolvedValueOnce(booking())
    .mockResolvedValueOnce(
      booking({ id: '102', venueId: '3', venueName: 'Seminar Room 4' }),
    )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))
  await screen.findByText(/Requested Great Hall/)
  await user.selectOptions(screen.getByLabelText('Venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  await screen.findByText(/Requested Seminar Room 4/)
  expect(within(bookingList()).getAllByRole('listitem')).toHaveLength(2)
})

// -- US14.2: cancelling one booking -----------------------------------------------

function rowFor(venueName: string) {
  const row = within(bookingList())
    .getAllByRole('listitem')
    .find((item) => item.textContent?.includes(venueName))
  if (!row) throw new Error(`No booking row for ${venueName}`)
  return row
}

async function openCancel(venueName = 'Great Hall') {
  const user = userEvent.setup()
  await user.click(
    await screen.findByRole('button', { name: `Cancel the ${venueName} booking` }),
  )
  return user
}

it('cancels the one booking with the reason, and shows who, when and why', async () => {
  listBookingsMock.mockResolvedValue([booking(), BREAKOUT])
  cancelBookingMock.mockResolvedValue(cancelled())
  render(<EventBookings event={event()} session={coordinator} />)

  const user = await openCancel()
  await user.type(screen.getByLabelText('Why are you cancelling this booking?'), `  ${REASON}  `)
  await user.click(screen.getByRole('button', { name: 'Cancel booking' }))

  await waitFor(() =>
    expect(cancelBookingMock).toHaveBeenCalledWith('900', '101', REASON, coordinator),
  )
  expect(
    await screen.findByText(
      'Cancelled Great Hall. The event and its other bookings are unchanged.',
    ),
  ).toBeInTheDocument()
  const row = rowFor('Great Hall')
  expect(row).toHaveTextContent('Cancelled')
  expect(row).toHaveTextContent(`Cancelled by Priya, 08 Oct 2026, 18:00: ${REASON}`)
  expect(screen.queryByLabelText('Why are you cancelling this booking?')).not.toBeInTheDocument()
})

// -- US18.1: suitability per booking ------------------------------------------------

function verdictOf(overrides: Partial<Suitability> = {}): Suitability {
  return { venueId: '1', suitable: true, reasons: [], notes: [], ...overrides }
}

const NOT_SUITABLE = verdictOf({
  venueId: '3',
  suitable: false,
  reasons: ['It holds 60 people, and this booking is for 300.'],
})

it('says Not suitable with the reasons, and will not request it', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(NOT_SUITABLE)
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '3')

  expect(await screen.findByText('Not suitable')).toBeInTheDocument()
  expect(
    screen.getByText('It holds 60 people, and this booking is for 300.'),
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Request venue' }))
  expect(requestBookingMock).not.toHaveBeenCalled()
})
