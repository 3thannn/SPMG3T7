/**
 * US20.1 AC1 on the event page: the assigned Coordinator turns registration on
 * and sets the capacity; everyone else who can open the event sees where it
 * stands. The rules are the server's; these tests hold what the card offers,
 * sends and says.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EventRegistration from './EventRegistration'
import { EventRuleError, type EventRecord } from '../eventsStore'
import {
  getRegistrationSettings,
  listEventRegistrations,
  saveRegistrationSettings,
  type EventRegistrations,
  type RegistrationSettings,
} from '../registrationStore'
import { buildSession } from '../test/sessions'
import type { EventStatus } from '../status'

vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  getRegistrationSettings: vi.fn(),
  saveRegistrationSettings: vi.fn(),
  listEventRegistrations: vi.fn(),
}))

const getMock = vi.mocked(getRegistrationSettings)
const saveMock = vi.mocked(saveRegistrationSettings)
const listMock = vi.mocked(listEventRegistrations)

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

function event(status: EventStatus = 'Planning', overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '950',
    title: 'Open House',
    purpose: 'Welcome visitors',
    description: 'Tours and talks.',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    expectedAttendance: 30,
    status,
    organiserId: '1',
    organiserName: 'Dylan',
    coordinatorId: '2',
    createdAt: '2099-01-01T09:00:00',
    updatedAt: '2099-01-01T09:00:00',
    history: [],
    ...overrides,
  }
}

function settings(overrides: Partial<RegistrationSettings> = {}): RegistrationSettings {
  return {
    eventId: '950',
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    defaultCapacity: 30,
    ...overrides,
  }
}

function people(overrides: Partial<EventRegistrations> = {}): EventRegistrations {
  return {
    eventId: '950',
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    registrations: [],
    ...overrides,
  }
}

beforeEach(() => {
  getMock.mockResolvedValue(settings())
  listMock.mockResolvedValue(people())
  saveMock.mockResolvedValue(settings())
})

afterEach(() => {
  vi.resetAllMocks()
})

it('offers the assigned Coordinator the switch, with the capacity starting at the attendance', async () => {
  render(<EventRegistration event={event()} session={coordinator} />)

  expect(await screen.findByText('Registration is off.')).toBeInTheDocument()
  expect(screen.getByRole('checkbox', { name: 'Open registration to Attendees' })).not.toBeChecked()
  expect(screen.getByLabelText('Capacity')).toHaveValue(30)
  expect(getMock).toHaveBeenCalledWith('950', coordinator)
})

it('turns registration on with the capacity shown', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  await user.click(await screen.findByRole('checkbox', { name: 'Open registration to Attendees' }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(saveMock).toHaveBeenCalledWith('950', { open: true, capacity: 30 }, coordinator)
  expect(await screen.findByText('Saved. Registration is on, for 30 places.')).toBeInTheDocument()
  expect(screen.getByText('Registration is on: 0 of 30 places taken.')).toBeInTheDocument()
})

it('sends a capacity the Coordinator typed', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 50, placesLeft: 50 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  const capacity = await screen.findByLabelText('Capacity')
  await user.clear(capacity)
  await user.type(capacity, '50')
  await user.click(screen.getByRole('checkbox', { name: 'Open registration to Attendees' }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(saveMock).toHaveBeenCalledWith('950', { open: true, capacity: 50 }, coordinator)
})

it('sends an emptied box as no capacity, for the server to default', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  await user.clear(await screen.findByLabelText('Capacity'))
  await user.click(screen.getByRole('checkbox', { name: 'Open registration to Attendees' }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(saveMock).toHaveBeenCalledWith('950', { open: true, capacity: null }, coordinator)
})

it('refuses a capacity of nobody before sending anything', async () => {
  const user = userEvent.setup()
  render(<EventRegistration event={event()} session={coordinator} />)

  const capacity = await screen.findByLabelText('Capacity')
  await user.clear(capacity)
  await user.type(capacity, '0')
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Give the capacity as a whole number of places, at least 1.',
  )
  expect(saveMock).not.toHaveBeenCalled()
})

it('shows the server’s refusal and keeps what was typed', async () => {
  const user = userEvent.setup()
  saveMock.mockRejectedValue(
    new EventRuleError('2 people have already registered, so the capacity cannot be less than 2.'),
  )
  render(<EventRegistration event={event()} session={coordinator} />)

  const capacity = await screen.findByLabelText('Capacity')
  await user.clear(capacity)
  await user.type(capacity, '1')
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    '2 people have already registered, so the capacity cannot be less than 2.',
  )
  expect(screen.getByLabelText('Capacity')).toHaveValue(1)
})

it('explains an unexpected failure to save', async () => {
  const user = userEvent.setup()
  saveMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<EventRegistration event={event()} session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Save registration' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not save the registration settings.',
  )
})

it('starts the box at the stored capacity once one is set', async () => {
  getMock.mockResolvedValue(settings({ open: false, capacity: 80, placesLeft: 80 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  expect(await screen.findByLabelText('Capacity')).toHaveValue(80)
})

it('shows the Organiser where it stands, with nothing to change', async () => {
  getMock.mockResolvedValue(settings({ open: true, capacity: 50, registered: 3, placesLeft: 47 }))
  render(<EventRegistration event={event('Confirmed')} session={organiser} />)

  expect(await screen.findByText('Registration is on: 3 of 50 places taken.')).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save registration' })).not.toBeInTheDocument()
})

it('offers no switch to a Coordinator the event is not assigned to', async () => {
  render(<EventRegistration event={event('Planning', { coordinatorId: '99' })} session={coordinator} />)

  await screen.findByText('Registration is off.')
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})

it('says when the event is full', async () => {
  getMock.mockResolvedValue(settings({ open: true, capacity: 2, registered: 2, placesLeft: 0 }))
  render(<EventRegistration event={event('Confirmed')} session={organiser} />)

  expect(
    await screen.findByText('Registration is on: 2 of 2 places taken. The event is full.'),
  ).toBeInTheDocument()
})

it('says Attendees see it only once it is Confirmed', async () => {
  getMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event('Planning')} session={coordinator} />)

  expect(
    await screen.findByText('Attendees will see this event once it is Confirmed.'),
  ).toBeInTheDocument()
})

it('tells the Coordinator it opens after approval, rather than offering it', async () => {
  render(<EventRegistration event={event('Submitted')} session={coordinator} />)

  expect(
    await screen.findByText('Registration can be opened once the event is approved.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})

it('offers nothing to change on a closed event', async () => {
  getMock.mockResolvedValue(settings({ open: true, capacity: 30, registered: 12, placesLeft: 18 }))
  render(<EventRegistration event={event('Completed')} session={coordinator} />)

  await screen.findByText('Registration is on: 12 of 30 places taken.')
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})

it('keeps count of the registrations made before it was turned off', async () => {
  getMock.mockResolvedValue(settings({ open: false, capacity: 30, registered: 2, placesLeft: 28 }))
  render(<EventRegistration event={event()} session={organiser} />)

  expect(
    await screen.findByText('Registration is off. 2 registered before it was turned off.'),
  ).toBeInTheDocument()
})

it('reports settings that will not load', async () => {
  getMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<EventRegistration event={event()} session={coordinator} />)

  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load the registration settings.'),
  )
})

/* ---------- US20.3: who registered ---------- */

