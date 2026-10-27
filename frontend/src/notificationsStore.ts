/**
 * Notification data access — US10.1, US10.2 and US19.
 *
 * The server writes Organiser status notices, Coordinator notices about events
 * needing their attention, and Tech Support equipment request notices. This
 * module reads each recipient's list and flips read state.
 */

import { authorizedFetch, type Session } from './api'
import type { EventStatus } from './status'

/** US10.2: what a Coordinator is told about, one kind per acceptance criterion. */
export type CoordinatorNoticeKind =
  | 'assigned'
  | 'unassigned'
  | 'hold-expiring'
  | 'hold-expired'
  | 'booking-conflict'
  | 'safety-changes'
  /** US17.2: the Safety Officer rejected the safety check. */
  | 'safety-rejected'
  | 'booking-confirmed'
  | 'booking-rejected'
  /** US20.1: registrations reached capacity. The Organiser is told too. */
  | 'event-full'

export type NotificationKind = 'event-status' | 'equipment-request' | CoordinatorNoticeKind

/** The label each non-status notice shows in place of a status badge. */
export const KIND_LABELS: Record<Exclude<NotificationKind, 'event-status'>, string> = {
  'equipment-request': 'Equipment request',
  assigned: 'Assigned to you',
  unassigned: 'Reassigned',
  'hold-expiring': 'Hold expiring',
  'hold-expired': 'Hold expired',
  'booking-conflict': 'Booking problem',
  'safety-changes': 'Safety changes',
  'safety-rejected': 'Safety check rejected',
  'booking-confirmed': 'Booking confirmed',
  'booking-rejected': 'Booking rejected',
  'event-full': 'Event full',
}

export type NotificationRecord = {
  id: string
  eventId: string
  eventTitle: string
  /** The status the event moved to when the notice was written. */
  status: EventStatus | null
  kind?: NotificationKind
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
