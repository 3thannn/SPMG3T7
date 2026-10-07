/**
 * The venue bookings card on an event — US14.1.
 *
 * Who may request, and for which events, is the server's call and is tested in
 * backend/tests/test_venue_bookings.py. This card's job is showing every booking
 * for the event together, offering the form to the assigned Coordinator, and
 * keeping each request on its own so one refusal does not undo another.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EventBookings from './EventBookings'
import {
  EventRuleError,
  formatBookingTimes,
  listBookings,
  requestBooking,
  type BookingRecord,
  type EventRecord,
} from '../eventsStore'
import { listVenues, type VenueRecord } from '../venuesStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  requestBooking: vi.fn(),
}))

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(async () => []),
}))

const listBookingsMock = vi.mocked(listBookings)
const requestBookingMock = vi.mocked(requestBooking)
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
    ...overrides,
  }
}

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
      { venueId: '1', startsAt: '2027-11-02T09:00', endsAt: '2027-11-02T17:00' },
      coordinator,
    ),
  )
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Requested Great Hall. It is waiting for Venue Staff to approve it.',
  )
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

  await screen.findByRole('status')
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