const TWO_PEOPLE = people({
  open: true,
  capacity: 50,
  registered: 1,
  placesLeft: 49,
  registrations: [
    {
      id: '5',
      name: 'Casey Tan',
      email: 'casey@example.com',
      status: 'Registered',
      registeredAt: '2026-10-22T15:51:40',
      withdrawnAt: '',
    },
    {
      id: '6',
      name: 'Morgan Lee',
      email: 'morgan@example.com',
      status: 'Withdrawn',
      registeredAt: '2026-10-22T16:00:00',
      withdrawnAt: '2026-10-23T01:00:00',
    },
  ],
})

it('shows the assigned Coordinator who registered, with the count against the capacity', async () => {
  listMock.mockResolvedValue(TWO_PEOPLE)
  render(<EventRegistration event={event('Confirmed')} session={coordinator} />)

  const table = await screen.findByRole('table', { name: 'People registered for this event' })
  const rows = within(table).getAllByRole('row')
  expect(rows[0]).toHaveTextContent('NameEmailRegisteredStatus')
  // Recorded in UTC, shown in Singapore time.
  expect(rows[1]).toHaveTextContent('Casey Tancasey@example.com22 Oct 2026, 23:51Registered')
  expect(rows[2]).toHaveTextContent('Morgan Leemorgan@example.com23 Oct 2026, 00:00Withdrawn 23 Oct 2026, 09:00')
  expect(screen.getByText('1 of 50 registered')).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledWith('950', coordinator)
})

it('shows the owning Organiser the same list', async () => {
  listMock.mockResolvedValue(TWO_PEOPLE)
  render(<EventRegistration event={event('Confirmed')} session={organiser} />)

  expect(await screen.findByRole('heading', { name: 'Who has registered' })).toBeInTheDocument()
  expect(await screen.findByText('Casey Tan')).toBeInTheDocument()
})

it('says when nobody has registered, before a capacity is set', async () => {
  render(<EventRegistration event={event()} session={organiser} />)

  expect(await screen.findByText('Nobody has registered yet.')).toBeInTheDocument()
  expect(screen.getByText('0 registered')).toBeInTheDocument()
})

it('does not ask for the list for anyone else', async () => {
  const lead = buildSession({ role: 'Event Coordinator Lead', id: '3' })
  const otherOrganiser = buildSession({ role: 'Event Organiser', id: '44' })
  for (const session of [lead, otherOrganiser]) {
    const { unmount } = render(<EventRegistration event={event('Confirmed')} session={session} />)
    await screen.findByText('Registration is off.')
    expect(screen.queryByRole('heading', { name: 'Who has registered' })).not.toBeInTheDocument()
    unmount()
  }
  render(
    <EventRegistration event={event('Confirmed', { coordinatorId: '99' })} session={coordinator} />,
  )
  await screen.findByText('Registration is off.')
  expect(screen.queryByRole('heading', { name: 'Who has registered' })).not.toBeInTheDocument()
  expect(listMock).not.toHaveBeenCalled()
})

it('reports a list that will not load', async () => {
  listMock.mockRejectedValue(new TypeError('Failed to fetch'))
  render(<EventRegistration event={event()} session={organiser} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load who has registered.')
})

it('reads the list again after the Coordinator saves', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  await screen.findByText('Nobody has registered yet.')
  listMock.mockResolvedValue(people({ open: true, capacity: 30, placesLeft: 30 }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(await screen.findByText('0 of 30 registered')).toBeInTheDocument()
  expect(listMock).toHaveBeenCalledTimes(2)
})
