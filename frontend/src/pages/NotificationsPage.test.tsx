/**
 * US10.1: the Organiser's notifications page — unread first, read state
 * toggled in place, and a useful message when there is nothing to show.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import NotificationsPage from './NotificationsPage'
import {
  listNotifications,
  setNotificationRead,
  type NotificationRecord,
} from '../notificationsStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../notificationsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../notificationsStore')>()),
  listNotifications: vi.fn(),
  setNotificationRead: vi.fn(),
}))

const listMock = vi.mocked(listNotifications)
const setReadMock = vi.mocked(setNotificationRead)

afterEach(() => {
  vi.resetAllMocks()
  window.location.hash = ''
})

const organiser = buildSession({ role: 'Event Organiser', id: '1' })
const support = buildSession({ role: 'Technical Support', id: '6' })

function notice(overrides: Partial<NotificationRecord> = {}): NotificationRecord {
  return {
    id: '1',
    eventId: '101',
    eventTitle: 'Gala',
    status: 'Approved',
    message: '"Gala" was approved.',
    read: false,
    createdAt: '2026-10-02T09:00:00',
    readAt: '',
    ...overrides,
  }
}

function group(name: 'Unread' | 'Read') {
  return screen.getByRole('region', { name: new RegExp(`^${name}`) })
}

it('opens an equipment notice at the specific request', async () => {
  listMock.mockResolvedValue([notice({
    status: null, kind: 'equipment-request', equipmentRequestId: '17',
    message: 'New microphone request.',
  })])
  render(<NotificationsPage session={support} />)
  const link = await screen.findByRole('link', { name: 'Open request' })
  expect(link).toHaveAttribute('href', '#/equipment-requests/17')
  expect(screen.getByText('Equipment request')).toBeInTheDocument()
  expect(screen.queryByText('Approved')).not.toBeInTheDocument()
})

it('TC-F05 shows unread notices before read ones', async () => {
  listMock.mockResolvedValue([
    notice({ id: '1', message: 'First unread' }),
    notice({ id: '2', message: 'Old news', read: true }),
  ])
  render(<NotificationsPage session={organiser} />)

  await screen.findByText('First unread')
  expect(within(group('Unread')).getByText('First unread')).toBeInTheDocument()
  expect(within(group('Read')).getByText('Old news')).toBeInTheDocument()
  const regions = screen.getAllByRole('region')
  expect(regions[0]).toBe(group('Unread'))
})

it('TC-F06 shows the status the event moved to', async () => {
  listMock.mockResolvedValue([notice({ status: 'Rejected', message: 'No.' })])
  render(<NotificationsPage session={organiser} />)
  expect(await screen.findByText('Rejected')).toBeInTheDocument()
})

it('TC-F07 marks a notice read and moves it to the read group', async () => {
  listMock.mockResolvedValue([notice()])
  setReadMock.mockResolvedValue(notice({ read: true, readAt: '2026-10-02T10:00:00' }))
  render(<NotificationsPage session={organiser} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Mark as read' }))

  expect(setReadMock).toHaveBeenCalledWith('1', true, organiser)
  expect(within(group('Read')).getByText('"Gala" was approved.')).toBeInTheDocument()
  expect(within(group('Unread')).getByText('You are all caught up.')).toBeInTheDocument()
})

it('TC-F08 marks a read notice unread again', async () => {
  listMock.mockResolvedValue([notice({ read: true, readAt: '2026-10-02T10:00:00' })])
  setReadMock.mockResolvedValue(notice())
  render(<NotificationsPage session={organiser} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Mark as unread' }))

  expect(setReadMock).toHaveBeenCalledWith('1', false, organiser)
  expect(within(group('Unread')).getByText('"Gala" was approved.')).toBeInTheDocument()
})

it('TC-F09 says so when there are no notices', async () => {
  listMock.mockResolvedValue([])
  render(<NotificationsPage session={organiser} />)
  expect(await screen.findByText('No notifications yet')).toBeInTheDocument()
})

it('TC-F10 reports a failed load rather than an empty list', async () => {
  listMock.mockRejectedValue(new ApiError('boom', 'unknown', 500))
  render(<NotificationsPage session={organiser} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 500')
  expect(screen.queryByText('No notifications yet')).not.toBeInTheDocument()
})

it('TC-F11 keeps the notice in place when a toggle fails', async () => {
  listMock.mockResolvedValue([notice()])
  setReadMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<NotificationsPage session={organiser} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Mark as read' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not update that notification')
  expect(within(group('Unread')).getByText('"Gala" was approved.')).toBeInTheDocument()
})

it('TC-F12 links each notice to its event', async () => {
  listMock.mockResolvedValue([notice()])
  render(<NotificationsPage session={organiser} />)
  await userEvent.click(await screen.findByRole('link', { name: 'Open Gala' }))
  expect(window.location.hash).toBe('#/events/101')
})

// US10.2: the Coordinator's notices share the page and the read toggle.

const coordinator = buildSession({ role: 'Event Coordinator', id: '2' })

it('TC-CF01 labels each Coordinator notice by what needs attention', async () => {
  listMock.mockResolvedValue([
    notice({ id: '1', status: null, kind: 'assigned', message: 'You were assigned "Gala".' }),
    notice({ id: '2', status: null, kind: 'hold-expiring', message: 'Hold expires soon.' }),
    notice({ id: '3', status: null, kind: 'hold-expired', message: 'Hold expired.' }),
    notice({ id: '4', status: null, kind: 'booking-conflict', message: 'Booking hit.' }),
    notice({ id: '5', status: null, kind: 'safety-changes', message: 'Safety changes.' }),
    notice({ id: '6', status: null, kind: 'unassigned', message: 'No longer yours.' }),
  ])
  render(<NotificationsPage session={coordinator} />)
  for (const label of [
    'Assigned to you',
    'Hold expiring',
    'Hold expired',
    'Booking problem',
    'Safety changes',
    'Reassigned',
  ]) {
    expect(await screen.findByText(label)).toBeInTheDocument()
  }
  expect(screen.queryByText('Approved')).not.toBeInTheDocument()
})

it('TC-CF02 links a Coordinator notice to its event', async () => {
  listMock.mockResolvedValue([notice({ status: null, kind: 'booking-conflict' })])
  render(<NotificationsPage session={coordinator} />)
  await userEvent.click(await screen.findByRole('link', { name: 'Open Gala' }))
  expect(window.location.hash).toBe('#/events/101')
})

it('TC-CF03 has no link for an event that was reassigned away', async () => {
  listMock.mockResolvedValue([
    notice({ status: null, kind: 'unassigned', message: '"Gala" is no longer assigned to you.' }),
  ])
  render(<NotificationsPage session={coordinator} />)
  expect(await screen.findByText('"Gala" is no longer assigned to you.')).toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})

it('TC-CF04 marks a Coordinator notice read', async () => {
  const unread = notice({ status: null, kind: 'assigned' })
  listMock.mockResolvedValue([unread])
  setReadMock.mockResolvedValue({ ...unread, read: true, readAt: '2026-10-15T09:00:00' })
  render(<NotificationsPage session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Mark as read' }))
  expect(setReadMock).toHaveBeenCalledWith('1', true, coordinator)
  expect(within(group('Read')).getByText(unread.message)).toBeInTheDocument()
})

it('TC-CF05 tells a Coordinator what will show up here', async () => {
  listMock.mockResolvedValue([])
  render(<NotificationsPage session={coordinator} />)
  expect(await screen.findByText(/When an event is assigned to you/)).toBeInTheDocument()
  expect(screen.getByText(/Assignments and booking or safety problems/)).toBeInTheDocument()
})

it('TC-DF20 labels the booking decision notices', async () => {
  listMock.mockResolvedValue([
    notice({ id: '1', status: null, kind: 'booking-confirmed', message: 'Confirmed.' }),
    notice({ id: '2', status: null, kind: 'booking-rejected', message: 'Rejected.' }),
  ])
  render(<NotificationsPage session={coordinator} />)
  expect(await screen.findByText('Booking confirmed')).toBeInTheDocument()
  expect(screen.getByText('Booking rejected')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: 'Open Gala' })).toHaveLength(2)
})

it('labels the event-full notice and links to the event (US20.1)', async () => {
  listMock.mockResolvedValue([
    notice({
      id: '1',
      status: null,
      kind: 'event-full',
      message: '"Gala" is full: all 50 places are taken.',
    }),
  ])
  render(<NotificationsPage session={coordinator} />)
  expect(await screen.findByText('Event full')).toBeInTheDocument()
  expect(screen.getByText('"Gala" is full: all 50 places are taken.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open Gala' })).toBeInTheDocument()
})

/* ---------- US4.6: cancelled events ---------- */

