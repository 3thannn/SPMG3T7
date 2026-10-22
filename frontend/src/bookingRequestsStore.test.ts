/** US16.1: the booking-request API calls and how their refusals reach the page. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  approveBookingRequest,
  listBookingRequests,
  rejectBookingRequest,
} from './bookingRequestsStore'
import { EventRuleError } from './eventsStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

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

describe('booking request API calls (US16.1)', () => {
  it('TC-DF01 reads the queue with the session token', async () => {
    const spy = stubFetch(ok([{ id: '11' }]))
    expect(await listBookingRequests(staff)).toEqual([{ id: '11' }])
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/booking-requests')
    expect(init.headers.Authorization).toBe('Bearer session-token')
  })

  it('TC-DF02 approves one request', async () => {
    const spy = stubFetch(ok({ id: '11', status: 'Confirmed' }))
    expect((await approveBookingRequest('11', staff)).status).toBe('Confirmed')
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/booking-requests/11/approve')
    expect(init.method).toBe('POST')
  })

  it('TC-DF03 rejects one request with the reason and suggestion', async () => {
    const spy = stubFetch(ok({ id: '11', status: 'Rejected' }))
    await rejectBookingRequest('11', 'Closed that week.', 'Bertha Room', staff)
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/booking-requests/11/reject')
    expect(JSON.parse(init.body)).toEqual({ reason: 'Closed that week.', suggestion: 'Bertha Room' })
  })

  it.each([400, 403, 409])('TC-DF04 turns a %s refusal into a sentence to show', async (status) => {
    stubFetch(failure(status, 'Great Hall is already taken for this slot.'))
    await expect(approveBookingRequest('11', staff)).rejects.toEqual(
      new EventRuleError('Great Hall is already taken for this slot.'),
    )
    stubFetch(failure(status, 'Give the Coordinator a reason.'))
    await expect(rejectBookingRequest('11', '', '', staff)).rejects.toBeInstanceOf(EventRuleError)
  })

  it('TC-DF05 lets a signed-out answer through to end the session', async () => {
    stubFetch(failure(401, 'Sign in again.'))
    await expect(approveBookingRequest('11', staff)).rejects.toBeInstanceOf(ApiError)
    stubFetch(failure(401, 'Sign in again.'))
    await expect(rejectBookingRequest('11', 'x', '', staff)).rejects.toBeInstanceOf(ApiError)
  })
})
