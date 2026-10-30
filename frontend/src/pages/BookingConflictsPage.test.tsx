/**
 * Venue Staff's booking conflicts page — US15.2.
 *
 * Which bookings are flagged, why, and when a flag clears are the server's
 * rules, tested in backend/tests/test_booking_conflicts.py. This page's job is
 * the flagged list as the server orders it, with what a review needs, and a
 * way on to the decision for a flagged request.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import BookingConflictsPage from './BookingConflictsPage'
import { listBookingConflicts, type FlaggedBooking } from '../bookingConflictsStore'
import { CONFLICT_LABEL, formatBookingTimes } from '../eventsStore'
import { formatRecordedAt } from '../status'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../bookingConflictsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../bookingConflictsStore')>()),
  listBookingConflicts: vi.fn(),
}))

const listMock = vi.mocked(listBookingConflicts)
const staff = buildSession({ role: 'Venue Staff', id: '4', name: 'Sam' })

const REASON =
  'With 30 minutes setup and 45 minutes turnaround it occupies 2027-11-02 09:30 to ' +
  '2027-11-02 12:45, which overlaps booking #11 (Requested) occupying 2027-11-02 12:00 to ' +
  '2027-11-02 14:45.'

function flagged(overrides: Partial<FlaggedBooking> = {}): FlaggedBooking {
  return {
    id: '10',
    eventId: '900',
    eventTitle: 'Open Day',
    coordinatorName: 'Priya',
    venueId: '1',
    venueName: 'Great Hall',
    startsAt: '2027-11-02T10:00:00',
    endsAt: '2027-11-02T12:00:00',
    occupiedFrom: '2027-11-02T09:30',
    occupiedTo: '2027-11-02T12:45',
    setupMinutes: 30,
    turnaroundMinutes: 45,
    status: 'Confirmed',
    requestedAt: '2027-09-01T09:00:00',
    headcount: 120,
    requiredLayout: '',
    requiredFacilities: [],
    accessibilityNeeds: [],
    cancellation: null,
    conflict: { label: CONFLICT_LABEL, flaggedAt: '2027-10-01T01:00:00', reason: REASON },
    clashes: [
      {
        bookingId: '11',
        eventTitle: 'Board Retreat',
        status: 'Requested',
        startsAt: '2027-11-02T12:30:00',
        endsAt: '2027-11-02T14:00:00',
        occupiedFrom: '2027-11-02T12:00',
        occupiedTo: '2027-11-02T14:45',
      },
    ],
    unavailable: [],
    label: CONFLICT_LABEL,
    ...overrides,
  }
}

beforeEach(() => {
  window.location.hash = '#/booking-conflicts'
})

afterEach(() => {
  vi.resetAllMocks()
})

it('TC-FF07 lists every flagged booking in the server order, with what a review needs', async () => {
  listMock.mockResolvedValue([
    flagged(),
    flagged({ id: '11', eventTitle: 'Board Retreat', status: 'Requested' }),
  ])

  render(<BookingConflictsPage session={staff} />)

  const list = await screen.findByRole('list', { name: 'Flagged bookings' })
  const headings = within(list).getAllByRole('heading', { level: 2 })
  expect(headings.map((h) => h.textContent)).toEqual(['Open Day', 'Board Retreat'])
  const first = headings[0].closest('li') as HTMLElement
  expect(first).toHaveTextContent('Conflict – review needed')
  expect(first).toHaveTextContent('Great Hall')
  expect(first).toHaveTextContent('Confirmed')
  expect(first).toHaveTextContent(
    formatBookingTimes('2027-11-02T10:00:00', '2027-11-02T12:00:00'),
  )
  expect(first).toHaveTextContent(
    `${formatBookingTimes('2027-11-02T09:30', '2027-11-02T12:45')} (30 minutes setup, 45 minutes turnaround)`,
  )
  expect(first).toHaveTextContent('Priya')
  expect(first).toHaveTextContent(
    `Flagged ${formatRecordedAt('2027-10-01T01:00:00')}: ${REASON}`,
  )
  expect(first).toHaveTextContent(
    `Booking #11, Board Retreat (Requested), occupying ${formatBookingTimes(
      '2027-11-02T12:00',
      '2027-11-02T14:45',
    )}`,
  )
  expect(listMock).toHaveBeenCalledWith(staff)
})

it('TC-FF08 names an unavailability period the booking now overlaps', async () => {
  listMock.mockResolvedValue([
    flagged({
      clashes: [],
      unavailable: [
        { id: '5', startDate: '2027-11-01', endDate: '2027-11-03', reason: 'Closure' },
        { id: '6', startDate: '2027-11-02', endDate: '2027-11-02', reason: '' },
      ],
    }),
  ])

  render(<BookingConflictsPage session={staff} />)

  expect(await screen.findByText('Venue unavailable 2027-11-01 to 2027-11-03 (Closure)'))
    .toBeInTheDocument()
  expect(screen.getByText('Venue unavailable 2027-11-02')).toBeInTheDocument()
})

it('TC-FF09 says when nothing clashes with it any more', async () => {
  listMock.mockResolvedValue([flagged({ clashes: [], unavailable: undefined })])

  render(<BookingConflictsPage session={staff} />)

  expect(
    await screen.findByText('Nothing clashes with it any more. Refresh to clear the flag.'),
  ).toBeInTheDocument()
})

it('TC-FF10 offers a flagged request the way on to its decision, and nothing else', async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValue([
    flagged(),
    flagged({ id: '11', eventTitle: 'Board Retreat', status: 'Requested' }),
  ])

  render(<BookingConflictsPage session={staff} />)
  const [decide] = await screen.findAllByRole('button', { name: 'Decide on Booking Requests' })

  expect(screen.getAllByRole('button', { name: 'Decide on Booking Requests' })).toHaveLength(1)
  await user.click(decide)
  expect(window.location.hash).toBe('#/booking-requests')
})

it('TC-FF11 fills in what the record leaves out', async () => {
  listMock.mockResolvedValue([
    flagged({
      label: '',
      venueName: '',
      eventTitle: '',
      coordinatorName: '',
      setupMinutes: 1,
      turnaroundMinutes: 1,
      conflict: null,
    }),
  ])

  render(<BookingConflictsPage session={staff} />)

  const list = await screen.findByRole('list', { name: 'Flagged bookings' })
  expect(list).toHaveTextContent('Conflict – review needed')
  expect(list).toHaveTextContent('Unnamed venue')
  expect(list).toHaveTextContent('Not assigned')
  expect(list).toHaveTextContent('(1 minute setup, 1 minute turnaround)')
  expect(list).not.toHaveTextContent('Flagged ')
})

it('TC-FF12 says so when nothing is flagged', async () => {
  listMock.mockResolvedValue([])

  render(<BookingConflictsPage session={staff} />)

  expect(await screen.findByRole('heading', { name: 'No booking conflicts' })).toBeInTheDocument()
})

it('TC-FF13 shows a list that will not load as an error', async () => {
  listMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))

  render(<BookingConflictsPage session={staff} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not load the flagged bookings. The API answered HTTP 500',
  )
})

it('TC-FF14 reads the list again on Refresh, so resolved flags drop off', async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValueOnce([flagged()]).mockResolvedValueOnce([])

  render(<BookingConflictsPage session={staff} />)
  await screen.findByRole('list', { name: 'Flagged bookings' })

  await user.click(screen.getByRole('button', { name: 'Refresh' }))

  expect(await screen.findByRole('heading', { name: 'No booking conflicts' })).toBeInTheDocument()
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
})

it('TC-FF15 shows loading until the list arrives', () => {
  listMock.mockReturnValue(new Promise(() => {}))

  render(<BookingConflictsPage session={staff} />)

  expect(screen.getByText('Loading flagged bookings…')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled()
})
