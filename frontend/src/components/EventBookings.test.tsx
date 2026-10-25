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
  CONFLICT_LABEL,
  EventRuleError,
  cancelBooking,
  checkSuitability,
  formatBookingTimes,
  listBookings,
  requestBooking,
  requestHeldBooking,
  type BookingRecord,
  type EventRecord,
  type Suitability,
} from '../eventsStore'
import { formatTimestamp } from '../status'
import { listVenues, type VenueRecord } from '../venuesStore'
import { ApiError } from '../api'
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
  expect(screen.queryByRole('button', { name: /cancel booking/i })).not.toBeInTheDocument()
})

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

it('says so when no venue has been requested yet', async () => {
  render(<EventBookings event={event()} session={organiser} />)

  expect(
    await screen.findByText('No venues have been requested for this event yet.'),
  ).toBeInTheDocument()
})

it('reports a failure to load the bookings in the card', async () => {
  listBookingsMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))

  render(<EventBookings event={event()} session={organiser} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('load the venue bookings')
})

it('does not offer the Organiser the form or load the catalogue for them', async () => {
  listBookingsMock.mockResolvedValue([booking()])

  render(<EventBookings event={event()} session={organiser} />)

  await screen.findByRole('list')
  expect(screen.queryByRole('button', { name: 'Request venue' })).not.toBeInTheDocument()
  expect(listVenuesMock).not.toHaveBeenCalled()
})

// -- AC1, AC3, AC5: requesting, one venue at a time ----------------------------

it('offers the Coordinator the catalogue, starting from the event times', async () => {
  render(<EventBookings event={event()} session={coordinator} />)

  await formReady()
  expect(screen.getByLabelText('Venue')).toHaveValue('')
  expect(screen.getByLabelText('Starts')).toHaveValue('2027-11-02T09:00')
  expect(screen.getByLabelText('Ends')).toHaveValue('2027-11-02T17:00')
})

it('requests the chosen venue and adds it to the list as Requested', async () => {
  const user = userEvent.setup()
  const onBookingRequested = vi.fn()
  requestBookingMock.mockResolvedValue(booking())
  render(<EventBookings event={event()} session={coordinator} onBookingRequested={onBookingRequested} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  await waitFor(() =>
    expect(requestBookingMock).toHaveBeenCalledWith(
      '900',
      {
        venueId: '1',
        startsAt: '2027-11-02T09:00',
        endsAt: '2027-11-02T17:00',
        headcount: '300',
        layout: '',
        facilities: '',
        accessibilityNeeds: '',
      },
      coordinator,
    ),
  )
  expect(
    await screen.findByText('Requested Great Hall. It is waiting for Venue Staff to approve it.'),
  ).toBeInTheDocument()
  expect(within(bookingList()).getByText('Great Hall')).toBeInTheDocument()
  expect(within(bookingList()).getByText('Requested')).toBeInTheDocument()
  expect(onBookingRequested).toHaveBeenCalledOnce()
})

it('clears the venue after a request but keeps the times for the next one', async () => {
  const user = userEvent.setup()
  requestBookingMock.mockResolvedValue(booking())
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  await screen.findByText(/Requested Great Hall/)
  expect(screen.getByLabelText('Venue')).toHaveValue('')
  expect(screen.getByLabelText('Starts')).toHaveValue('2027-11-02T09:00')
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

it('keeps the list sorted by time when a booking is added', async () => {
  const user = userEvent.setup()
  listBookingsMock.mockResolvedValue([
    booking({ id: '101', startsAt: '2027-11-02T13:00:00', endsAt: '2027-11-02T15:00:00' }),
  ])
  requestBookingMock.mockResolvedValue(
    booking({ id: '102', venueId: '3', venueName: 'Seminar Room 4' }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  await screen.findByText(/Requested Seminar Room 4/)
  const rows = within(bookingList()).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Seminar Room 4')
  expect(rows[1]).toHaveTextContent('Great Hall')
})

it('shows a refusal without touching the bookings already made', async () => {
  const user = userEvent.setup()
  listBookingsMock.mockResolvedValue([booking()])
  requestBookingMock.mockRejectedValue(new EventRuleError('That venue is not in the catalogue.'))
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '3')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'That venue is not in the catalogue.',
  )
  expect(within(bookingList()).getAllByRole('listitem')).toHaveLength(1)
  // What was chosen stays, so the Coordinator can change one thing and retry.
  expect(screen.getByLabelText('Venue')).toHaveValue('3')
})

it('explains an unexpected failure rather than showing nothing', async () => {
  const user = userEvent.setup()
  requestBookingMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('request this venue')
})

it('asks for a venue before sending anything', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(screen.getByRole('alert')).toHaveTextContent('Choose a venue.')
  expect(requestBookingMock).not.toHaveBeenCalled()
})

it('refuses an end that is not after the start before sending anything', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.clear(screen.getByLabelText('Ends'))
  await user.type(screen.getByLabelText('Ends'), '2027-11-02T08:00')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(screen.getByRole('alert')).toHaveTextContent('The booking must end after it starts.')
  expect(requestBookingMock).not.toHaveBeenCalled()
})

it('asks for the times when the event has none to start from', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event({ endsAt: undefined })} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(screen.getByRole('alert')).toHaveTextContent('Give the booking an end time.')
})

