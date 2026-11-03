/**
 * The event client calls eventsStore.test.ts does not reach: US7.3 clarification,
 * US4.5 completion, the US14.1 booking calls, US18.1 suitability, US14.2
 * cancelling and the US14.5 replacement venue. Each sends what the server
 * expects, and turns a refusal into a sentence the page can show.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  EventRuleError,
  cancelBooking,
  checkSuitability,
  completeEvent,
  confirmEvent,
  formatBookingTimes,
  getConfirmReadiness,
  listBookings,
  recheckArrangements,
  rejectEvent,
  requestBooking,
  requestClarification,
  requestReplacementVenue,
  searchReplacementVenues,
  validateBooking,
  type BookingInput,
} from './eventsStore'
import { failure, ok, sent, stubFetch } from './test/fetch'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const coordinator = buildSession({ role: 'Event Coordinator', token: 'session-token' })

const BOOKING: BookingInput = {
  venueId: '1',
  startsAt: '2027-11-02T09:00',
  endsAt: '2027-11-02T17:00',
  headcount: '120',
  layout: 'Theatre',
  facilities: 'Stage, Projector',
  accessibilityNeeds: 'Hearing loop',
}

describe('what each call sends', () => {
  it.each([
    [
      'asks the Organiser for clarification',
      () => requestClarification('7', 'Which room layout?', coordinator),
      '/events/7/clarification',
      'POST',
      { message: 'Which room layout?' },
    ],
    ['completes an ended event', () => completeEvent('7', coordinator), '/events/7/complete', 'POST', undefined],
    ["lists an event's bookings", () => listBookings('7', coordinator), '/events/7/bookings', 'GET', undefined],
    [
      "rechecks an event's arrangements (US11.2)",
      () => recheckArrangements('7', coordinator),
      '/events/7/arrangements/recheck',
      'POST',
      undefined,
    ],
    [
      'cancels a booking with its reason',
      () => cancelBooking('7', '55', 'Moved online', coordinator),
      '/events/7/bookings/55/cancel',
      'POST',
      { reason: 'Moved online' },
    ],
    [
      'requests a replacement venue for a flagged booking',
      () => requestReplacementVenue('55', '2', coordinator),
      '/bookings/55/request-replacement',
      'POST',
      { venueId: '2' },
    ],
  ])('%s', async (_name, call, path, method, body) => {
    const spy = stubFetch(ok({}))

    await call()

    expect(sent(spy)).toEqual({ path, method, body })
  })

  it('requests a booking with the headcount as a number and the lists split', async () => {
    const spy = stubFetch(ok({ id: '55' }, 201))

    await requestBooking('7', BOOKING, coordinator)

    const { path, method, body } = sent(spy)
    expect([path, method]).toEqual(['/events/7/bookings', 'POST'])
    expect(body).toMatchObject({
      venueId: '1',
      headcount: 120,
      layout: 'Theatre',
      facilities: ['Stage', 'Projector'],
    })
  })

  it('checks suitability with the same payload as the request', async () => {
    const spy = stubFetch(ok({ suitable: true, problems: [] }))

    await checkSuitability('7', BOOKING, coordinator)

    expect(sent(spy).path).toBe('/events/7/bookings/suitability')
    expect(sent(spy).body).toMatchObject({ venueId: '1', headcount: 120 })
  })

  it('searches replacement venues with only the filters given', async () => {
    const spy = stubFetch(ok([]))

    await searchReplacementVenues('55', coordinator, {
      minCapacity: '100',
      location: '',
      accessibility: '',
    })

    expect(sent(spy).path).toBe('/bookings/55/replacement-venues?minCapacity=100')
  })

  it('searches replacement venues unfiltered by default', async () => {
    const spy = stubFetch(ok([]))

    await searchReplacementVenues('55', coordinator)

    expect(sent(spy).path).toBe('/bookings/55/replacement-venues')
  })
})

describe('a refusal becomes a sentence; anything else stays an API error', () => {
  const calls = [
    ['clarification', () => requestClarification('7', 'Why?', coordinator)],
    ['completion', () => completeEvent('7', coordinator)],
    ['rejection', () => rejectEvent('7', 'No budget', coordinator)],
    ['a booking request', () => requestBooking('7', BOOKING, coordinator)],
    ['a suitability check', () => checkSuitability('7', BOOKING, coordinator)],
    ['a cancellation', () => cancelBooking('7', '55', 'Moved', coordinator)],
    ['a replacement search', () => searchReplacementVenues('55', coordinator)],
    ['a replacement request', () => requestReplacementVenue('55', '2', coordinator)],
  ] as const

  it.each(calls)('%s refused with 409', async (_name, call) => {
    stubFetch(failure(409, 'That slot is taken.'))

    await expect(call()).rejects.toEqual(new EventRuleError('That slot is taken.'))
  })

  it.each(calls)('%s failing with 500', async (_name, call) => {
    stubFetch(failure(500, 'Internal error'))

    await expect(call()).rejects.toBeInstanceOf(ApiError)
  })
})

describe('the booking form helpers', () => {
  it('asks for a start time before anything else after the venue', () => {
    expect(validateBooking({ ...BOOKING, startsAt: '  ' })).toBe('Give the booking a start time.')
  })

  it('shows an end it cannot read as it was sent, rather than "Invalid Date"', () => {
    const start = formatBookingTimes('2027-11-02T09:00+08:00', '2027-11-02T09:00+08:00')
      .split(' – ')[0]

    expect(formatBookingTimes('2027-11-02T09:00+08:00', '2027-11-02Tlate')).toBe(
      `${start} – 2027-11-02Tlate`,
    )
  })
})

describe('US4.7: confirming the event', () => {
  it('asks whether it can be confirmed', async () => {
    const spy = stubFetch(ok({ ready: false, reason: 'safety-not-approved', message: 'Not yet.' }))

    const readiness = await getConfirmReadiness('7', coordinator)

    expect(readiness.reason).toBe('safety-not-approved')
    expect(sent(spy)).toMatchObject({ path: '/events/7/confirmation', method: 'GET' })
  })

  it('confirms it, and a refusal is a sentence', async () => {
    const spy = stubFetch(ok({ id: '7', status: 'Confirmed' }))
    expect((await confirmEvent('7', coordinator)).status).toBe('Confirmed')
    expect(sent(spy)).toMatchObject({ path: '/events/7/confirm', method: 'POST' })

    stubFetch(failure(409, 'Breakout Room B is still awaiting Venue Staff approval.'))
    await expect(confirmEvent('7', coordinator)).rejects.toEqual(
      new EventRuleError('Breakout Room B is still awaiting Venue Staff approval.'),
    )
  })

  it('any other failure stays an API error', async () => {
    stubFetch(failure(500))

    await expect(confirmEvent('7', coordinator)).rejects.toBeInstanceOf(ApiError)
  })
})
