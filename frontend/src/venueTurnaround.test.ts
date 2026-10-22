/**
 * US9.4: setup and turnaround time — the store helpers the form and the detail
 * page share. The server (backend/app/venue_turnaround.py) enforces the same
 * rule; these say it before a round trip, in the same words.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  EMPTY_VENUE,
  MINUTES_MAX,
  formatMinutes,
  minutesField,
  parseMinutes,
  saveVenue,
  validateVenue,
} from './venuesStore'
import { buildSession } from './test/sessions'

const WHOLE = (label: string) => `Give the ${label} as a whole number of minutes, 0 or more.`

describe('parseMinutes', () => {
  it.each([
    ['', 0],
    ['   ', 0],
    ['0', 0],
    ['1', 1],
    ['45', 45],
    [' 45 ', 45],
    ['1440', 1440],
  ])('reads %o as %d', (raw, expected) => {
    expect(parseMinutes(raw, 'setup')).toBe(expected)
  })

  it('the ceiling is a day', () => {
    expect(MINUTES_MAX).toBe(24 * 60)
  })

  it.each(['-1', '-30'])('calls %o negative', (raw) => {
    expect(parseMinutes(raw, 'turnaround')).toBe('The turnaround time cannot be negative.')
  })

  it.each(['1.5', 'abc', '30m', '-', '+5', '٣', '1e3'])('refuses %o as not whole minutes', (raw) => {
    expect(parseMinutes(raw, 'setup')).toBe(WHOLE('setup time'))
  })

  it.each(['1441', '99999'])('refuses %o as more than a day', (raw) => {
    expect(parseMinutes(raw, 'turnaround')).toBe(
      'Keep the turnaround time to 1440 minutes (24 hours) or fewer.',
    )
  })
})

describe('minutesField', () => {
  it('shows a stored value, and 0 for a record that predates US9.4', () => {
    expect(minutesField(30)).toBe('30')
    expect(minutesField(0)).toBe('0')
    expect(minutesField(undefined)).toBe('0')
  })
})

describe('formatMinutes', () => {
  it.each([
    [undefined, 'None'],
    [0, 'None'],
    [-5, 'None'],
    [1, '1 minute'],
    [45, '45 minutes'],
    [59, '59 minutes'],
    [60, '60 minutes (1 h)'],
    [90, '90 minutes (1 h 30 min)'],
    [1440, '1440 minutes (24 h)'],
  ])('reads %o as %o', (value, expected) => {
    expect(formatMinutes(value)).toBe(expected)
  })
})

describe('validateVenue — US9.4 fields', () => {
  const complete = { ...EMPTY_VENUE, name: 'Atrium', location: 'Science Quarter', capacity: 90 }

  it('accepts the defaults and the ceiling', () => {
    expect(validateVenue(complete)).toBe('')
    expect(validateVenue({ ...complete, setupMinutes: 1440, turnaroundMinutes: 1440 })).toBe('')
  })

  it.each([
    [{ setupMinutes: -1 }, 'The setup time cannot be negative.'],
    [{ setupMinutes: 1.5 }, WHOLE('setup time')],
    [{ turnaroundMinutes: 1441 }, 'Keep the turnaround time to 1440 minutes (24 hours) or fewer.'],
    [{ turnaroundMinutes: Number.NaN }, WHOLE('turnaround time')],
  ])('refuses %o', (change, message) => {
    expect(validateVenue({ ...complete, ...change })).toBe(message)
  })

  it('checks setup before turnaround', () => {
    expect(validateVenue({ ...complete, setupMinutes: -1, turnaroundMinutes: -1 })).toBe(
      'The setup time cannot be negative.',
    )
  })
})

describe('saveVenue — US9.4 sends both values and hands back the re-check', () => {
  const session = buildSession({ role: 'Venue Staff', token: 'staff-token' })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('puts the minutes as JSON and returns the record with its re-check', async () => {
    const recheck = { setupMinutes: 30, turnaroundMinutes: 45, checkedBookings: 0, conflicts: [] }
    const saved = { id: '1', name: 'Great Hall', setupMinutes: 30, turnaroundMinutes: 45, recheck }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => saved })
    vi.stubGlobal('fetch', fetchMock)
    const input = {
      ...EMPTY_VENUE,
      name: 'Great Hall',
      location: 'A',
      capacity: 500,
      setupMinutes: 30,
      turnaroundMinutes: 45,
    }

    await expect(saveVenue('1', input, session)).resolves.toEqual(saved)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/venues/1')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toMatchObject({ setupMinutes: 30, turnaroundMinutes: 45 })
  })
})
