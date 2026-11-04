/**
 * US20.1 AC1 on the event page: the assigned Coordinator turns registration on
 * and sets the capacity. D3 (CODE_AUDIT.md): so does the owning Organiser, as
 * the Week 4 answers leave timing and closing to them. The rules are the
 * server's; these tests hold what the card offers and sends.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EventRegistration from './EventRegistration'
import type { EventRecord } from '../eventsStore'
import {
  getRegistrationSettings,
  listEventRegistrations,
  saveRegistrationSettings,
  type EventRegistrations,
  type RegistrationSettings,
} from '../registrationStore'
import { buildSession } from '../test/sessions'
import type { EventStatus } from '../status'

// Each mock has an implementation of its own, not only the beforeEach answers.
// The list of who registered mounts once the settings have loaded, so its
// effect can run after a test ends and this file's resetAllMocks has run, but
// before the card is unmounted. A reset keeps an implementation given to vi.fn;
// without one, the call would return undefined and fail whichever test was last.
vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  getRegistrationSettings: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    defaultCapacity: 30,
  })),
  saveRegistrationSettings: vi.fn(async () => ({
    eventId: '950',
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    defaultCapacity: 30,
  })),
  listEventRegistrations: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    registrations: [],
  })),
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

it('turns registration on with the capacity shown', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event()} session={coordinator} />)

  await user.click(await screen.findByRole('checkbox', { name: 'Open registration to Attendees' }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(saveMock).toHaveBeenCalledWith('950', { open: true, capacity: 30 }, coordinator)
  expect(screen.getByText('Registration is on: 0 of 30 places taken.')).toBeInTheDocument()
})

it('offers the owning Organiser the same switch (D3)', async () => {
  const user = userEvent.setup()
  saveMock.mockResolvedValue(settings({ open: true, capacity: 30, placesLeft: 30 }))
  render(<EventRegistration event={event()} session={organiser} />)

  await user.click(await screen.findByRole('checkbox', { name: 'Open registration to Attendees' }))
  await user.click(screen.getByRole('button', { name: 'Save registration' }))

  expect(saveMock).toHaveBeenCalledWith('950', { open: true, capacity: 30 }, organiser)
})

it('offers another Organiser no switch', async () => {
  render(
    <EventRegistration
      event={event('Planning', { organiserId: '77' })}
      session={organiser}
    />,
  )

  expect(await screen.findByText('Registration is off.')).toBeInTheDocument()
  expect(
    screen.queryByRole('checkbox', { name: 'Open registration to Attendees' }),
  ).not.toBeInTheDocument()
})
