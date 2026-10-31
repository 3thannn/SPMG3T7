/**
 * US9.1a-c, US9.2, US9.3 and US12.2: the venue client calls and form rules
 * venuesStore.test.ts does not reach.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  VenueRuleError,
  createVenue,
  deleteVenue,
  formatUnavailabilityReason,
  getAvailability,
  getVenue,
  listVenues,
  NO_FILTERS,
  saveVenue,
  validateUnavailability,
  type UnavailabilityInput,
  type UnavailabilityRecord,
  type VenueInput,
} from './venuesStore'
import { failure, ok, sent, stubFetch } from './test/fetch'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const staff = buildSession({ role: 'Venue Staff', token: 'session-token' })

const VENUE = { name: 'Great Hall', location: 'Main Campus', capacity: '500' } as unknown as VenueInput

describe('the catalogue', () => {
  it('lists every venue when nothing is filtered', async () => {
    const spy = stubFetch(ok([{ id: '1' }]))

    const venues = await listVenues(staff)

    expect(venues).toHaveLength(1)
    expect(sent(spy).path).toBe('/venues')
  })

  it('narrows by the filters given', async () => {
    const spy = stubFetch(ok([]))

    await listVenues(staff, { ...NO_FILTERS, minCapacity: '100', location: 'Library' })

    expect(sent(spy).path).toBe('/venues?minCapacity=100&location=Library')
  })

  it('sends layout, facilities and the time, and leaves blank ones out', async () => {
    const spy = stubFetch(ok([]))

    await listVenues(staff, {
      ...NO_FILTERS,
      layout: ' Theatre ',
      facilities: 'Stage, Projector',
      startsAt: '2027-11-02T18:00',
      endsAt: '  ',
    })

    expect(sent(spy).path).toBe(
      '/venues?layout=Theatre&facilities=Stage%2C+Projector&startsAt=2027-11-02T18%3A00',
    )
  })

  it('a filter the server cannot read is a sentence the reader can fix', async () => {
    stubFetch(failure(400, 'Give the capacity as a whole number.'))

    await expect(listVenues(staff)).rejects.toEqual(
      new VenueRuleError('Give the capacity as a whole number.'),
    )
  })

  it('any other failure stays an API error', async () => {
    stubFetch(failure(500))

    await expect(listVenues(staff)).rejects.toBeInstanceOf(ApiError)
  })
})

it("reads a venue's availability over a range (US12.3)", async () => {
  const spy = stubFetch(ok({ venueId: '1', from: '2027-03-01', to: '2027-03-14', entries: [] }))

  const availability = await getAvailability('1', { from: '2027-03-01', to: '2027-03-14' }, staff)

  expect(availability.entries).toEqual([])
  expect(sent(spy).path).toBe('/venues/1/availability?from=2027-03-01&to=2027-03-14')
})

describe('one venue', () => {
  it('reads it by id', async () => {
    const spy = stubFetch(ok({ id: '1', name: 'Great Hall' }))

    expect(await getVenue('1', staff)).toEqual({ id: '1', name: 'Great Hall' })
    expect(sent(spy).path).toBe('/venues/1')
  })

  it('is null when there is no such record', async () => {
    stubFetch(failure(404, 'That venue does not exist.'))

    expect(await getVenue('99', staff)).toBeNull()
  })

  it('throws on any other failure', async () => {
    stubFetch(failure(500))

    await expect(getVenue('1', staff)).rejects.toBeInstanceOf(ApiError)
  })

  it('adds a venue as typed', async () => {
    const spy = stubFetch(ok({ id: '4' }, 201))

    await createVenue(VENUE, staff)

    expect(sent(spy)).toEqual({ path: '/venues', method: 'POST', body: VENUE })
  })

  it('a refused add is a sentence', async () => {
    stubFetch(failure(409, 'A venue called Great Hall already exists.'))

    await expect(createVenue(VENUE, staff)).rejects.toEqual(
      new VenueRuleError('A venue called Great Hall already exists.'),
    )
  })

  it('saves an edit to its id, and a refused one is a sentence', async () => {
    const spy = stubFetch(ok({ id: '1' }))
    await saveVenue('1', VENUE, staff)
    expect(sent(spy)).toEqual({ path: '/venues/1', method: 'PUT', body: VENUE })

    stubFetch(failure(409, 'A venue called Great Hall already exists.'))
    await expect(saveVenue('1', VENUE, staff)).rejects.toEqual(
      new VenueRuleError('A venue called Great Hall already exists.'),
    )
  })

  it('deletes by id', async () => {
    const spy = stubFetch(ok(null, 204))

    await deleteVenue('1', staff)

    expect(sent(spy)).toMatchObject({ path: '/venues/1', method: 'DELETE' })
  })

  it('a refused delete is a sentence', async () => {
    stubFetch(failure(409, 'Great Hall has bookings, so it cannot be deleted.'))

    await expect(deleteVenue('1', staff)).rejects.toEqual(
      new VenueRuleError('Great Hall has bookings, so it cannot be deleted.'),
    )
  })

  it('an unexpected failure to delete stays an API error', async () => {
    stubFetch(failure(500))

    await expect(deleteVenue('1', staff)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('unavailability reasons (US12.2)', () => {
  const RANGE: UnavailabilityInput = {
    startDate: '2026-11-02',
    endDate: '2026-11-06',
    reasonType: 'maintenance',
    otherReason: '',
  }

  it('refuses a reason type the form does not offer', () => {
    const tampered = { ...RANGE, reasonType: 'party' } as unknown as UnavailabilityInput

    expect(validateUnavailability(tampered)).toBe('Select a valid reason type.')
  })

  it('"other" needs its own words', () => {
    expect(validateUnavailability({ ...RANGE, reasonType: 'other', otherReason: '   ' })).toBe(
      'Give a custom reason when selecting "Other".',
    )
  })

  it('a reason type it does not know reads as no reason, not as blank', () => {
    const record = { reasonType: 'party', otherReason: '' } as unknown as UnavailabilityRecord

    expect(formatUnavailabilityReason(record)).toBe('No reason given')
  })
})
