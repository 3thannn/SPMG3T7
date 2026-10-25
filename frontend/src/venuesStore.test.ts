/**
 * The venue store's own logic — US9.1a-c, US9.2 and US9.3.
 *
 * The fetching is a thin `authorizedFetch` call and is covered where that is.
 * What is worth asserting here is the logic the pages lean on: how a record
 * with unfilled columns is presented, what the filters turn into on the wire,
 * and what the form accepts before it bothers the server.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  EMPTY_UNAVAILABILITY,
  listedItems,
  NOT_RECORDED,
  NO_FILTERS,
  REASON_MAX,
  VenueRuleError,
  describeDates,
  detailOrNotRecorded,
  formatCapacity,
  formatDate,
  formatDateRange,
  hasDates,
  hasFilters,
  listUnavailability,
  markUnavailable,
  parseCapacity,
  rangeTiming,
  todayIso,
  validateUnavailability,
  validateVenue,
  venueQuery,
} from './venuesStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

describe('detailOrNotRecorded', () => {
  it('passes a recorded detail through unchanged', () => {
    expect(detailOrNotRecorded('Stage, PA system')).toBe('Stage, PA system')
  })

  it('names an empty detail rather than rendering a blank', () => {
    expect(detailOrNotRecorded('')).toBe(NOT_RECORDED)
  })

  it('treats whitespace as nothing recorded', () => {
    expect(detailOrNotRecorded('   ')).toBe(NOT_RECORDED)
  })
})

describe('formatCapacity', () => {
  it('reads as a number of people', () => {
    expect(formatCapacity(500)).toBe('500 people')
  })

  it('says person for a venue that holds one', () => {
    expect(formatCapacity(1)).toBe('1 person')
  })

  it('groups a large capacity so it can be read at a glance', () => {
    // toLocaleString under the test locale; the separator is not asserted.
    expect(formatCapacity(1200)).toMatch(/people$/)
    expect(formatCapacity(1200)).not.toBe('1200 people')
  })

  it('does not claim a capacity it does not have', () => {
    // NOT NULL in the schema, so these are malformed rather than expected —
    // but a 0 rendered as "0 people" would read as a deliberate answer.
    expect(formatCapacity(0)).toBe(NOT_RECORDED)
    expect(formatCapacity(Number.NaN)).toBe(NOT_RECORDED)
  })
})

describe('venueQuery', () => {
  it('asks for the whole catalogue when nothing is filtered', () => {
    expect(venueQuery(NO_FILTERS)).toBe('')
  })

  it('sends only the filters that were filled in', () => {
    expect(venueQuery({ ...NO_FILTERS, location: 'Library' })).toBe('?location=Library')
  })

  it('sends all three together, which the server ANDs', () => {
    const query = venueQuery({
      ...NO_FILTERS,
      minCapacity: '200',
      location: 'Library',
      accessibility: 'Step-free',
    })

    expect(query.startsWith('?')).toBe(true)
    expect(query).toContain('minCapacity=200')
    expect(query).toContain('location=Library')
    expect(query).toContain('accessibility=Step-free')
  })

  it('treats a whitespace-only box as not filled in', () => {
    expect(venueQuery({ ...NO_FILTERS, location: '   ' })).toBe('')
  })

  it('trims a filter rather than searching for the spaces', () => {
    expect(venueQuery({ ...NO_FILTERS, location: '  Library  ' })).toBe('?location=Library')
  })

  it('escapes a value that would otherwise break the query string', () => {
    expect(venueQuery({ ...NO_FILTERS, location: 'A & B' })).toContain('location=A+%26+B')
  })
})

describe('hasFilters', () => {
  it('is false for an untouched form', () => {
    expect(hasFilters(NO_FILTERS)).toBe(false)
  })

  it('is false when every box holds only spaces', () => {
    expect(
      hasFilters({
        minCapacity: ' ',
        location: '  ',
        accessibility: ' ',
        availableFrom: ' ',
        availableTo: '',
      }),
    ).toBe(false)
  })

  it('is true as soon as one filter is real', () => {
    expect(hasFilters({ ...NO_FILTERS, minCapacity: '50' })).toBe(true)
    expect(hasFilters({ ...NO_FILTERS, location: 'Library' })).toBe(true)
    expect(hasFilters({ ...NO_FILTERS, accessibility: 'Ramp' })).toBe(true)
  })
})

describe('parseCapacity', () => {
  it('reads a whole number of people', () => {
    expect(parseCapacity('90')).toBe(90)
  })

  it('treats an empty box as not filled in yet', () => {
    expect(parseCapacity('')).toBeNull()
    expect(parseCapacity('   ')).toBeNull()
  })

  it('refuses anything that is not a positive whole number', () => {
    // US9.1a says positive, so nought is refused as well as a negative.
    for (const raw of ['0', '-5', '1.5', 'many', '9e9']) {
      expect(parseCapacity(raw)).toBe('invalid')
    }
  })
})

describe('validateVenue', () => {
  const complete = {
    name: 'Atrium',
    location: 'Science Quarter',
    capacity: 90,
    facilities: '',
    accessibilityFeatures: '',
    operatingHours: '',
    supportedLayouts: '',
    setupMinutes: 0,
    turnaroundMinutes: 0,
  }

  it('accepts a record with only the required fields', () => {
    expect(validateVenue(complete)).toBe('')
  })

  it('requires a name', () => {
    expect(validateVenue({ ...complete, name: '  ' })).toContain('name')
  })

  it('requires a location', () => {
    expect(validateVenue({ ...complete, location: '' })).toContain('location')
  })

  it('requires a capacity', () => {
    expect(validateVenue({ ...complete, capacity: null })).toContain('capacity')
  })

  it('requires the capacity to be positive', () => {
    expect(validateVenue({ ...complete, capacity: 0 })).toContain('positive')
    expect(validateVenue({ ...complete, capacity: -5 })).toContain('positive')
  })
})

// --- US12.1 ------------------------------------------------------------------

describe('planning dates in the catalogue query', () => {
  it('sends both dates when both are given', () => {
    expect(
      venueQuery({ ...NO_FILTERS, availableFrom: '2026-11-02', availableTo: '2026-11-06' }),
    ).toBe('?availableFrom=2026-11-02&availableTo=2026-11-06')
  })

  it('sends one date alone, for the server to read as that day', () => {
    expect(venueQuery({ ...NO_FILTERS, availableTo: '2026-11-04' })).toBe(
      '?availableTo=2026-11-04',
    )
  })

  it('leaves blank dates out', () => {
    expect(venueQuery({ ...NO_FILTERS, availableFrom: '  ', availableTo: '' })).toBe('')
  })

  it('counts a date as a filter, and either box is enough', () => {
    expect(hasDates({ ...NO_FILTERS, availableFrom: '2026-11-02' })).toBe(true)
    expect(hasDates({ ...NO_FILTERS, availableTo: '2026-11-02' })).toBe(true)
    expect(hasDates(NO_FILTERS)).toBe(false)
    expect(hasFilters({ ...NO_FILTERS, availableTo: '2026-11-02' })).toBe(true)
  })
})

describe('describeDates', () => {
  it('names a range from start to end', () => {
    expect(
      describeDates({ ...NO_FILTERS, availableFrom: '2026-11-02', availableTo: '2026-11-06' }),
    ).toBe(formatDateRange('2026-11-02', '2026-11-06'))
  })

  it.each([
    ['only a start', { availableFrom: '2026-11-04' }],
    ['only an end', { availableTo: '2026-11-04' }],
    ['the same day twice', { availableFrom: '2026-11-04', availableTo: '2026-11-04' }],
  ])('says "on" one day for %s', (_, dates) => {
    expect(describeDates({ ...NO_FILTERS, ...dates })).toBe(`on ${formatDate('2026-11-04')}`)
  })
})

describe('validateUnavailability', () => {
  const valid = { startDate: '2026-11-02', endDate: '2026-11-06', reasonType: 'maintenance', otherReason: '' }

  it('accepts a complete range', () => {
    expect(validateUnavailability(valid)).toBe('')
  })

  it('accepts a one-day range, the tightest one there is', () => {
    expect(validateUnavailability({ ...valid, endDate: '2026-11-02' })).toBe('')
  })

  it('accepts an end one day after the start', () => {
    expect(validateUnavailability({ ...valid, endDate: '2026-11-03' })).toBe('')
  })

  it('refuses an end one day before the start', () => {
    expect(validateUnavailability({ ...valid, endDate: '2026-11-01' })).toBe(
      'The end date cannot be earlier than the start date.',
    )
  })

  it('compares across a month end and a year end as dates', () => {
    expect(
      validateUnavailability({ ...valid, startDate: '2026-10-31', endDate: '2026-11-01' }),
    ).toBe('')
    expect(
      validateUnavailability({ ...valid, startDate: '2026-12-31', endDate: '2027-01-01' }),
    ).toBe('')
    expect(
      validateUnavailability({ ...valid, startDate: '2027-01-01', endDate: '2026-12-31' }),
    ).not.toBe('')
  })

  it('asks for the start first, then the end', () => {
    expect(validateUnavailability(EMPTY_UNAVAILABILITY)).toBe('Give the start date.')
    expect(validateUnavailability({ ...valid, startDate: '  ' })).toBe('Give the start date.')
    expect(validateUnavailability({ ...valid, endDate: '' })).toBe('Give the end date.')
  })

  it('takes a reason at the limit and refuses one over it', () => {
    expect(validateUnavailability({ ...valid, reasonType: 'other', otherReason: 'x'.repeat(REASON_MAX) })).toBe('')
    expect(validateUnavailability({ ...valid, reasonType: 'other', otherReason: 'x'.repeat(REASON_MAX + 1) })).toBe(
      `Keep the custom reason to ${REASON_MAX} characters or fewer.`,
    )
  })

  it('counts the reason after trimming, as the server does', () => {
    expect(
      validateUnavailability({ ...valid, reasonType: 'other', otherReason: `  ${'x'.repeat(REASON_MAX)}  ` }),
    ).toBe('')
  })
})

describe('todayIso', () => {
  it('is the local calendar day, padded', () => {
    expect(todayIso(new Date(2026, 0, 5, 9, 30))).toBe('2026-01-05')
  })

  it('is still today just before local midnight, whatever UTC says', () => {
    expect(todayIso(new Date(2026, 10, 4, 23, 59))).toBe('2026-11-04')
  })

  it('is today just after local midnight', () => {
    expect(todayIso(new Date(2026, 10, 4, 0, 1))).toBe('2026-11-04')
  })

  it('is the local month and year in Singapore before 8am, when UTC is still behind', () => {
    // 00:30 on 1 Jan 2027 in Singapore is 16:30 on 31 Dec 2026 in UTC: every
    // part of the date differs, so reading any of them in UTC is caught here.
    // Pinned rather than left to the machine, because CI runs in UTC.
    vi.stubEnv('TZ', 'Asia/Singapore')
    try {
      const justAfterMidnight = new Date('2026-12-31T16:30:00Z')
      expect(todayIso(justAfterMidnight)).toBe('2027-01-01')
    } finally {
      vi.unstubAllEnvs()
    }
  })
})

describe('rangeTiming', () => {
  const today = '2026-11-04'

  it.each([
    ['ended yesterday', '2026-11-01', '2026-11-03', 'past'],
    ['ends today', '2026-11-01', '2026-11-04', 'current'],
    ['is today only', '2026-11-04', '2026-11-04', 'current'],
    ['starts today', '2026-11-04', '2026-11-09', 'current'],
    ['starts tomorrow', '2026-11-05', '2026-11-09', 'upcoming'],
  ])('reads a range that %s as %s', (_, startDate, endDate, timing) => {
    expect(rangeTiming({ startDate, endDate }, today)).toBe(timing)
  })
})

describe('formatDate', () => {
  it('reads a bare date as that local day, not UTC midnight', () => {
    expect(formatDate('2026-11-02')).toBe(
      new Date(2026, 10, 2).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }),
    )
  })

  it('passes anything that is not YYYY-MM-DD through untouched', () => {
    expect(formatDate('soon')).toBe('soon')
    expect(formatDate('')).toBe('')
  })
})

describe('formatDateRange', () => {
  it('joins two different days', () => {
    expect(formatDateRange('2026-11-02', '2026-11-06')).toBe(
      `${formatDate('2026-11-02')} – ${formatDate('2026-11-06')}`,
    )
  })

  it('shows one day once', () => {
    expect(formatDateRange('2026-11-02', '2026-11-02')).toBe(formatDate('2026-11-02'))
  })

  it('shows whichever end it has', () => {
    expect(formatDateRange('2026-11-02', '')).toBe(formatDate('2026-11-02'))
    expect(formatDateRange('', '2026-11-06')).toBe(formatDate('2026-11-06'))
  })
})

describe('the unavailability requests', () => {
  const session = buildSession({ role: 'Venue Staff', token: 'staff-token' })
  const record = {
    id: '101',
    venueId: '1',
    startDate: '2026-11-02',
    endDate: '2026-11-06',
    reasonType: 'maintenance',
    otherReason: '',
    createdAt: '2026-10-01T09:00:00',
  }

  function respond(status: number, body: unknown) {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: status < 400,
      status,
      json: async () => body,
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads a venue’s ranges with the session’s token', async () => {
    const fetchMock = respond(200, [record])

    await expect(listUnavailability('1', session)).resolves.toEqual([record])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/venues/1/unavailability')
    expect(init.headers).toMatchObject({ Authorization: 'Bearer staff-token' })
  })

  it('posts a range as JSON and hands back what was stored', async () => {
    const fetchMock = respond(201, record)
    const input = { startDate: '2026-11-02', endDate: '2026-11-06', reasonType: 'maintenance', otherReason: '' }

    await expect(markUnavailable('1', input, session)).resolves.toEqual(record)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/venues/1/unavailability')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(input)
  })

  it.each([400, 403])('turns a %i refusal into a rule the form can show', async (status) => {
    respond(status, { detail: { code: 'invalid_unavailability', message: 'No.' } })

    const saving = markUnavailable('1', EMPTY_UNAVAILABILITY, session)

    await expect(saving).rejects.toBeInstanceOf(VenueRuleError)
    await expect(saving).rejects.toThrow('No.')
  })

  it('leaves a server fault as the unexpected failure it is', async () => {
    respond(500, {})

    const saving = markUnavailable('1', EMPTY_UNAVAILABILITY, session)

    await expect(saving).rejects.toBeInstanceOf(ApiError)
    await expect(saving).rejects.not.toBeInstanceOf(VenueRuleError)
  })

  it('lets a failed read through for the card to describe', async () => {
    respond(404, { detail: { code: 'venue_not_found', message: 'Gone.' } })

    await expect(listUnavailability('999', session)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('listedItems: what a venue lists, in either of the catalogue\'s formats', () => {
  it('reads a plain list', () => {
    expect(listedItems('Theatre, standing;  cabaret ')).toEqual(['Theatre', 'standing', 'cabaret'])
  })

  it('reads a Postgres array literal, quotes and all', () => {
    expect(listedItems('{stage,"AV system","the \\"big\\" room, upstairs"}')).toEqual([
      'stage',
      'AV system',
      'the "big" room, upstairs',
    ])
  })

  it('lists nothing for an empty field or an empty array', () => {
    expect(listedItems('')).toEqual([])
    expect(listedItems('{}')).toEqual([])
  })
})
