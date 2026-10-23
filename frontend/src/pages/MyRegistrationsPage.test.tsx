/**
 * US20.2 for the Attendee: their registrations, withdrawing, and registering
 * again. The rules are the server's; these tests hold what the page shows,
 * sends and says.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MyRegistrationsPage from './MyRegistrationsPage'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import {
  listMyRegistrations,
  registerForEvent,
  withdrawRegistration,
  type MyRegistration,
} from '../registrationStore'
import { formatRecordedAt } from '../status'
import { buildSession } from '../test/sessions'

vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  listMyRegistrations: vi.fn(),
  withdrawRegistration: vi.fn(),
  registerForEvent: vi.fn(),
}))

const listMock = vi.mocked(listMyRegistrations)
const withdrawMock = vi.mocked(withdrawRegistration)
const registerMock = vi.mocked(registerForEvent)

const attendee = buildSession({ role: 'Attendee', id: '20', name: 'Casey Tan' })

function registration(overrides: Partial<MyRegistration> = {}): MyRegistration {
  return {
    id: '5',
    eventId: '950',
    title: 'Open House',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    venues: ['Great Hall'],
    status: 'Registered',
    name: 'Casey Tan',
    email: 'casey@example.com',
    registeredAt: '2026-10-22T15:51:40',
    withdrawnAt: '',
    canWithdraw: true,
    canRegisterAgain: false,
    placesLeft: 11,
    ...overrides,
  }
}

const WITHDRAWN = registration({
  status: 'Withdrawn',
  withdrawnAt: '2026-10-23T01:00:00',
  canWithdraw: false,
  canRegisterAgain: true,
  placesLeft: 12,
})

function card(): HTMLElement {
  return screen.getByRole('heading', { name: 'Open House' }).closest('li') as HTMLElement
}

beforeEach(() => {
  listMock.mockResolvedValue([registration()])
})

afterEach(() => {
  vi.resetAllMocks()
})

it('shows each registration with its status and the event as it is now', async () => {
  render(<MyRegistrationsPage session={attendee} />)

  expect(await screen.findByRole('heading', { name: 'Open House' })).toBeInTheDocument()
  const item = card()
  expect(within(item).getByText('Registered', { selector: '.mine-status' })).toBeInTheDocument()
  expect(item).toHaveTextContent(formatBookingTimes('2099-11-02T09:00', '2099-11-02T17:00'))
  expect(item).toHaveTextContent('Great Hall')
  expect(item).toHaveTextContent('Casey Tan · casey@example.com')
  // Recorded in UTC, shown in Singapore time.
  expect(item).toHaveTextContent(formatRecordedAt('2026-10-22T15:51:40'))
  expect(item).toHaveTextContent('22 Oct 2026, 23:51')
  expect(listMock).toHaveBeenCalledWith(attendee)
})

it('shows a withdrawn registration as Withdrawn, with when', async () => {
  listMock.mockResolvedValue([WITHDRAWN])
  render(<MyRegistrationsPage session={attendee} />)

  await screen.findByRole('heading', { name: 'Open House' })
  expect(within(card()).getByText('Withdrawn', { selector: '.mine-status' })).toBeInTheDocument()
  expect(card()).toHaveTextContent('23 Oct 2026, 09:00')
})

it('says when there are none, and where to find events', async () => {
  listMock.mockResolvedValue([])
  render(<MyRegistrationsPage session={attendee} />)

  expect(
    await screen.findByText('You have not registered for any events yet'),
  ).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Upcoming Events' })).toHaveAttribute('href', '#/attend')
})

it('reports a list that will not load', async () => {
  listMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<MyRegistrationsPage session={attendee} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your registrations.')
})

it('asks before withdrawing, then withdraws and reads the list again', async () => {
  const user = userEvent.setup()
  withdrawMock.mockResolvedValue(WITHDRAWN)
  render(<MyRegistrationsPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Withdraw from Open House' }))
  expect(screen.getByText(/Your place goes back to the event/)).toBeInTheDocument()
  expect(withdrawMock).not.toHaveBeenCalled()

  listMock.mockResolvedValue([WITHDRAWN])
  await user.click(screen.getByRole('button', { name: 'Confirm withdrawal' }))

  expect(withdrawMock).toHaveBeenCalledWith('5', attendee)
  expect(
    await screen.findByText(
      'You have withdrawn from Open House. Your place has gone back to the event.',
    ),
  ).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Register again for Open House' })).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(2)
})

it('keeps the place when the Attendee changes their mind', async () => {
  const user = userEvent.setup()
  render(<MyRegistrationsPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Withdraw from Open House' }))
  await user.click(screen.getByRole('button', { name: 'Keep my place' }))

  expect(screen.queryByRole('button', { name: 'Confirm withdrawal' })).not.toBeInTheDocument()
  expect(withdrawMock).not.toHaveBeenCalled()
})

it('shows the server’s refusal on the registration it was about', async () => {
  const user = userEvent.setup()
  withdrawMock.mockRejectedValue(
    new EventRuleError('This event has already started, so you can no longer withdraw.'),
  )
  render(<MyRegistrationsPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Withdraw from Open House' }))
  listMock.mockResolvedValue([registration({ canWithdraw: false })])
  await user.click(screen.getByRole('button', { name: 'Confirm withdrawal' }))

  expect(await within(card()).findByRole('alert')).toHaveTextContent(
    'This event has already started, so you can no longer withdraw.',
  )
  expect(await screen.findByText('Withdrawing has closed for this event.')).toBeInTheDocument()
})

it('explains an unexpected failure to withdraw', async () => {
  const user = userEvent.setup()
  withdrawMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<MyRegistrationsPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Withdraw from Open House' }))
  await user.click(screen.getByRole('button', { name: 'Confirm withdrawal' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not withdraw from this event.',
  )
})

it('offers no withdrawal once it has closed', async () => {
  listMock.mockResolvedValue([registration({ canWithdraw: false })])
  render(<MyRegistrationsPage session={attendee} />)

  expect(await screen.findByText('Withdrawing has closed for this event.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Withdraw/ })).not.toBeInTheDocument()
})

it('registers again with the same name and email, and says so', async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValue([WITHDRAWN])
  registerMock.mockResolvedValue({
    id: '6',
    eventId: '950',
    name: 'Casey Tan',
    email: 'casey@example.com',
    status: 'Registered',
    createdAt: '2026-10-23T02:00:00',
  })
  render(<MyRegistrationsPage session={attendee} />)

  expect(await screen.findByText('12 places left')).toBeInTheDocument()
  listMock.mockResolvedValue([registration({ id: '6' })])
  await user.click(screen.getByRole('button', { name: 'Register again for Open House' }))

  expect(registerMock).toHaveBeenCalledWith(
    '950',
    { name: 'Casey Tan', email: 'casey@example.com' },
    attendee,
  )
  expect(await screen.findByText('You are registered again for Open House.')).toBeInTheDocument()
  await waitFor(() =>
    expect(within(card()).getByText('Registered', { selector: '.mine-status' })).toBeInTheDocument(),
  )
})

it('says the event is full when the place went to someone else first', async () => {
  const user = userEvent.setup()
  listMock.mockResolvedValue([WITHDRAWN])
  registerMock.mockRejectedValue(new EventRuleError('Event is full.'))
  render(<MyRegistrationsPage session={attendee} />)

  const again = await screen.findByRole('button', { name: 'Register again for Open House' })
  listMock.mockResolvedValue([{ ...WITHDRAWN, canRegisterAgain: false, placesLeft: 0 }])
  await user.click(again)

  expect(await screen.findByRole('alert')).toHaveTextContent('Event is full.')
  expect(await screen.findByText('No places are left to register again.')).toBeInTheDocument()
})

it('says why there is no way back when registration has closed', async () => {
  listMock.mockResolvedValue([{ ...WITHDRAWN, canRegisterAgain: false, placesLeft: null }])
  render(<MyRegistrationsPage session={attendee} />)

  expect(
    await screen.findByText('This event is no longer taking registrations.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Register again/ })).not.toBeInTheDocument()
})
