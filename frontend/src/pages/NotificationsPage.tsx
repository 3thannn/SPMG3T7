import { useEffect, useState } from 'react'
import './NotificationsPage.css'
import StatusBadge from '../components/StatusBadge'
import {
  KIND_LABELS,
  listNotifications,
  setNotificationRead,
  type NotificationRecord,
} from '../notificationsStore'
import { displayEventTitle } from '../draftRules'
import { navigate } from '../router'
import { formatTimestamp } from '../status'
import { unexpectedFailureMessage, type Session } from '../api'

type NotificationsPageProps = {
  session: Session
}

/**
 * Organiser status notices, Coordinator attention notices (US10.2) and Tech
 * Support equipment request notices.
 *
 * Unread notices come first so the list reads from the top, and each can be
 * marked read or unread so it never becomes a pile nobody can work through.
 * The server already orders the list; the page splits it into the two groups
 * and keeps a toggled notice in place until the next load, so a click does not
 * make the row jump out from under the pointer.
 */
const SUBTITLES: Partial<Record<Session['role'], string>> = {
  'Technical Support': 'New equipment requests, unread first.',
  'Event Coordinator': 'Assignments and booking or safety problems on your events, unread first.',
}

const EMPTY_TEXT: Partial<Record<Session['role'], string>> = {
  'Technical Support': 'New equipment requests will appear here.',
  'Event Coordinator':
    'When an event is assigned to you, or one of yours has a hold, booking or safety problem, it shows up here.',
}

/** Where a notice leads, or null when there is nothing the reader can open. */
function target(item: NotificationRecord): { path: string; label: string } | null {
  if (item.kind === 'equipment-request') {
    return { path: `/equipment-requests/${item.equipmentRequestId ?? 'missing'}`, label: 'Open request' }
  }
  // US10.2: the event was taken off this Coordinator, so they can no longer open it.
  if (item.kind === 'unassigned') return null
  return { path: `/events/${item.eventId}`, label: `Open ${displayEventTitle(item.eventTitle)}` }
}

export default function NotificationsPage({ session }: NotificationsPageProps) {
  const [notifications, setNotifications] = useState<NotificationRecord[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [pending, setPending] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listNotifications(session)
      .then((loaded) => {
        if (!cancelled) setNotifications(loaded)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setNotifications([])
        setLoadError(unexpectedFailureMessage(error, 'load your notifications'))
      })
    return () => {
      cancelled = true
    }
  }, [session, session.token])

  async function toggle(notification: NotificationRecord) {
    setPending(notification.id)
    setActionError('')
    try {
      const updated = await setNotificationRead(notification.id, !notification.read, session)
      setNotifications((current) =>
        (current ?? []).map((item) => (item.id === updated.id ? updated : item)),
      )
    } catch (error) {
      setActionError(unexpectedFailureMessage(error, 'update that notification'))
    } finally {
      setPending(null)
    }
  }

  const unread = (notifications ?? []).filter((item) => !item.read)
  const read = (notifications ?? []).filter((item) => item.read)

  return (
    <div className="page">
      <div className="shell">
        <header className="page-head">
          <div>
            <h1 className="page-title">Notifications</h1>
            <p className="page-subtitle">
              {SUBTITLES[session.role] ?? 'Status changes on your events, unread first.'}
            </p>
          </div>
        </header>

        {(loadError || actionError) && (
          <p className="form-error" role="alert">
            {loadError || actionError}
          </p>
        )}

        {notifications === null ? (
          <p className="muted">Loading notifications…</p>
        ) : loadError ? null : notifications.length === 0 ? (
          <div className="card empty">
            <h3>No notifications yet</h3>
            <p>
              {EMPTY_TEXT[session.role] ??
                'When a Coordinator reviews, approves or rejects one of your events, it shows up here.'}
            </p>
          </div>
        ) : (
          <>
            {renderGroup('Unread', unread, 'You are all caught up.')}
            {renderGroup('Read', read, 'Nothing marked read yet.')}
          </>
        )}
      </div>
    </div>
  )

  function renderGroup(label: string, items: NotificationRecord[], empty: string) {
    const headingId = `notifications-${label.toLowerCase()}`
    return (
      <section className="notification-group" aria-labelledby={headingId}>
        <h2 className="notification-group-title" id={headingId}>
          {label} <span className="notification-count">{items.length}</span>
        </h2>
        {items.length === 0 ? (
          <p className="muted">{empty}</p>
        ) : (
          <ul className="notification-list">
            {items.map((item) => {
              const link = target(item)
              return (
              <li
                key={item.id}
                className={`notification-row card${item.read ? '' : ' is-unread'}`}
              >
                <div className="notification-main">
                  <div className="notification-meta">
                    {item.status && <StatusBadge status={item.status} />}
                    {item.kind && item.kind !== 'event-status' && (
                      <span>{KIND_LABELS[item.kind]}</span>
                    )}
                    <span>{formatTimestamp(item.createdAt)}</span>
                  </div>
                  <p className="notification-message">{item.message}</p>
                  {link && (
                    <a
                      className="notification-event"
                      href={`#${link.path}`}
                      onClick={(clickEvent) => {
                        clickEvent.preventDefault()
                        navigate(link.path)
                      }}
                    >
                      {link.label}
                    </a>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === item.id}
                  onClick={() => void toggle(item)}
                >
                  {item.read ? 'Mark as unread' : 'Mark as read'}
                </button>
              </li>
              )
            })}
          </ul>
        )}
      </section>
    )
  }
}
