/** US10.1: the Notifications link and its unread count on the rail. */

import { render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import TopNav from './TopNav'
import {
  NOTIFICATIONS_CHANGED,
  listNotifications,
  type NotificationRecord,
} from '../notificationsStore'
import { buildSession } from '../test/sessions'

vi.mock('../notificationsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../notificationsStore')>()),
  listNotifications: vi.fn(),
}))

const listMock = vi.mocked(listNotifications)

afterEach(() => {
  vi.resetAllMocks()
})

function notice(id: string, read: boolean): NotificationRecord {
  return {
    id,
    eventId: '101',
    eventTitle: 'Gala',
    status: 'Approved',
    message: 'm',
    read,
    createdAt: '2026-10-02T09:00:00',
    readAt: '',
  }
}

it('TC-F13 shows the unread count on the Notifications link', async () => {
  listMock.mockResolvedValue([notice('1', false), notice('2', false), notice('3', true)])
  render(<TopNav route="/events" session={buildSession()} onSignOut={() => {}} />)
  expect(await screen.findByLabelText('2 unread')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Notifications/ })).toBeInTheDocument()
})

it('TC-F14 shows no count when everything is read', async () => {
  listMock.mockResolvedValue([notice('1', true)])
  render(<TopNav route="/events" session={buildSession()} onSignOut={() => {}} />)
  await waitFor(() => expect(listMock).toHaveBeenCalled())
  expect(screen.queryByLabelText(/unread/)).not.toBeInTheDocument()
})

it('TC-F15 re-reads the count when read state changes', async () => {
  listMock.mockResolvedValueOnce([notice('1', false)]).mockResolvedValueOnce([notice('1', true)])
  render(<TopNav route="/events" session={buildSession()} onSignOut={() => {}} />)
  expect(await screen.findByLabelText('1 unread')).toBeInTheDocument()

  act(() => {
    window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
  })
  await waitFor(() => expect(screen.queryByLabelText(/unread/)).not.toBeInTheDocument())
})

it.each(['Event Coordinator Lead', 'Venue Staff'] as const)(
  'TC-F16 offers no Notifications link to %s',
  (role) => {
    render(<TopNav route="/events" session={buildSession({ role })} onSignOut={() => {}} />)
    expect(screen.queryByRole('link', { name: /Notifications/ })).not.toBeInTheDocument()
    expect(listMock).not.toHaveBeenCalled()
  },
)

it('TC-CF06 gives a Coordinator the Notifications link and unread count', async () => {
  listMock.mockResolvedValue([{ ...notice('1', false), status: null, kind: 'assigned' }])
  render(
    <TopNav
      route="/events"
      session={buildSession({ role: 'Event Coordinator' })}
      onSignOut={() => {}}
    />,
  )
  expect(await screen.findByLabelText('1 unread')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Notifications/ })).toBeInTheDocument()
})

it('TC-DF19 offers Venue Staff the Booking Requests link and a Coordinator none', () => {
  listMock.mockResolvedValue([])
  const { unmount } = render(
    <TopNav route="/venues" session={buildSession({ role: 'Venue Staff' })} onSignOut={() => {}} />,
  )
  expect(screen.getByRole('link', { name: 'Booking Requests' })).toBeInTheDocument()
  unmount()

  render(
    <TopNav
      route="/events"
      session={buildSession({ role: 'Event Coordinator' })}
      onSignOut={() => {}}
    />,
  )
  expect(screen.queryByRole('link', { name: 'Booking Requests' })).not.toBeInTheDocument()
})

it('TC-FF22 offers Venue Staff the Booking Conflicts link and a Coordinator none', () => {
  listMock.mockResolvedValue([])
  const { unmount } = render(
    <TopNav route="/venues" session={buildSession({ role: 'Venue Staff' })} onSignOut={() => {}} />,
  )
  expect(screen.getByRole('link', { name: 'Booking Conflicts' })).toHaveAttribute(
    'href',
    '#/booking-conflicts',
  )
  unmount()

  render(
    <TopNav
      route="/events"
      session={buildSession({ role: 'Event Coordinator' })}
      onSignOut={() => {}}
    />,
  )
  expect(screen.queryByRole('link', { name: 'Booking Conflicts' })).not.toBeInTheDocument()
})
