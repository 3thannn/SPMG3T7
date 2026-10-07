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
  EventRuleError,
  cancelBooking,
  checkSuitability,
  formatBookingTimes,
  listBookings,
  requestBooking,
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
  requestBookingMock.mockResolvedValue(booking())
  render(<EventBookings event={event()} session={coordinator} />)
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

it.each(['Rejected', 'Cancelled', 'Completed'] as const)(
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

it.each(['Submitted', 'Under Review', 'Approved', 'Planning', 'Confirmed'] as const)(
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
  expect(row).toHaveTextContent(
    `Cancelled by Priya, ${formatTimestamp('2026-10-08T10:00:00')}: ${REASON}`,
  )
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
    `Cancelled by a former user, ${formatTimestamp('2026-10-08T10:00:00')}: ${REASON}`,
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
