/**
 * The event request module — Event Request Creation.
 *
 * Two things are being tested here. The validation mirror, field by field,
 * against a fixed "today" so the suite means the same thing in September as it
 * does in November. And `createEventRequest`, against a stubbed fetch, for what
 * it puts on the wire and how it reports a refusal.
 *
 * The page test covers the same rules through the form. This file is where each
 * one is pinned down on its own, including the inputs a form cannot produce.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  ATTENDANCE_MAX,
  createEventRequest,
  DESCRIPTION_MAX,
  EMPTY_REQUEST,
  EventRequestError,
  isCalendarDate,
  isComplete,
  minutesOfDay,
  NAME_MAX,
  parseExpectedAttendance,
  PURPOSE_MAX,
  todayIso,
  validate,
  type RequestFields,
} from './eventRequests'
import { buildSession } from './test/sessions'

const TODAY = '2026-09-15'

const COMPLETE: RequestFields = {
  name: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks, then supper.',
  proposedDate: '2026-11-02',
  startTime: '18:00',
  endTime: '21:30',
  expectedAttendance: '120',
}

/** Validate a complete request with some fields swapped out. */
function check(overrides: Partial<RequestFields> = {}) {
  return validate({ ...COMPLETE, ...overrides }, TODAY)
}

describe('todayIso', () => {
  it('formats a date as YYYY-MM-DD', () => {
    expect(todayIso(new Date(2026, 8, 15, 12, 0))).toBe('2026-09-15')
  })

  it('pads a single-digit month and day', () => {
    expect(todayIso(new Date(2026, 0, 5, 12, 0))).toBe('2026-01-05')
  })

  it('uses the local date rather than the UTC one', () => {
    // Just after midnight local time. toISOString() would say the 14th for any
    // timezone east of Greenwich, which would refuse an event proposed for this
    // morning as being in the past.
    expect(todayIso(new Date(2026, 8, 15, 0, 30))).toBe('2026-09-15')
  })

  it('uses the real clock when given no date', () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('isCalendarDate', () => {
  it('accepts a real day', () => {
    expect(isCalendarDate('2026-11-02')).toBe(true)
  })

  it('accepts the 29th of February in a leap year', () => {
    expect(isCalendarDate('2028-02-29')).toBe(true)
  })

  it.each(['', '2026/11/02', '02-11-2026', '20261102', '2026-11-2', 'soon'])(
    'refuses %s, which is not the shape the field produces',
    (raw) => {
      expect(isCalendarDate(raw)).toBe(false)
    },
  )

  it.each(['2026-02-30', '2026-13-01', '2027-02-29'])(
    'refuses %s, which is well formed but not a day',
    (raw) => {
      // Date() rolls these forward rather than refusing them, so the check has
      // to ask what came back rather than whether it parsed.
      expect(isCalendarDate(raw)).toBe(false)
    },
  )
})

describe('minutesOfDay', () => {
  it('reads hours and minutes', () => {
    expect(minutesOfDay('18:30')).toBe(18 * 60 + 30)
  })

  it('reads midnight as zero', () => {
    expect(minutesOfDay('00:00')).toBe(0)
  })

  it('accepts seconds, which a time input sends once its step is finer', () => {
    expect(minutesOfDay('18:30:45')).toBe(18 * 60 + 30)
  })

  it.each(['', '6pm', '18', '1:00', '18:00+08:00'])('refuses %s', (raw) => {
    expect(minutesOfDay(raw)).toBeNull()
  })

  it.each(['25:00', '18:60'])('refuses %s, which is not a time on a clock', (raw) => {
    expect(minutesOfDay(raw)).toBeNull()
  })
})

describe('parseExpectedAttendance', () => {
  it('reads a positive whole number', () => {
    expect(parseExpectedAttendance('120')).toBe(120)
  })

  it('reads one, the smallest allowed', () => {
    expect(parseExpectedAttendance('1')).toBe(1)
  })

  it('ignores surrounding spaces', () => {
    expect(parseExpectedAttendance('  120  ')).toBe(120)
  })

  it('reads an explicit plus', () => {
    expect(parseExpectedAttendance('+7')).toBe(7)
  })

  it('asks for a number when the field is empty', () => {
    expect(parseExpectedAttendance('')).toBe('Give the expected attendance.')
  })

  it('asks for a number when the field is only spaces', () => {
    expect(parseExpectedAttendance('   ')).toBe('Give the expected attendance.')
  })

  it.each(['twenty', '12.5', '1e3', '1,000', '12 people'])(
    'refuses %s as not a whole number',
    (raw) => {
      expect(parseExpectedAttendance(raw)).toBe('Expected attendance must be a whole number.')
    },
  )

  it('refuses zero, because the story says positive', () => {
    expect(parseExpectedAttendance('0')).toBe('Expected attendance must be at least 1.')
  })

  it('refuses a negative number', () => {
    expect(parseExpectedAttendance('-5')).toBe('Expected attendance must be at least 1.')
  })

  it('allows the ceiling itself', () => {
    expect(parseExpectedAttendance(String(ATTENDANCE_MAX))).toBe(ATTENDANCE_MAX)
  })

  it('refuses a number above the ceiling as a slipped keypress', () => {
    expect(parseExpectedAttendance(String(ATTENDANCE_MAX + 1))).toBe(
      'Expected attendance cannot be more than 1,000,000.',
    )
  })
})

describe('validate', () => {
  it('finds nothing wrong with a complete request', () => {
    expect(check()).toEqual({})
    expect(isComplete(check())).toBe(true)
  })

  it('leaves the description optional', () => {
    expect(check({ description: '' })).toEqual({})
  })

  it('reports every empty field at once rather than one per attempt', () => {
    // The server stops at the first; a form should not make someone submit six
    // times to be told about six blanks.
    const errors = validate(EMPTY_REQUEST, TODAY)

    expect(Object.keys(errors).sort()).toEqual([
      'endTime',
      'expectedAttendance',
      'name',
      'proposedDate',
      'purpose',
      'startTime',
    ])
    expect(isComplete(errors)).toBe(false)
  })

  describe('the name', () => {
    it.each(['', '   '])('is required', (name) => {
      expect(check({ name }).name).toBe('Give the event a name.')
    })

    it('may fill the column', () => {
      expect(check({ name: 'x'.repeat(NAME_MAX) }).name).toBeUndefined()
    })

    it('may not exceed it', () => {
      expect(check({ name: 'x'.repeat(NAME_MAX + 1) }).name).toBe(
        'Keep the name to 255 characters or fewer.',
      )
    })
  })

  describe('the purpose', () => {
    it('is required, unlike on a draft', () => {
      expect(check({ purpose: '  ' }).purpose).toBe('Say what the event is for.')
    })

    it('may not exceed the column', () => {
      expect(check({ purpose: 'x'.repeat(PURPOSE_MAX + 1) }).purpose).toBe(
        'Keep the purpose to 500 characters or fewer.',
      )
    })
  })

  describe('the description', () => {
    it('may reach the chosen limit', () => {
      expect(check({ description: 'x'.repeat(DESCRIPTION_MAX) }).description).toBeUndefined()
    })

    it('may not exceed it', () => {
      expect(check({ description: 'x'.repeat(DESCRIPTION_MAX + 1) }).description).toBe(
        'Keep the description to 2000 characters or fewer.',
      )
    })
  })

  describe('the proposed date', () => {
    it('is required', () => {
      expect(check({ proposedDate: '' }).proposedDate).toBe('Give the event a proposed date.')
    })

    it('must be a real date', () => {
      expect(check({ proposedDate: '2026-02-30' }).proposedDate).toBe(
        'Give the proposed date as YYYY-MM-DD.',
      )
    })

    it('may not be yesterday', () => {
      expect(check({ proposedDate: '2026-09-14' }).proposedDate).toBe(
        'The proposed date cannot be in the past.',
      )
    })

    it('may be today', () => {
      expect(check({ proposedDate: TODAY }).proposedDate).toBeUndefined()
    })

    it('may be tomorrow', () => {
      expect(check({ proposedDate: '2026-09-16' }).proposedDate).toBeUndefined()
    })

    it('compares against the real today when none is given', () => {
      expect(validate({ ...COMPLETE, proposedDate: '1999-01-01' }).proposedDate).toBe(
        'The proposed date cannot be in the past.',
      )
    })
  })

  describe('the times', () => {
    it('requires a start', () => {
      expect(check({ startTime: '' }).startTime).toBe('Give the event a start time.')
    })

    it('requires an end', () => {
      expect(check({ endTime: '' }).endTime).toBe('Give the event an end time.')
    })

    it('requires the start to be a time', () => {
      expect(check({ startTime: '6pm' }).startTime).toBe('Give the start time as HH:MM.')
    })

    it('requires the end to be a time', () => {
      expect(check({ endTime: 'half nine' }).endTime).toBe('Give the end time as HH:MM.')
    })

    it('requires the end to be after the start', () => {
      expect(check({ startTime: '18:00', endTime: '17:00' }).endTime).toBe(
        'The end time must be after the start time.',
      )
    })

    it('refuses an end equal to the start, which is no event at all', () => {
      expect(check({ startTime: '18:00', endTime: '18:00' }).endTime).toBe(
        'The end time must be after the start time.',
      )
    })

    it('accepts a single minute', () => {
      expect(check({ startTime: '18:00', endTime: '18:01' }).endTime).toBeUndefined()
    })

    it('compares clock times rather than text', () => {
      expect(check({ startTime: '09:00', endTime: '10:00' }).endTime).toBeUndefined()
    })

    it('does not complain about the order when the start is unreadable', () => {
      // Two complaints about one mistake reads as two mistakes.
      const errors = check({ startTime: 'nonsense', endTime: '09:00' })

      expect(errors.startTime).toBe('Give the start time as HH:MM.')
      expect(errors.endTime).toBeUndefined()
    })
  })
})

describe('createEventRequest', () => {
  const session = buildSession()
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /** A fetch answer, as `authorizedFetch` expects to find it. */
  function answer(status: number, body: unknown) {
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    }
  }

  function sent() {
    const [, init] = fetchMock.mock.calls[0]
    return JSON.parse(init.body as string)
  }

  it('posts to the event requests endpoint', async () => {
    fetchMock.mockResolvedValue(answer(201, { id: '7' }))

    await createEventRequest(COMPLETE, session)

    expect(fetchMock.mock.calls[0][0]).toContain('/event-requests')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  })

  it('carries the session token', async () => {
    fetchMock.mockResolvedValue(answer(201, { id: '7' }))

    await createEventRequest(COMPLETE, session)

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer test-token')
  })

  it('sends the date and the two times as three separate fields', async () => {
    fetchMock.mockResolvedValue(answer(201, { id: '7' }))

    await createEventRequest(COMPLETE, session)

    expect(sent()).toMatchObject({
      proposedDate: '2026-11-02',
      startTime: '18:00',
      endTime: '21:30',
    })
  })

  it('sends the text fields trimmed', async () => {
    fetchMock.mockResolvedValue(answer(201, { id: '7' }))

    await createEventRequest(
      { ...COMPLETE, name: '  Padded  ', purpose: ' Why ', description: ' What ' },
      session,
    )

    expect(sent()).toMatchObject({ name: 'Padded', purpose: 'Why', description: 'What' })
  })

  it('never sends an organiser — the server reads it from the session', async () => {
    fetchMock.mockResolvedValue(answer(201, { id: '7' }))

    await createEventRequest(COMPLETE, session)

    expect(sent()).not.toHaveProperty('organiserId')
  })

  it('returns the created event', async () => {
    fetchMock.mockResolvedValue(
      answer(201, { id: '7', status: 'Submitted', endsAt: '2026-11-02T21:30' }),
    )

    const created = await createEventRequest(COMPLETE, session)

    expect(created.id).toBe('7')
    expect(created.status).toBe('Submitted')
    expect(created.endsAt).toBe('2026-11-02T21:30')
  })

  it('turns a 400 into an error carrying the server sentence', async () => {
    fetchMock.mockResolvedValue(
      answer(400, {
        detail: {
          code: 'invalid_event_request',
          message: 'The proposed date cannot be in the past.',
          field: 'proposedDate',
        },
      }),
    )

    await expect(createEventRequest(COMPLETE, session)).rejects.toThrow(
      'The proposed date cannot be in the past.',
    )
  })

  it('turns a 403 into the same error, so the page can show the reason', async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: { code: 'forbidden', message: 'The role cannot create events.' } }),
    )

    await expect(createEventRequest(COMPLETE, session)).rejects.toBeInstanceOf(
      EventRequestError,
    )
  })

  it('lets a 401 through, because it ends the session rather than the form', async () => {
    fetchMock.mockResolvedValue(
      answer(401, { detail: { code: 'session_expired', message: 'Signed out.' } }),
    )

    const failure = await createEventRequest(COMPLETE, session).catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).not.toBeInstanceOf(EventRequestError)
  })

  it('lets a network failure through untouched', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(createEventRequest(COMPLETE, session)).rejects.toThrow('Failed to fetch')
  })
})
