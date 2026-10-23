/**
 * The registration store is a client for US20.1's routes.
 *
 * These tests assert what it sends and how it reads what comes back. The rules
 * themselves — who may open registration, one place per Attendee, never more
 * than the capacity — are the server's, tested in
 * backend/tests/test_registration_us20_1.py.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  EVENT_FULL_MESSAGE,
  describePlacesLeft,
  getRegistrationSettings,
  listMyRegistrations,
  listOpenEvents,
  parseCapacity,
  registerForEvent,
  saveRegistrationSettings,
  validateRegistration,
  withdrawRegistration,
} from './registrationStore'
import { EventRuleError } from './eventsStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const coordinator = buildSession({ role: 'Event Coordinator', token: 'coordinator-token' })
const attendee = buildSession({ role: 'Attendee', token: 'attendee-token' })

const SETTINGS = {
  eventId: '950',
  open: true,
  capacity: 50,
  registered: 3,
  placesLeft: 47,
  defaultCapacity: 30,
}

const OPEN_EVENT = {
  id: '950',
  title: 'Open House',
  startsAt: '2099-11-02T09:00',
  endsAt: '2099-11-02T17:00',
  venues: ['Great Hall'],
  placesLeft: 12,
  registered: false,
}

function ok(body: unknown, status = 200) {
  return { ok: true, status, json: async () => body }
}

function failure(status: number, code: string, message: string) {
  return { ok: false, status, json: async () => ({ detail: { code, message } }) }
}

function stubFetch(response: unknown) {
  const spy = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', spy)
  return spy
}

describe('the Coordinator’s settings', () => {
  it('reads the settings with the session’s token', async () => {
    const spy = stubFetch(ok(SETTINGS))

    expect(await getRegistrationSettings('950', coordinator)).toEqual(SETTINGS)
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/events/950/registration')
    expect(spy.mock.calls[0][1].headers.Authorization).toBe('Bearer coordinator-token')
  })

  it('puts whether it is on and the capacity', async () => {
    const spy = stubFetch(ok(SETTINGS))

    await saveRegistrationSettings('950', { open: true, capacity: 50 }, coordinator)

    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/events/950/registration')
    expect(spy.mock.calls[0][1].method).toBe('PUT')
    expect(JSON.parse(spy.mock.calls[0][1].body)).toEqual({ open: true, capacity: 50 })
  })

  it('sends no capacity as null, for the server to keep or default', async () => {
    const spy = stubFetch(ok(SETTINGS))

    await saveRegistrationSettings('950', { open: false, capacity: null }, coordinator)

    expect(JSON.parse(spy.mock.calls[0][1].body)).toEqual({ open: false, capacity: null })
  })

  it('turns refusals into rule errors and lets a lapsed session through', async () => {
    stubFetch(
      failure(
        409,
        'rule_refused',
        '2 people have already registered, so the capacity cannot be less than 2.',
      ),
    )
    await expect(
      saveRegistrationSettings('950', { open: true, capacity: 1 }, coordinator),
    ).rejects.toThrow(
      new EventRuleError('2 people have already registered, so the capacity cannot be less than 2.'),
    )

    stubFetch(failure(401, 'session_expired', 'Sign in again.'))
    await expect(
      saveRegistrationSettings('950', { open: true, capacity: 1 }, coordinator),
    ).rejects.not.toBeInstanceOf(EventRuleError)
  })
})

describe('the Attendee’s events', () => {
  it('lists the open events with the session’s token', async () => {
    const spy = stubFetch(ok([OPEN_EVENT]))

    expect(await listOpenEvents(attendee)).toEqual([OPEN_EVENT])
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/attendee/events')
    expect(spy.mock.calls[0][1].headers.Authorization).toBe('Bearer attendee-token')
  })

  it('registers with the name and email, trimmed', async () => {
    const spy = stubFetch(
      ok(
        {
          id: '5',
          eventId: '950',
          name: 'Casey Tan',
          email: 'casey@example.com',
          status: 'Registered',
          createdAt: '2026-10-23T06:00:00',
        },
        201,
      ),
    )

    const registration = await registerForEvent(
      '950',
      { name: '  Casey Tan ', email: ' casey@example.com ' },
      attendee,
    )

    expect(registration.status).toBe('Registered')
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/attendee/events/950/registrations')
    expect(spy.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(spy.mock.calls[0][1].body)).toEqual({
      name: 'Casey Tan',
      email: 'casey@example.com',
    })
  })

  it.each([
    [409, 'rule_refused', 'Event is full.'],
    [409, 'rule_refused', 'You are already registered for this event.'],
    [404, 'event_not_open', 'That event is not open for registration.'],
    [400, 'invalid_registration', 'Give your name.'],
  ])('reads a %i refusal as a rule the page can show', async (status, code, message) => {
    stubFetch(failure(status, code, message))

    await expect(
      registerForEvent('950', { name: 'Casey', email: 'casey@example.com' }, attendee),
    ).rejects.toThrow(new EventRuleError(message))
  })

  it('leaves a server fault as the failure it is', async () => {
    stubFetch(failure(500, 'unknown', 'Internal Server Error'))

    await expect(
      registerForEvent('950', { name: 'Casey', email: 'casey@example.com' }, attendee),
    ).rejects.toBeInstanceOf(ApiError)
  })
})

describe('the Attendee’s own registrations (US20.2)', () => {
  const MINE = {
    id: '5',
    eventId: '950',
    title: 'Open House',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    venues: ['Great Hall'],
    status: 'Registered',
    name: 'Casey Tan',
    email: 'casey@example.com',
    registeredAt: '2026-10-23T06:00:00',
    withdrawnAt: '',
    canWithdraw: true,
    canRegisterAgain: false,
    placesLeft: 11,
  }

  it('lists them with the session’s token', async () => {
    const spy = stubFetch(ok([MINE]))

    expect(await listMyRegistrations(attendee)).toEqual([MINE])
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/attendee/registrations')
    expect(spy.mock.calls[0][1].headers.Authorization).toBe('Bearer attendee-token')
  })

  it('withdraws one by its id', async () => {
    const spy = stubFetch(ok({ ...MINE, status: 'Withdrawn', canWithdraw: false }))

    const withdrawn = await withdrawRegistration('5', attendee)

    expect(withdrawn.status).toBe('Withdrawn')
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/attendee/registrations/5/withdraw')
    expect(spy.mock.calls[0][1].method).toBe('POST')
  })

  it.each([
    [409, 'rule_refused', 'This event has already started, so you can no longer withdraw.'],
    [409, 'rule_refused', 'You have already withdrawn from this event.'],
    [404, 'registration_not_found', 'That registration no longer exists.'],
  ])('reads a %i refusal to withdraw as a rule the page can show', async (status, code, message) => {
    stubFetch(failure(status, code, message))

    await expect(withdrawRegistration('5', attendee)).rejects.toThrow(new EventRuleError(message))
  })
})

describe('parseCapacity', () => {
  it('reads a whole number of places', () => {
    expect(parseCapacity('50')).toBe(50)
    expect(parseCapacity(' 1 ')).toBe(1)
  })

  it('treats an empty box as no capacity given', () => {
    expect(parseCapacity('')).toBeNull()
    expect(parseCapacity('   ')).toBeNull()
  })

  it.each(['0', '-1', '1.5', 'abc', '1e3', '2147483648'])('refuses %s', (text) => {
    expect(parseCapacity(text)).toBe('invalid')
  })

  it('takes the largest number the column holds', () => {
    expect(parseCapacity('2147483647')).toBe(2147483647)
  })
})

describe('validateRegistration', () => {
  it('accepts a name and a valid email', () => {
    expect(validateRegistration({ name: 'Casey', email: 'casey@example.com' })).toBeNull()
  })

  it('asks for the name first, then the email, as the server does', () => {
    expect(validateRegistration({ name: ' ', email: '' })).toBe('Give your name.')
    expect(validateRegistration({ name: 'Casey', email: '  ' })).toBe('Give your email address.')
  })

  it.each(['casey', 'casey@', '@example.com', 'casey@example', 'casey tan@example.com'])(
    'refuses %s as an email',
    (email) => {
      expect(validateRegistration({ name: 'Casey', email })).toBe(
        'Give a valid email address, such as name@example.com.',
      )
    },
  )

  it('takes 255 characters and refuses 256', () => {
    const local = 'a'.repeat(243)
    expect(validateRegistration({ name: 'n'.repeat(255), email: `${local}@example.com` })).toBeNull()
    expect(validateRegistration({ name: 'n'.repeat(256), email: 'c@example.com' })).toBe(
      'Keep your name to 255 characters or fewer.',
    )
    expect(validateRegistration({ name: 'Casey', email: `${local}a@example.com` })).toBe(
      'Keep your email address to 255 characters or fewer.',
    )
  })
})

describe('describePlacesLeft', () => {
  it('counts down in words, and says when the event is full', () => {
    expect(describePlacesLeft(12)).toBe('12 places left')
    expect(describePlacesLeft(1)).toBe('1 place left')
    expect(describePlacesLeft(0)).toBe(EVENT_FULL_MESSAGE)
    expect(EVENT_FULL_MESSAGE).toBe('Event is full.')
  })
})