it('reports a catalogue that will not load and keeps the form shut', async () => {
  listVenuesMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))

  render(<EventBookings event={event()} session={coordinator} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('load the venue catalogue')
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeDisabled()
})

// -- The status rule -------------------------------------------------------------

it.each(['Rejected', 'Cancelled', 'Confirmed', 'Completed'] as const)(
  'tells the Coordinator why a %s event takes no more requests',
  async (status) => {
    listBookingsMock.mockResolvedValue([booking()])

    render(<EventBookings event={event({ status })} session={coordinator} />)

    expect(
      await screen.findByText('This event is closed, so no more venues can be requested for it.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request venue' })).not.toBeInTheDocument()
    expect(listVenuesMock).not.toHaveBeenCalled()
    // The bookings it had are still shown.
    expect(within(bookingList()).getByText('Great Hall')).toBeInTheDocument()
  },
)

it.each(['Approved', 'Planning'] as const)(
  'offers the form on a %s event',
  async (status) => {
    render(<EventBookings event={event({ status })} session={coordinator} />)

    await formReady()
    expect(screen.getByRole('button', { name: 'Request venue' })).toBeEnabled()
  },
)

// -- Formatting ------------------------------------------------------------------

it('shows only the end time when a booking is within one day', () => {
  const text = formatBookingTimes('2027-11-02T09:00:00', '2027-11-02T17:00:00')

  expect(text.split(' – ')).toHaveLength(2)
  expect(text.split(' – ')[1]).not.toMatch(/2027/)
})

