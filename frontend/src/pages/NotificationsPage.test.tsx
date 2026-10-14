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
