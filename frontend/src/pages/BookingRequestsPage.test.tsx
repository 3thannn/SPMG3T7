/**
 * Venue Staff's booking requests page — US16.1.
 *
 * The rules (who decides, the clash check, the reason) are the server's and are
 * tested in backend/tests/test_booking_decisions.py. This page's job is the
 * queue as the server orders it, with what a decision needs, the two decisions,
 * and showing why one was refused.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import BookingRequestsPage from './BookingRequestsPage'
import {
  approveBookingRequest,
  listBookingRequests,
  rejectBookingRequest,
  type BookingRequest,
} from '../bookingRequestsStore'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../bookingRequestsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../bookingRequestsStore')>()),
  listBookingRequests: vi.fn(),
  approveBookingRequest: vi.fn(),
  rejectBookingRequest: vi.fn(),
}))

const listMock = vi.mocked(listBookingRequests)
const approveMock = vi.mocked(approveBookingRequest)
const rejectMock = vi.mocked(rejectBookingRequest)
const staff = buildSession({ role: 'Venue Staff', id: '4', name: 'Sam' })

function request(overrides: Partial<BookingRequest> = {}): BookingRequest {
  return {
    id: '11',
    eventId: '900',
    eventTitle: 'Open Day',
    coordinatorName: 'Priya',
    venueId: '1',
    venueName: 'Great Hall',
    startsAt: '2027-11-02T09:00:00',
    endsAt: '2027-11-02T17:00:00',
    occupiedFrom: '2027-11-02T08:30',
    occupiedTo: '2027-11-02T17:45',
    setupMinutes: 30,
    turnaroundMinutes: 45,
    status: 'Requested',
    requestedAt: '2027-09-01T09:00:00',
    headcount: 120,
    requiredLayout: 'Theatre',
    requiredFacilities: [],
    accessibilityNeeds: [],
    cancellation: null,
    clashes: [],
    ...overrides,
  }
}

beforeEach(() => {
  listMock.mockResolvedValue([request()])
})

afterEach(() => {
  vi.resetAllMocks()
})

async function card(name = 'Open Day') {
  const heading = await screen.findByRole('heading', { name })
  return heading.closest('li') as HTMLElement
}

it('TC-DF06 shows each request with what a decision needs', async () => {
  render(<BookingRequestsPage session={staff} />)
  const row = await card()

  expect(row).toHaveTextContent('Coordinator: Priya')
  expect(row).toHaveTextContent('Great Hall')
  expect(row).toHaveTextContent(formatBookingTimes('2027-11-02T09:00:00', '2027-11-02T17:00:00'))
  expect(row).toHaveTextContent(formatBookingTimes('2027-11-02T08:30', '2027-11-02T17:45'))
  expect(row).toHaveTextContent('(30 minutes setup, 45 minutes turnaround)')
  expect(row).toHaveTextContent('120')
  expect(row).toHaveTextContent('Theatre')
})

it('TC-DF07 keeps the order the server sends, oldest first', async () => {
  listMock.mockResolvedValue([
    request({ id: '12', eventTitle: 'Careers Fair' }),
    request({ id: '11', eventTitle: 'Open Day' }),
  ])
  render(<BookingRequestsPage session={staff} />)
  const list = await screen.findByRole('list', { name: 'Booking requests' })
  expect(
    within(list)
      .getAllByRole('heading')
      .map((heading) => heading.textContent),
  ).toEqual(['Careers Fair', 'Open Day'])
})

it('TC-DF08 says when nothing is waiting', async () => {
  listMock.mockResolvedValue([])
  render(<BookingRequestsPage session={staff} />)
  expect(await screen.findByText('No booking requests waiting')).toBeInTheDocument()
})

it('TC-DF09 says so when the queue cannot be loaded', async () => {
  listMock.mockRejectedValue(new Error('network down'))
  render(<BookingRequestsPage session={staff} />)
  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not load the booking requests/)
})

it('TC-DF10 approves a request and takes it off the queue', async () => {
  approveMock.mockResolvedValue(request({ status: 'Confirmed' }))
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Approve Great Hall for Open Day' }),
  )

  expect(approveMock).toHaveBeenCalledWith('11', staff)
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Confirmed Great Hall for Open Day. The Coordinator has been notified.',
  )
  expect(screen.queryByRole('heading', { name: 'Open Day' })).not.toBeInTheDocument()
})

it('TC-DF11 shows a known clash and will not approve into it', async () => {
  listMock.mockResolvedValue([
    request({
      clashes: [
        {
          bookingId: '10',
          eventTitle: 'Careers Fair',
          status: 'Confirmed',
          startsAt: '2027-11-02T06:00',
          endsAt: '2027-11-02T08:00',
          occupiedFrom: '2027-11-02T05:30',
          occupiedTo: '2027-11-02T08:45',
        },
      ],
    }),
  ])
  render(<BookingRequestsPage session={staff} />)
  const row = await card()

  expect(within(row).getByRole('note')).toHaveTextContent(
    'Clashes with a booking that already takes this slot.',
  )
  expect(within(row).getByRole('note')).toHaveTextContent('Careers Fair (Confirmed)')
  expect(within(row).getByRole('button', { name: /^Approve/ })).toBeDisabled()
  expect(within(row).getByRole('button', { name: /^Reject/ })).toBeEnabled()
})

it('TC-DF12 shows the clash when the server blocks an approval, and refreshes', async () => {
  approveMock.mockRejectedValue(
    new EventRuleError('Great Hall is already taken for this slot by "Careers Fair".'),
  )
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Approve Great Hall for Open Day' }),
  )

  expect(await screen.findByRole('alert')).toHaveTextContent('already taken for this slot')
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
})

it('TC-DF13 needs a reason before rejecting', async () => {
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Reject Great Hall for Open Day' }))
  await userEvent.click(screen.getByRole('button', { name: 'Reject booking' }))

  expect(screen.getByRole('alert')).toHaveTextContent(
    'Give the Coordinator a reason for rejecting this booking.',
  )
  expect(rejectMock).not.toHaveBeenCalled()
})

it('TC-DF14 rejects with a reason and a suggested alternative', async () => {
  rejectMock.mockResolvedValue(request({ status: 'Rejected' }))
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Reject Great Hall for Open Day' }))
  await userEvent.type(
    screen.getByLabelText("Why can't this booking be supported?"),
    'Closed that week.',
  )
  await userEvent.type(
    screen.getByLabelText('Suggest another venue or time (optional)'),
    'Bertha Room',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Reject booking' }))

  expect(rejectMock).toHaveBeenCalledWith('11', 'Closed that week.', 'Bertha Room', staff)
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Rejected Great Hall for Open Day. The slot is free again',
  )
})

it('TC-DF15 Keep it closes the reject form without deciding', async () => {
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Reject Great Hall for Open Day' }))
  await userEvent.click(screen.getByRole('button', { name: 'Keep it' }))

  expect(screen.getByRole('button', { name: 'Approve Great Hall for Open Day' })).toBeEnabled()
  expect(rejectMock).not.toHaveBeenCalled()
})

it('TC-DF16 says something useful when a decision fails for another reason', async () => {
  approveMock.mockRejectedValue(new Error('network down'))
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Approve Great Hall for Open Day' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not approve this booking/)
  expect(listMock).toHaveBeenCalledTimes(1)
})

it('TC-DF17 a refused rejection is shown on its card', async () => {
  rejectMock.mockRejectedValue(new EventRuleError('This booking has already been rejected.'))
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Reject Great Hall for Open Day' }))
  await userEvent.type(screen.getByLabelText("Why can't this booking be supported?"), 'No.')
  await userEvent.click(screen.getByRole('button', { name: 'Reject booking' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already been rejected')
})

// -- US15.1 / US15.2 ------------------------------------------------------------------

it('TC-CF08 a request overlapping an unavailability period cannot be approved', async () => {
  listMock.mockResolvedValue([
    request({
      unavailable: [{ id: '5', startDate: '2027-11-02', endDate: '2027-11-02', reason: 'Flooded' }],
    }),
  ])
  render(<BookingRequestsPage session={staff} />)
  const row = await card()

  const note = within(row).getByRole('note')
  expect(note).toHaveTextContent(
    'The venue is unavailable for this slot. It cannot be approved while this remains:',
  )
  expect(note).toHaveTextContent('Venue unavailable 2027-11-02 (Flooded)')
  expect(within(row).getByRole('button', { name: /^Approve/ })).toBeDisabled()
  expect(within(row).getByRole('button', { name: /^Reject/ })).toBeEnabled()
})

it('TC-CF09 names a booking clash first when there are both', async () => {
  listMock.mockResolvedValue([
    request({
      clashes: [
        {
          bookingId: '10',
          eventTitle: 'Careers Fair',
          status: 'Confirmed',
          startsAt: '2027-11-02T06:00',
          endsAt: '2027-11-02T08:00',
          occupiedFrom: '2027-11-02T05:30',
          occupiedTo: '2027-11-02T08:45',
        },
      ],
      unavailable: [
        { id: '5', startDate: '2027-11-01', endDate: '2027-11-03', reason: '' },
      ],
    }),
  ])
  render(<BookingRequestsPage session={staff} />)
  const note = within(await card()).getByRole('note')

  expect(note).toHaveTextContent('Clashes with a booking that already takes this slot.')
  expect(note).toHaveTextContent('Careers Fair (Confirmed)')
  expect(note).toHaveTextContent('Venue unavailable 2027-11-01 to 2027-11-03')
})

it('TC-FF17 shows a request flagged after a setup or turnaround change', async () => {
  listMock.mockResolvedValue([
    request({
      conflict: {
        label: 'Conflict – review needed',
        flaggedAt: '2027-10-01T01:00:00',
        reason: 'With 30 minutes setup and 45 minutes turnaround it occupies …',
      },
    }),
  ])
  render(<BookingRequestsPage session={staff} />)
  const row = await card()

  const [flag] = within(row).getAllByRole('note')
  expect(flag).toHaveTextContent('Conflict – review needed')
  expect(flag).toHaveTextContent('With 30 minutes setup and 45 minutes turnaround it occupies')
  // The flag alone does not block approval: the server's check does.
  expect(within(row).getByRole('button', { name: /^Approve/ })).toBeEnabled()
})

