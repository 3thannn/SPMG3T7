/**
 * US10.1: the notifications client. What it sends and how it reads the reply;
 * which transitions notify, and the ordering, are tested in
 * backend/tests/test_notifications.py.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  NOTIFICATIONS_CHANGED,
  listNotifications,
  setNotificationRead,
  unreadCount,
  type NotificationRecord,
} from './notificationsStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const session = buildSession({ token: 'session-token', id: '1' })

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

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('listNotifications', () => {
  it('TC-F01 reads the list with the session token', async () => {
    const fetchMock = stubFetch([notice()])
    const listed = await listNotifications(session)
    expect(listed).toEqual([notice()])
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/notifications$/)
    expect(init.headers.Authorization).toBe('Bearer session-token')
  })

  it('TC-F02 surfaces a refusal as an ApiError', async () => {
    stubFetch({ detail: { code: 'forbidden', message: 'No.' } }, 403)
    await expect(listNotifications(session)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('setNotificationRead', () => {
  it('TC-F03 sends the new read state and announces the change', async () => {
    const fetchMock = stubFetch(notice({ read: true, readAt: '2026-10-02T10:00:00' }))
    const announced = vi.fn()
    window.addEventListener(NOTIFICATIONS_CHANGED, announced)

    const updated = await setNotificationRead('1', true, session)

    window.removeEventListener(NOTIFICATIONS_CHANGED, announced)
    expect(updated.read).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/notifications\/1$/)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ read: true })
    expect(announced).toHaveBeenCalledOnce()
  })
})

describe('unreadCount', () => {
  it('TC-F04 counts only unread notices', () => {
    expect(unreadCount([notice(), notice({ id: '2', read: true }), notice({ id: '3' })])).toBe(2)
    expect(unreadCount([])).toBe(0)
  })
})
