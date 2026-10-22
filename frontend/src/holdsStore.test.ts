/** US14.3: the hold form's own check, which mirrors the server's rules. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  listHoldableEvents,
  listHolds,
  nowLocal,
  placeHold,
  validateHold,
  type HoldInput,
} from './holdsStore'
import { EventRuleError, requestHeldBooking } from './eventsStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

const NOW = '2027-10-01T09:00'

const HOLD: HoldInput = {
  eventId: '900',
  startsAt: '2027-11-02T09:00',
  endsAt: '2027-11-02T17:00',
  expiresAt: '2027-10-08T17:00',
}

describe('validateHold (US14.3)', () => {
  it('TC-HF08 accepts a complete hold', () => {
    expect(validateHold(HOLD, NOW)).toBe('')
  })

  it.each([
    [{ eventId: '' }, 'Choose the event to hold this venue for.'],
    [{ startsAt: '' }, 'Give the booking a start time.'],
    [{ endsAt: '' }, 'Give the booking an end time.'],
    [{ endsAt: '2027-11-02T09:00' }, 'The booking must end after it starts.'],
    [{ expiresAt: '' }, 'Give the hold an expiry date and time.'],
    [{ expiresAt: '2027-09-30T09:00' }, 'The hold must expire in the future.'],
    [{ expiresAt: NOW }, 'The hold must expire in the future.'],
    [{ expiresAt: '2027-11-02T09:01' }, 'The hold must expire no later than the booking starts.'],
  ])('TC-HF09 refuses %o', (overrides, message) => {
    expect(validateHold({ ...HOLD, ...overrides }, NOW)).toBe(message)
  })

  it('TC-HF10 accepts expiry a minute from now and exactly at the start', () => {
    expect(validateHold({ ...HOLD, expiresAt: '2027-10-01T09:01' }, NOW)).toBe('')
    expect(validateHold({ ...HOLD, expiresAt: HOLD.startsAt }, NOW)).toBe('')
  })
})

// -- The API calls --------------------------------------------------------------

const staff = buildSession({ role: 'Venue Staff', token: 'session-token' })

function ok(body: unknown, status = 200) {
  return { ok: true, status, json: async () => body }
}

function failure(status: number, message: string) {
  return { ok: false, status, json: async () => ({ detail: { code: 'refused', message } }) }
}

function stubFetch(response: unknown) {
  const spy = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', spy)
  return spy
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('hold API calls (US14.3)', () => {
  it('TC-HF19 lists the events a hold can be placed for', async () => {
    const spy = stubFetch(ok([{ id: '900', title: 'Open Day' }]))
    const events = await listHoldableEvents(staff)
    expect(events[0].id).toBe('900')
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/holds/events')
    expect(spy.mock.calls[0][1].headers.Authorization).toBe('Bearer session-token')
  })

  it('TC-HF20 lists one venue holds by its id', async () => {
    const spy = stubFetch(ok([]))
    await listHolds('1', staff)
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/holds?venueId=1')
  })

  it('TC-HF21 places a hold with the venue and the form values', async () => {
    const spy = stubFetch(ok({ id: '101', status: 'Held' }, 201))
    const held = await placeHold('1', HOLD, staff)
    expect(held.status).toBe('Held')
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/holds')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ venueId: '1', ...HOLD })
  })

  it.each([400, 403, 409])('TC-HF22 turns a %s refusal into a sentence to show', async (status) => {
    stubFetch(failure(status, 'The hold must expire in the future.'))
    await expect(placeHold('1', HOLD, staff)).rejects.toEqual(
      new EventRuleError('The hold must expire in the future.'),
    )
  })

  it('TC-HF23 lets a signed-out answer through to end the session', async () => {
    stubFetch(failure(401, 'Sign in again.'))
    await expect(placeHold('1', HOLD, staff)).rejects.toBeInstanceOf(ApiError)
  })

  it('TC-HF24 requests a held booking on its event', async () => {
    const coordinator = buildSession({ role: 'Event Coordinator', token: 'session-token' })
    const spy = stubFetch(ok({ id: '101', status: 'Requested' }))
    const requested = await requestHeldBooking('900', '101', coordinator)
    expect(requested.status).toBe('Requested')
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/events/900/bookings/101/request')
    expect(init.method).toBe('POST')
  })

  it('TC-HF25 turns an expired-hold refusal into a sentence to show', async () => {
    stubFetch(failure(409, 'The hold on Great Hall expired at 2027-10-08 17:00.'))
    await expect(
      requestHeldBooking('900', '101', buildSession({ role: 'Event Coordinator' })),
    ).rejects.toBeInstanceOf(EventRuleError)
  })
})

it('TC-HF30 reads now as a datetime-local value, which the form compares as text', () => {
  expect(nowLocal()).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
})
