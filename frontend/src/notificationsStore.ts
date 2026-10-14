/**
 * Notification data access — US10.1 and US19.
 *
 * The server writes Organiser status notices and Tech Support equipment request
 * notices. This module reads each recipient's list and flips read state.
 */

import { authorizedFetch, type Session } from './api'
import type { EventStatus } from './status'

export type NotificationRecord = {
  id: string
  eventId: string
  eventTitle: string
  /** The status the event moved to when the notice was written. */
  status: EventStatus | null
  kind?: 'event-status' | 'equipment-request'
  equipmentRequestId?: string | null
  message: string
  read: boolean
  createdAt: string
  /** Empty while unread. */
  readAt: string
}

/**
 * Fired on `window` whenever read state changes, so the nav's unread count
 * follows the page without the two sharing state.
 */
export const NOTIFICATIONS_CHANGED = 'notifications:changed'

export async function listNotifications(session: Session): Promise<NotificationRecord[]> {
  const response = await authorizedFetch('/notifications', session.token)
  return (await response.json()) as NotificationRecord[]
}

export async function setNotificationRead(
  id: string,
  read: boolean,
  session: Session,
): Promise<NotificationRecord> {
  const response = await authorizedFetch(`/notifications/${id}`, session.token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ read }),
  })
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
  return (await response.json()) as NotificationRecord
}

export function unreadCount(notifications: readonly NotificationRecord[]): number {
  return notifications.filter((notification) => !notification.read).length
}