it('shows both dates in full when a booking runs past midnight', () => {
  const text = formatBookingTimes('2027-11-02T20:00:00', '2027-11-03T02:00:00')

  expect(text.split(' – ')[1]).toMatch(/2027/)
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

it('offers the Coordinator a cancel for each Requested booking', async () => {
  listBookingsMock.mockResolvedValue([booking(), BREAKOUT])

  render(<EventBookings event={event()} session={coordinator} />)

  expect(
    await screen.findByRole('button', { name: 'Cancel the Great Hall booking' }),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Cancel the Seminar Room 4 booking' }),
  ).toBeInTheDocument()
})

it('offers the Organiser no cancel', async () => {
  listBookingsMock.mockResolvedValue([booking()])

  render(<EventBookings event={event()} session={organiser} />)

  await screen.findByRole('list')
  expect(screen.queryByRole('button', { name: /^Cancel the/ })).not.toBeInTheDocument()
})

it('offers no cancel on a booking that is already cancelled', async () => {
  listBookingsMock.mockResolvedValue([cancelled()])

  render(<EventBookings event={event()} session={coordinator} />)

  await screen.findByRole('list')
  expect(screen.queryByRole('button', { name: /^Cancel the/ })).not.toBeInTheDocument()
})

it('still offers a cancel on a closed event, to give the venue back', async () => {
  listBookingsMock.mockResolvedValue([booking()])

  render(<EventBookings event={event({ status: 'Rejected' })} session={coordinator} />)

  expect(
    await screen.findByRole('button', { name: 'Cancel the Great Hall booking' }),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request venue' })).not.toBeInTheDocument()
})

it('asks for a reason under the booking being cancelled', async () => {
  listBookingsMock.mockResolvedValue([booking(), BREAKOUT])
  render(<EventBookings event={event()} session={coordinator} />)

  await openCancel('Seminar Room 4')

  const row = rowFor('Seminar Room 4')
  expect(within(row).getByLabelText('Why are you cancelling this booking?')).toBeInTheDocument()
  expect(within(row).getByRole('button', { name: 'Cancel booking' })).toBeDisabled()
  expect(
    within(rowFor('Great Hall')).queryByLabelText('Why are you cancelling this booking?'),
  ).not.toBeInTheDocument()
})

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

it('leaves the other bookings exactly as they were', async () => {
  listBookingsMock.mockResolvedValue([booking(), BREAKOUT])
  cancelBookingMock.mockResolvedValue(cancelled())
  render(<EventBookings event={event()} session={coordinator} />)

  const user = await openCancel()
  await user.type(screen.getByLabelText('Why are you cancelling this booking?'), REASON)
  await user.click(screen.getByRole('button', { name: 'Cancel booking' }))

  await screen.findByText(/Cancelled Great Hall\./)
  const breakout = rowFor('Seminar Room 4')
  expect(within(breakout).getByText('Requested')).toBeInTheDocument()
  expect(
    within(breakout).getByRole('button', { name: 'Cancel the Seminar Room 4 booking' }),
  ).toBeInTheDocument()
  expect(within(bookingList()).getAllByRole('listitem')).toHaveLength(2)
})

it('keeps the box open with the reason when the cancel is refused', async () => {
  listBookingsMock.mockResolvedValue([booking()])
  cancelBookingMock.mockRejectedValue(
    new EventRuleError('This booking has already been cancelled.'),
  )
  render(<EventBookings event={event()} session={coordinator} />)

  const user = await openCancel()
  await user.type(screen.getByLabelText('Why are you cancelling this booking?'), REASON)
  await user.click(screen.getByRole('button', { name: 'Cancel booking' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'This booking has already been cancelled.',
  )
  expect(screen.getByLabelText('Why are you cancelling this booking?')).toHaveValue(REASON)
  expect(within(rowFor('Great Hall')).getByText('Requested')).toBeInTheDocument()
})

it('explains an unexpected failure to cancel', async () => {
  listBookingsMock.mockResolvedValue([booking()])
  cancelBookingMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))
  render(<EventBookings event={event()} session={coordinator} />)

  const user = await openCancel()
  await user.type(screen.getByLabelText('Why are you cancelling this booking?'), REASON)
  await user.click(screen.getByRole('button', { name: 'Cancel booking' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('cancel this booking')
})

it('keeps the booking when the Coordinator changes their mind', async () => {
  listBookingsMock.mockResolvedValue([booking()])
  render(<EventBookings event={event()} session={coordinator} />)

  const user = await openCancel()
  await user.type(screen.getByLabelText('Why are you cancelling this booking?'), REASON)
  await user.click(screen.getByRole('button', { name: 'Keep booking' }))

  expect(screen.queryByLabelText('Why are you cancelling this booking?')).not.toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Cancel the Great Hall booking' }),
  ).toBeInTheDocument()
  expect(cancelBookingMock).not.toHaveBeenCalled()
})

it('shows a cancelled booking from the server with who, when and why', async () => {
  listBookingsMock.mockResolvedValue([cancelled()])

  render(<EventBookings event={event()} session={organiser} />)

  const row = await screen.findByRole('listitem')
  expect(row).toHaveTextContent('Cancelled by Priya')
  // cancelled_at is naive UTC, so 10:00 there is 18:00 in Singapore.
  expect(row).toHaveTextContent('08 Oct 2026, 18:00')
  expect(row).toHaveTextContent(REASON)
})

it('still shows the reason when the user who cancelled has been removed', async () => {
  listBookingsMock.mockResolvedValue([
    cancelled({
      cancellation: { at: '2026-10-08T10:00:00', byId: null, byName: '', reason: REASON },
    }),
  ])

  render(<EventBookings event={event()} session={organiser} />)

  expect(await screen.findByRole('listitem')).toHaveTextContent(
    `Cancelled by a former user, 08 Oct 2026, 18:00: ${REASON}`,
  )
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

it('starts the headcount at the event attendance', async () => {
  render(<EventBookings event={event()} session={coordinator} />)

  await formReady()
  expect(screen.getByLabelText('Headcount')).toHaveValue(300)
})

it('leaves the headcount for the Coordinator when the event has no attendance', async () => {
  render(<EventBookings event={event({ expectedAttendance: null })} session={coordinator} />)

  await formReady()
  expect(screen.getByLabelText('Headcount')).toHaveValue(null)
})

it('checks a venue as soon as it is picked, and says Suitable', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()
  expect(checkSuitabilityMock).not.toHaveBeenCalled()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(await screen.findByText('Suitable')).toBeInTheDocument()
  expect(checkSuitabilityMock).toHaveBeenCalledWith(
    '900',
    {
      venueId: '1',
      startsAt: '2027-11-02T09:00',
      endsAt: '2027-11-02T17:00',
      headcount: '300',
      layout: '',
      facilities: '',
      accessibilityNeeds: '',
    },
    coordinator,
  )
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeEnabled()
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

it('checks again with the booking\'s own headcount', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockImplementation(async (_eventId, input) =>
    Number(input.headcount) > 60 ? NOT_SUITABLE : verdictOf({ venueId: '3' }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()
  await user.selectOptions(screen.getByLabelText('Venue'), '3')
  await screen.findByText('Not suitable')

  await user.clear(screen.getByLabelText('Headcount'))
  await user.type(screen.getByLabelText('Headcount'), '40')

  expect(await screen.findByText('Suitable')).toBeInTheDocument()
  expect(screen.queryByText('Not suitable')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeEnabled()
  expect(checkSuitabilityMock).toHaveBeenLastCalledWith(
    '900',
    expect.objectContaining({ venueId: '3', headcount: '40' }),
    coordinator,
  )
})

it('shows what could not be checked alongside the verdict', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(
    verdictOf({
      notes: ['Its operating hours are not recorded, so the booking time was not checked.'],
    }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(
    await screen.findByText(
      'Its operating hours are not recorded, so the booking time was not checked.',
    ),
  ).toBeInTheDocument()
})

it('shows a check the server refuses in place of a verdict', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockRejectedValue(new EventRuleError('A booking cannot start in the past.'))
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(await screen.findByText('A booking cannot start in the past.')).toBeInTheDocument()
  expect(screen.queryByText('Suitable')).not.toBeInTheDocument()
})

it('does not check while the form would be refused anyway', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event({ expectedAttendance: null })} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  await new Promise((resolve) => setTimeout(resolve, 400))
  expect(checkSuitabilityMock).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Request venue' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Give the headcount for this booking.')
})

it('refuses a headcount of nobody before sending anything', async () => {
  const user = userEvent.setup()
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.clear(screen.getByLabelText('Headcount'))
  await user.type(screen.getByLabelText('Headcount'), '0')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(screen.getByRole('alert')).toHaveTextContent('The headcount must be at least 1.')
  expect(requestBookingMock).not.toHaveBeenCalled()
})

it('sends what the booking needs with the request', async () => {
  const user = userEvent.setup()
  requestBookingMock.mockResolvedValue(booking())
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.clear(screen.getByLabelText('Headcount'))
  await user.type(screen.getByLabelText('Headcount'), '120')
  await user.type(screen.getByLabelText('Layout (optional)'), 'Theatre')
  await user.type(screen.getByLabelText('Facilities needed (optional)'), 'projector, PA system')
  await user.type(screen.getByLabelText('Accessibility needs (optional)'), 'hearing loop')
  await screen.findByText('Suitable')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  await waitFor(() =>
    expect(requestBookingMock).toHaveBeenCalledWith(
      '900',
      expect.objectContaining({
        headcount: '120',
        layout: 'Theatre',
        facilities: 'projector, PA system',
        accessibilityNeeds: 'hearing loop',
      }),
      coordinator,
    ),
  )
})

it('shows a refusal when the server finds the venue unsuitable at request time', async () => {
  const user = userEvent.setup()
  requestBookingMock.mockRejectedValue(
    new EventRuleError('Great Hall is not suitable for this booking. It holds 500 people.'),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Great Hall is not suitable for this booking.',
  )
})

it('says what each booking was made for', async () => {
  listBookingsMock.mockResolvedValue([
    booking({
      headcount: 40,
      requiredLayout: 'Classroom',
      requiredFacilities: ['projector', 'whiteboard'],
      accessibilityNeeds: ['step-free access'],
    }),
  ])

  render(<EventBookings event={event()} session={organiser} />)

  expect(await screen.findByRole('listitem')).toHaveTextContent(
    'For 40 people · Classroom layout · Needs projector, whiteboard · Access: step-free access',
  )
})

it('says nothing about needs on a booking made before there were any', async () => {
  listBookingsMock.mockResolvedValue([booking({ headcount: null })])

  render(<EventBookings event={event()} session={organiser} />)

  const row = await screen.findByRole('listitem')
  expect(row).not.toHaveTextContent('For ')
  expect(row.querySelector('.booking-needs')).toBeNull()
})

it('suggests every layout the catalogue lists, once each', async () => {
  listVenuesMock.mockResolvedValue([
    { ...venue('1', 'Great Hall', 500), supportedLayouts: 'Theatre, cabaret' },
    { ...venue('3', 'Seminar Room 4', 60), supportedLayouts: '{theatre,"breakout tables"}' },
  ])
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  const options = [...document.querySelectorAll('#booking-layouts option')].map(
    (option) => (option as HTMLOptionElement).value,
  )
  expect(options).toEqual(['breakout tables', 'cabaret', 'Theatre'])
})

// -- US14.3: tentative holds ---------------------------------------------------

const requestHeldBookingMock = vi.mocked(requestHeldBooking)

function held(overrides: Partial<BookingRecord> = {}): BookingRecord {
  return booking({
    status: 'Held',
    holdExpiresAt: '2027-10-08T17:00:00',
    holdExpired: false,
    heldByName: 'Sam',
    ...overrides,
  })
}

it('TC-HF01 shows a hold as Held with who placed it and when it expires', async () => {
  listBookingsMock.mockResolvedValue([held()])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Held')
  expect(row).toHaveTextContent(
    `Held by Sam until ${formatTimestamp('2027-10-08T17:00:00')}. Request it before then`,
  )
  expect(row).not.toHaveTextContent('Confirmed')
})

it('TC-HF02 lets the Coordinator request a held venue', async () => {
  const onBookingRequested = vi.fn()
  listBookingsMock.mockResolvedValue([held()])
  requestHeldBookingMock.mockResolvedValue(held({ status: 'Requested' }))
  render(
    <EventBookings event={event()} session={coordinator} onBookingRequested={onBookingRequested} />,
  )

  await userEvent.click(await screen.findByRole('button', { name: 'Request the held Great Hall' }))

  expect(requestHeldBookingMock).toHaveBeenCalledWith('900', '101', coordinator)
  const row = within(bookingList()).getByRole('listitem')
  await waitFor(() => expect(row).toHaveTextContent('Requested'))
  expect(row).toHaveTextContent('Requested from a hold by Sam.')
  expect(screen.getByRole('status')).toHaveTextContent('Requested Great Hall.')
  expect(onBookingRequested).toHaveBeenCalled()
})

it('TC-HF03 shows an expired hold as expired, with nothing to do', async () => {
  listBookingsMock.mockResolvedValue([held({ holdExpired: true })])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Hold expired')
  expect(row).toHaveTextContent('The venue is no longer kept for this event.')
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
})

// US14.4: what the scheduled sweep writes. It reads like a lapsed Held hold.
it('shows a hold the sweep marked Expired as expired, with nothing to do', async () => {
  listBookingsMock.mockResolvedValue([held({ status: 'Expired', holdExpired: true })])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Hold expired')
  expect(row).toHaveTextContent(
    `Hold expired ${formatTimestamp('2027-10-08T17:00:00')}. The venue is no longer kept`,
  )
  expect(row).not.toHaveTextContent('Requested from a hold')
  expect(row).toHaveClass('is-expired')
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
})

it('TC-HF04 shows the server refusal under the hold', async () => {
  listBookingsMock.mockResolvedValue([held()])
  requestHeldBookingMock.mockRejectedValue(
    new EventRuleError('The hold on Great Hall expired at 2027-10-08 17:00.'),
  )
  render(<EventBookings event={event()} session={coordinator} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Request the held Great Hall' }))

  const row = within(bookingList()).getByRole('listitem')
  expect(await within(row).findByRole('alert')).toHaveTextContent(
    'The hold on Great Hall expired at 2027-10-08 17:00.',
  )
})

it('TC-HF05 offers the Organiser no way to request a hold', async () => {
  listBookingsMock.mockResolvedValue([held()])
  render(<EventBookings event={event()} session={organiser} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Held')
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
})

it('TC-HF06 offers no request on an event that cannot take bookings', async () => {
  listBookingsMock.mockResolvedValue([held()])
  render(<EventBookings event={event({ status: 'Cancelled' })} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(
    within(row).queryByRole('button', { name: 'Request the held Great Hall' }),
  ).not.toBeInTheDocument()
})

it('TC-HF07 lets the Coordinator release a hold with Cancel', async () => {
  listBookingsMock.mockResolvedValue([held()])
  render(<EventBookings event={event()} session={coordinator} />)

  expect(
    await screen.findByRole('button', { name: 'Cancel the Great Hall booking' }),
  ).toBeInTheDocument()
})

// -- US16.1: Venue Staff's decision, as the Coordinator sees it ---------------------

it('TC-DF21 shows a confirmed booking with who confirmed it, and no Cancel', async () => {
  listBookingsMock.mockResolvedValue([
    booking({
      status: 'Confirmed',
      decision: { at: '2027-10-01T01:00:00', byId: '4', byName: 'Sam', reason: '', suggestion: '' },
    }),
  ])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Confirmed')
  expect(row).toHaveTextContent(`Confirmed by Sam, ${formatTimestamp('2027-10-01T01:00:00')}.`)
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
})

it('TC-DF22 shows a rejection with its reason and suggestion, and no Cancel', async () => {
  listBookingsMock.mockResolvedValue([
    booking({
      status: 'Rejected',
      decision: {
        at: '2027-10-01T01:00:00',
        byId: '4',
        byName: 'Sam',
        reason: 'Closed that week.',
        suggestion: 'Bertha Room on 9 Nov',
      },
    }),
  ])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Rejected')
  expect(row).toHaveTextContent('Closed that week.')
  expect(row).toHaveTextContent('Suggested instead: Bertha Room on 9 Nov')
  expect(within(row).queryByRole('button')).not.toBeInTheDocument()
})

it('TC-DF23 shows a rejection without a suggestion as just the reason', async () => {
  listBookingsMock.mockResolvedValue([
    booking({
      status: 'Rejected',
      decision: { at: '2027-10-01T01:00:00', byId: null, byName: '', reason: 'Closed.', suggestion: '' },
    }),
  ])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Rejected by a former user')
  expect(row).not.toHaveTextContent('Suggested instead')
})

// -- US15.1: is the slot free, setup and turnaround included -------------------------

it('TC-CF01 says Available with the full window the booking would occupy', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(
    verdictOf({
      available: true,
      clashes: [],
      occupiedFrom: '2027-11-02T08:30',
      occupiedTo: '2027-11-02T17:45',
    }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(
    await screen.findByText(
      `Available: the venue would be occupied ${formatBookingTimes(
        '2027-11-02T08:30',
        '2027-11-02T17:45',
      )}, setup and turnaround included.`,
    ),
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeEnabled()
})

it('TC-CF02 says Not available with each clash, and will not request it', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(
    verdictOf({
      available: false,
      clashes: [
        'booking #12 (Confirmed) occupying 2027-11-02 16:00 to 2027-11-02 19:45',
        "the venue's unavailable period 2027-11-02 (Maintenance)",
      ],
      occupiedFrom: '2027-11-02T08:30',
      occupiedTo: '2027-11-02T17:45',
    }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(await screen.findByText('Not available')).toBeInTheDocument()
  expect(
    screen.getByText(
      `With setup and turnaround it would occupy ${formatBookingTimes(
        '2027-11-02T08:30',
        '2027-11-02T17:45',
      )}, which overlaps:`,
    ),
  ).toBeInTheDocument()
  expect(
    screen.getByText('booking #12 (Confirmed) occupying 2027-11-02 16:00 to 2027-11-02 19:45'),
  ).toBeInTheDocument()
  expect(
    screen.getByText("the venue's unavailable period 2027-11-02 (Maintenance)"),
  ).toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Request venue' })
  expect(button).toBeDisabled()
  expect(button).toHaveAttribute('title', 'This venue is already taken for this slot.')
  expect(requestBookingMock).not.toHaveBeenCalled()
})

it('TC-CF03 still names the clashes when the window is missing', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(
    verdictOf({ available: false, clashes: ['booking #12 (Held) occupying x to y'] }),
  )
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(await screen.findByText('Not available')).toBeInTheDocument()
  expect(screen.getByText('booking #12 (Held) occupying x to y')).toBeInTheDocument()
  expect(screen.queryByText(/which overlaps:/)).not.toBeInTheDocument()
})

it('TC-CF04 reads a bare Available when the window is missing', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(verdictOf({ available: true }))
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  expect(await screen.findByText('Available')).toBeInTheDocument()
})

it('TC-CF05 reads an answer without availability as free, and says nothing about it', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue(verdictOf())
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '1')

  await screen.findByText('Suitable')
  expect(screen.queryByText(/Available/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Request venue' })).toBeEnabled()
})

it('TC-CF06 an unsuitable venue explains that first, even when the slot is taken too', async () => {
  const user = userEvent.setup()
  checkSuitabilityMock.mockResolvedValue({ ...NOT_SUITABLE, available: false, clashes: ['x'] })
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()

  await user.selectOptions(screen.getByLabelText('Venue'), '3')

  await screen.findByText('Not available')
  expect(screen.getByRole('button', { name: 'Request venue' })).toHaveAttribute(
    'title',
    'This venue is not suitable for this booking.',
  )
})

it('TC-CF07 shows the server refusal naming the clash at request time', async () => {
  const user = userEvent.setup()
  const message =
    'Great Hall is not available for this booking. With setup and turnaround it would occupy ' +
    '2027-11-02 08:30 to 2027-11-02 17:45, which overlaps booking #12 (Confirmed) occupying ' +
    '2027-11-02 16:00 to 2027-11-02 19:45.'
  requestBookingMock.mockRejectedValue(new EventRuleError(message))
  render(<EventBookings event={event()} session={coordinator} />)
  await formReady()
  await user.selectOptions(screen.getByLabelText('Venue'), '1')
  await screen.findByText('Suitable')

  await user.click(screen.getByRole('button', { name: 'Request venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(message)
})

// -- US15.2: a booking flagged after a setup or turnaround change -----------------

it('TC-FF01 shows the flag with its reason, keeping the status', async () => {
  const reason =
    'With 30 minutes setup and 45 minutes turnaround it occupies 2027-11-02 08:30 to ' +
    '2027-11-02 17:45, which overlaps booking #12 (Requested) occupying 2027-11-02 17:00 to ' +
    '2027-11-02 19:45.'
  listBookingsMock.mockResolvedValue([
    booking({
      status: 'Confirmed',
      conflict: { label: CONFLICT_LABEL, flaggedAt: '2027-10-01T01:00:00', reason },
    }),
  ])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent('Confirmed')
  const note = within(row).getByRole('note')
  expect(note).toHaveTextContent('Conflict – review needed')
  expect(note).toHaveTextContent(
    `Flagged ${formatTimestamp('2027-10-01T01:00:00')}: ${reason} Nothing has been cancelled.`,
  )
})

it('TC-FF02 shows no flag on a booking that has none', async () => {
  listBookingsMock.mockResolvedValue([booking({ conflict: null })])
  render(<EventBookings event={event()} session={coordinator} />)

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).not.toHaveTextContent('Conflict – review needed')
  expect(within(row).queryByRole('note')).not.toBeInTheDocument()
})
