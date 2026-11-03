/** US10.1: the Notifications link and its unread count on the rail. */

import { render, screen, waitFor, within } from '@testing-library/react'
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

// US4.6 gave Venue Staff notifications, for bookings a cancellation releases,
// and US10.3 the Lead, for new submissions.
it('TC-F16 offers no Notifications link to a Safety Officer', () => {
  render(
    <TopNav
      route="/events"
      session={buildSession({ role: 'Safety Officer' })}
      onSignOut={() => {}}
    />,
  )
  expect(screen.queryByRole('link', { name: /Notifications/ })).not.toBeInTheDocument()
  expect(listMock).not.toHaveBeenCalled()
})

it('US10.3 gives a Lead the Notifications link and unread count', async () => {
  listMock.mockResolvedValue([{ ...notice('1', false), status: 'Submitted' }])
  render(
    <TopNav
      route="/unassigned-queue"
      session={buildSession({ role: 'Event Coordinator Lead' })}
      onSignOut={() => {}}
    />,
  )
  expect(await screen.findByLabelText('1 unread')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Notifications/ })).toBeInTheDocument()
})

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

// -- A rail with more pages than room scrolls sideways (the Lead has six) -------

function leadRail(width: { scroll: number; client: number }) {
  listMock.mockResolvedValue([])
  render(
    <TopNav
      route="/notifications"
      session={buildSession({ role: 'Event Coordinator Lead' })}
      onSignOut={() => {}}
    />,
  )
  const rail = screen.getByRole('navigation', { name: 'Main' })
  Object.defineProperty(rail, 'scrollWidth', { configurable: true, value: width.scroll })
  Object.defineProperty(rail, 'clientWidth', { configurable: true, value: width.client })
  return rail
}

function wheel(rail: HTMLElement, deltaX: number, deltaY: number) {
  const event = new WheelEvent('wheel', { deltaX, deltaY, cancelable: true, bubbles: true })
  act(() => {
    rail.dispatchEvent(event)
  })
  return event
}

it('turns a mouse wheel into sideways scrolling when the links do not fit', () => {
  const rail = leadRail({ scroll: 900, client: 600 })

  const event = wheel(rail, 0, 120)

  expect(rail.scrollLeft).toBe(120)
  expect(event.defaultPrevented).toBe(true)
})

it('leaves the wheel alone when every link fits', () => {
  const rail = leadRail({ scroll: 600, client: 600 })

  const event = wheel(rail, 0, 120)

  expect(rail.scrollLeft).toBe(0)
  expect(event.defaultPrevented).toBe(false)
})

it('leaves a sideways trackpad swipe to the browser', () => {
  const rail = leadRail({ scroll: 900, client: 600 })

  const event = wheel(rail, 80, 10)

  expect(event.defaultPrevented).toBe(false)
})

it('scrolls the page you are on into view', () => {
  const scrollIntoView = vi.fn()
  Element.prototype.scrollIntoView = scrollIntoView
  try {
    leadRail({ scroll: 900, client: 600 })

    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' })
    expect(scrollIntoView.mock.contexts[0]).toHaveTextContent('Notifications')
  } finally {
    // jsdom has no scrollIntoView; put it back as it was.
    delete (Element.prototype as Partial<Element>).scrollIntoView
  }
})

function pointer(type: string, target: EventTarget, clientX: number, pointerType = 'mouse') {
  // jsdom has no PointerEvent; a MouseEvent with a pointerType reads the same here.
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX, button: 0 })
  Object.defineProperty(event, 'pointerType', { value: pointerType })
  act(() => {
    target.dispatchEvent(event)
  })
}

function clickLink(rail: HTMLElement, name: string) {
  const link = within(rail).getByRole('link', { name: new RegExp(name) })
  const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
  act(() => {
    link.dispatchEvent(event)
  })
}

it('drags the rail sideways with the mouse, and the drag does not open a link', () => {
  window.location.hash = '#/notifications'
  const rail = leadRail({ scroll: 900, client: 600 })

  pointer('pointerdown', rail, 300)
  pointer('pointermove', window, 200)
  expect(rail.scrollLeft).toBe(100)
  expect(rail).toHaveClass('is-dragging')
  pointer('pointerup', window, 200)
  clickLink(rail, 'Venues')

  expect(rail).not.toHaveClass('is-dragging')
  expect(window.location.hash).toBe('#/notifications')
})

it('treats a press that barely moves as a click', () => {
  window.location.hash = '#/notifications'
  const rail = leadRail({ scroll: 900, client: 600 })

  pointer('pointerdown', rail, 300)
  pointer('pointermove', window, 302)
  pointer('pointerup', window, 302)
  clickLink(rail, 'Venues')

  expect(rail.scrollLeft).toBe(0)
  expect(window.location.hash).toBe('#/venues')
})

it.each([
  ['a touch, which already swipes', { scroll: 900, client: 600 }, 'touch'],
  ['a rail where every link fits', { scroll: 600, client: 600 }, 'mouse'],
])('does not drag %s', (_case, width, pointerType) => {
  const rail = leadRail(width)

  pointer('pointerdown', rail, 300, pointerType)
  pointer('pointermove', window, 100, pointerType)

  expect(rail.scrollLeft).toBe(0)
})

it('fades the edges that hide links', () => {
  const rail = leadRail({ scroll: 900, client: 600 })
  act(() => {
    window.dispatchEvent(new Event('resize'))
  })
  expect(rail.dataset).toMatchObject({ fadeStart: 'false', fadeEnd: 'true' })

  rail.scrollLeft = 100
  act(() => {
    rail.dispatchEvent(new Event('scroll'))
  })
  expect(rail.dataset).toMatchObject({ fadeStart: 'true', fadeEnd: 'true' })

  rail.scrollLeft = 300
  act(() => {
    rail.dispatchEvent(new Event('scroll'))
  })
  expect(rail.dataset).toMatchObject({ fadeStart: 'true', fadeEnd: 'false' })
})