const venueStaff = buildSession({ role: 'Venue Staff', id: '4' })

function cancellation(message: string): NotificationRecord {
  return notice({ status: 'Cancelled', eventTitle: 'Open House', message })
}

it('shows Venue Staff a released booking without a link to an event they cannot open', async () => {
  listMock.mockResolvedValue([
    cancellation('"Open House" was cancelled, so its booking was released: Great Hall.'),
  ])
  render(<NotificationsPage session={venueStaff} />)

  expect(await screen.findByText(/its booking was released: Great Hall/)).toBeInTheDocument()
  expect(screen.getByText('Cancelled')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Open/ })).not.toBeInTheDocument()
  expect(screen.getByText('Bookings released by cancelled events, unread first.')).toBeInTheDocument()
})

it('shows Tech Support released equipment without a link to the event', async () => {
  listMock.mockResolvedValue([
    cancellation('"Open House" was cancelled, so its equipment request was released.'),
  ])
  render(<NotificationsPage session={support} />)

  expect(await screen.findByText(/equipment request was released/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Open/ })).not.toBeInTheDocument()
})

it('still links the Organiser to their cancelled event', async () => {
  listMock.mockResolvedValue([cancellation('"Open House" was cancelled by Priya.')])
  render(<NotificationsPage session={organiser} />)

  expect(await screen.findByRole('link', { name: 'Open Open House' })).toHaveAttribute(
    'href',
    '#/events/101',
  )
})

