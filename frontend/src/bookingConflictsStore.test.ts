/** US15.2: the flagged-bookings API call, and US15.1's period wording. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { listBookingConflicts } from './bookingConflictsStore'
import { describePeriod } from './bookingRequestsStore'
import { buildSession } from './test/sessions'

const staff = buildSession({ role: 'Venue Staff', token: 'session-token' })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('booking conflicts API call (US15.2)', () => {
  it('TC-FF16 reads the flagged list with the session token', async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: '10', label: 'Conflict – review needed' }],
    })
    vi.stubGlobal('fetch', spy)

    expect(await listBookingConflicts(staff)).toEqual([
      { id: '10', label: 'Conflict – review needed' },
    ])
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/booking-conflicts')
    expect(init.headers.Authorization).toBe('Bearer session-token')
  })
})

describe('unavailability periods (US15.1)', () => {
  it('TC-CF10 names one day by its date', () => {
    expect(describePeriod({ id: '1', startDate: '2027-11-02', endDate: '2027-11-02', reason: '' }))
      .toBe('2027-11-02')
  })

  it('TC-CF11 names several days by both dates, with the reason', () => {
    expect(
      describePeriod({
        id: '1',
        startDate: '2027-11-01',
        endDate: '2027-11-03',
        reason: 'Maintenance',
      }),
    ).toBe('2027-11-01 to 2027-11-03 (Maintenance)')
  })
})
