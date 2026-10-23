/**
 * US20.1 for the Attendee: the Confirmed events taking registrations, and
 * registering for one. The rules are the server's; these tests hold what the
 * page shows, sends and says.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AttendPage from './AttendPage'
import { EventRuleError, formatBookingTimes } from '../eventsStore'
import { listOpenEvents, registerForEvent, type OpenEvent } from '../registrationStore'
import { buildSession } from '../test/sessions'

vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  listOpenEvents: vi.fn(),
  registerForEvent: vi.fn(),
}))

const listMock = vi.mocked(listOpenEvents)
const registerMock = vi.mocked(registerForEvent)

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

it('says the venue is to be announced when none is confirmed', async () => {
  listMock.mockResolvedValue([openEvent({ venues: [] })])
  render(<AttendPage session={attendee} />)

  expect(await screen.findByText('Venue to be announced')).toBeInTheDocument()
})

it('says one place in the singular', async () => {
  listMock.mockResolvedValue([openEvent({ placesLeft: 1 })])
  render(<AttendPage session={attendee} />)

  expect(await screen.findByText('1 place left')).toBeInTheDocument()
})

it('says when nothing is open', async () => {
  listMock.mockResolvedValue([])
  render(<AttendPage session={attendee} />)

  expect(await screen.findByText('No events are open for registration')).toBeInTheDocument()
})

it('reports a list that will not load', async () => {
  listMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<AttendPage session={attendee} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not load the events open for registration.',
  )
})

it('starts the form with the account’s own name and email', async () => {
  const user = userEvent.setup()
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))

  expect(screen.getByLabelText('Name')).toHaveValue('Casey Tan')
  expect(screen.getByLabelText('Email')).toHaveValue('casey@example.com')
})

it('registers, says so, and reads the list again', async () => {
  const user = userEvent.setup()
  registerMock.mockResolvedValue({
    id: '5',
    eventId: '950',
    name: 'Casey T',
    email: 'casey.t@example.com',
    status: 'Registered',
    createdAt: '2026-10-23T06:00:00',
  })
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  await user.clear(screen.getByLabelText('Name'))
  await user.type(screen.getByLabelText('Name'), 'Casey T')
  await user.clear(screen.getByLabelText('Email'))
  await user.type(screen.getByLabelText('Email'), 'casey.t@example.com')
  listMock.mockResolvedValue([openEvent({ placesLeft: 11, registered: true })])
  await user.click(screen.getByRole('button', { name: 'Confirm registration' }))

  expect(registerMock).toHaveBeenCalledWith(
    '950',
    { name: 'Casey T', email: 'casey.t@example.com' },
    attendee,
  )
  expect(await screen.findByText('You are registered for Open House.')).toBeInTheDocument()
  expect(await screen.findByText(/^You are registered for this event\./)).toBeInTheDocument()
  expect(screen.getByText('11 places left')).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(2)
})

it('asks for a name before sending anything', async () => {
  const user = userEvent.setup()
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  await user.clear(screen.getByLabelText('Name'))
  await user.click(screen.getByRole('button', { name: 'Confirm registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give your name.')
  expect(registerMock).not.toHaveBeenCalled()
})

it('refuses an email that cannot be one before sending anything', async () => {
  const user = userEvent.setup()
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  await user.clear(screen.getByLabelText('Email'))
  await user.type(screen.getByLabelText('Email'), 'casey@example')
  await user.click(screen.getByRole('button', { name: 'Confirm registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Give a valid email address, such as name@example.com.',
  )
  expect(registerMock).not.toHaveBeenCalled()
})

it('says the event is full when the last place went first, and shows the places now', async () => {
  const user = userEvent.setup()
  registerMock.mockRejectedValue(new EventRuleError('Event is full.'))
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  listMock.mockResolvedValue([openEvent({ placesLeft: 0 })])
  await user.click(screen.getByRole('button', { name: 'Confirm registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Event is full.')
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
  expect(within(card()).getAllByText('Event is full.').length).toBeGreaterThan(0)
})

it('explains an unexpected failure to register', async () => {
  const user = userEvent.setup()
  registerMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  await user.click(screen.getByRole('button', { name: 'Confirm registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not register for this event.')
})

it('offers no second place once registered', async () => {
  listMock.mockResolvedValue([openEvent({ registered: true })])
  render(<AttendPage session={attendee} />)

  expect(await screen.findByText(/^You are registered for this event\./)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Register for/ })).not.toBeInTheDocument()
  // US20.2: withdrawing is done from My Registrations.
  expect(screen.getByRole('link', { name: 'My Registrations' })).toHaveAttribute(
    'href',
    '#/my-registrations',
  )
})

it('offers no Register button on a full event', async () => {
  listMock.mockResolvedValue([openEvent({ placesLeft: 0 })])
  render(<AttendPage session={attendee} />)

  expect(await screen.findByText('Event is full.')).toBeInTheDocument()
  expect(screen.getByText('No places are left.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Register for/ })).not.toBeInTheDocument()
})

it('closes the form without registering', async () => {
  const user = userEvent.setup()
  render(<AttendPage session={attendee} />)

  await user.click(await screen.findByRole('button', { name: 'Register for Open House' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Register for Open House' })).toBeInTheDocument()
  expect(registerMock).not.toHaveBeenCalled()
})
