/**
 * US20.1 for the Attendee: the Confirmed events taking registrations, and
 * registering for one. The rules are the server's; these tests hold what the
 * page shows, sends and says.
 */

import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AttendPage from './AttendPage'
import { formatBookingTimes } from '../eventsStore'
import { listOpenEvents, type OpenEvent } from '../registrationStore'
import { buildSession } from '../test/sessions'

vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  listOpenEvents: vi.fn(),
  registerForEvent: vi.fn(),
}))

const listMock = vi.mocked(listOpenEvents)


const attendee = buildSession({
  role: 'Attendee',
  id: '20',
  name: 'Casey Tan',
  email: 'casey@example.com',
})

function openEvent(overrides: Partial<OpenEvent> = {}): OpenEvent {
  return {
    id: '950',
    title: 'Open House',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    venues: ['Great Hall', 'Seminar Room 4'],
    placesLeft: 12,
    registered: false,
    ...overrides,
  }
}

function card(title = 'Open House'): HTMLElement {
  const heading = screen.getByRole('heading', { name: title })
  return heading.closest('li') as HTMLElement
}

beforeEach(() => {
  listMock.mockResolvedValue([openEvent()])
})

afterEach(() => {
  vi.resetAllMocks()
})

it('shows each open event with when, where and the places left', async () => {
  render(<AttendPage session={attendee} />)

  expect(await screen.findByRole('heading', { name: 'Open House' })).toBeInTheDocument()
  const item = card()
  expect(item).toHaveTextContent(formatBookingTimes('2099-11-02T09:00', '2099-11-02T17:00'))
  expect(item).toHaveTextContent('Great Hall, Seminar Room 4')
  expect(item).toHaveTextContent('12 places left')
  expect(listMock).toHaveBeenCalledWith(attendee)
})
