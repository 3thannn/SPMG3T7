/**
 * The venue store's own logic — US9.1a-c, US9.2 and US9.3.
 *
 * The fetching is a thin `authorizedFetch` call and is covered where that is.
 * What is worth asserting here is the logic the pages lean on: how a record
 * with unfilled columns is presented, what the filters turn into on the wire,
 * and what the form accepts before it bothers the server.
 */

import { describe, expect, it } from 'vitest'
import {
  NOT_RECORDED,
  NO_FILTERS,
  detailOrNotRecorded,
  formatCapacity,
  hasFilters,
  parseCapacity,
  validateVenue,
  venueQuery,
} from './venuesStore'

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
    expect(hasFilters({ minCapacity: ' ', location: '  ', accessibility: ' ' })).toBe(false)
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
