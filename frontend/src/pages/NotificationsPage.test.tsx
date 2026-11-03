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

it('TC-F07 marks a notice read and moves it to the read group', async () => {
  listMock.mockResolvedValue([notice()])
  setReadMock.mockResolvedValue(notice({ read: true, readAt: '2026-10-02T10:00:00' }))
  render(<NotificationsPage session={organiser} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Mark as read' }))

  expect(setReadMock).toHaveBeenCalledWith('1', true, organiser)
  expect(within(group('Read')).getByText('"Gala" was approved.')).toBeInTheDocument()
  expect(within(group('Unread')).getByText('You are all caught up.')).toBeInTheDocument()
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

/* ---------- US4.6 with US20.1: registered Attendees ---------- */

const attendee = buildSession({ role: 'Attendee', id: '20' })

it('US10.4 labels an Attendee notice of a new date, time or venue', async () => {
  listMock.mockResolvedValue([
    notice({
      id: '1',
      status: null,
      kind: 'event-updated',
      message: '"Open House" has a new venue: Bertha Room, Library, Level 3.',
    }),
  ])
  render(<NotificationsPage session={attendee} />)

  expect(await screen.findByText('Event updated')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open My Registrations' })).toBeInTheDocument()
})

it('US10.3 tells a Lead what their notices are about', async () => {
  listMock.mockResolvedValue([])
  render(<NotificationsPage session={buildSession({ role: 'Event Coordinator Lead' })} />)

  expect(
    await screen.findByText('When an event is submitted for assignment, it shows up here.'),
  ).toBeInTheDocument()
})
