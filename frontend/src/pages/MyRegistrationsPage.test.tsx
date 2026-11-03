/**
 * US20.2 for the Attendee: their registrations, withdrawing, and registering
 * again. The rules are the server's; these tests hold what the page shows,
 * sends and says.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MyRegistrationsPage from './MyRegistrationsPage'
import {
  listMyRegistrations,
  withdrawRegistration,
  type MyRegistration,
} from '../registrationStore'
import { buildSession } from '../test/sessions'

vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  listMyRegistrations: vi.fn(),
  withdrawRegistration: vi.fn(),
  registerForEvent: vi.fn(),
}))

const listMock = vi.mocked(listMyRegistrations)
const withdrawMock = vi.mocked(withdrawRegistration)

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

beforeEach(() => {
  listMock.mockResolvedValue([registration()])
})

afterEach(() => {
  vi.resetAllMocks()
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
