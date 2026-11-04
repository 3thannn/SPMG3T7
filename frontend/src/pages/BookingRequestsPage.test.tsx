/**
 * Venue Staff's booking requests page — US16.1.
 *
 * The rules (who decides, the clash check, the reason) are the server's and are
 * tested in backend/tests/test_booking_decisions.py. This page's job is the
 * queue as the server orders it, with what a decision needs, the decisions
 * (approve, approve as a tentative hold, reject), and showing why one was
 * refused.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import BookingRequestsPage from './BookingRequestsPage'
import {
  approveBookingRequest,
  listBookingRequests,
  rejectBookingRequest,
  type BookingRequest,
} from '../bookingRequestsStore'
import { buildSession } from '../test/sessions'

vi.mock('../bookingRequestsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../bookingRequestsStore')>()),
  listBookingRequests: vi.fn(),
  approveBookingRequest: vi.fn(),
  rejectBookingRequest: vi.fn(),
}))

const listMock = vi.mocked(listBookingRequests)

const rejectMock = vi.mocked(rejectBookingRequest)
const approveMock = vi.mocked(approveBookingRequest)
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
  expect(within(row).getByRole('button', { name: 'Approve Great Hall for Open Day' })).toBeDisabled()
  expect(
    within(row).getByRole('button', { name: 'Approve Great Hall for Open Day as a tentative hold' }),
  ).toBeDisabled()
  expect(within(row).getByRole('button', { name: /^Reject/ })).toBeEnabled()
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


it('TC-DF15 approves as a tentative hold until an expiry (US14.3)', async () => {
  approveMock.mockResolvedValue(
    request({ status: 'Held', holdExpiresAt: '2027-10-08T17:00:00', heldByName: 'Sam' }),
  )
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Approve Great Hall for Open Day as a tentative hold',
    }),
  )
  await userEvent.type(screen.getByLabelText('Hold until'), '2027-10-08T17:00')
  await userEvent.click(screen.getByRole('button', { name: 'Approve as tentative hold' }))

  expect(approveMock).toHaveBeenCalledWith('11', staff, '2027-10-08T17:00')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Approved Great Hall for Open Day as a tentative hold until',
  )
})

it('TC-DF16 asks for an expiry before approving as a hold', async () => {
  render(<BookingRequestsPage session={staff} />)
  await userEvent.click(
    await screen.findByRole('button', {
      name: 'Approve Great Hall for Open Day as a tentative hold',
    }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Approve as tentative hold' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the hold an expiry date and time.')
  expect(approveMock).not.toHaveBeenCalled()
})