it('tells Venue Staff what will show up here', async () => {
  listMock.mockResolvedValue([])
  render(<NotificationsPage session={venueStaff} />)

  expect(
    await screen.findByText('When a cancelled event gives back its venue bookings, it shows up here.'),
  ).toBeInTheDocument()
})

/* ---------- US4.6 with US20.1: registered Attendees ---------- */

const attendee = buildSession({ role: 'Attendee', id: '20' })

it('links an Attendee to My Registrations, since they cannot open the event', async () => {
  listMock.mockResolvedValue([
    cancellation('"Open House" has been cancelled, so your registration for it is cancelled too.'),
  ])
  render(<NotificationsPage session={attendee} />)

  expect(await screen.findByText(/your registration for it is cancelled too/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open My Registrations' })).toHaveAttribute(
    'href',
    '#/my-registrations',
  )
  expect(screen.queryByRole('link', { name: 'Open Open House' })).not.toBeInTheDocument()
  expect(
    screen.getByText('Events you registered for that have been cancelled, unread first.'),
  ).toBeInTheDocument()
})

it('tells an Attendee with no notices what will show up here', async () => {
  listMock.mockResolvedValue([])
  render(<NotificationsPage session={attendee} />)

  expect(
    await screen.findByText('If an event you registered for is cancelled, it shows up here.'),
  ).toBeInTheDocument()
})
