/**
 * Venue data access — US9.1a-c, US9.2 and US9.3.
 *
 * A thin layer over `/venues`, the same shape `eventsStore` settled into. Four
 * stories share this module and they do not share a role: a Coordinator reads
 * the catalogue (US9.2) and narrows it (US9.3), while Venue Staff create,
 * update and delete the records in it (US9.1a-c).
 *
 * The rules are not enforced here. The server refuses a write from a role that
 * may not make it, and refuses a duplicate name whatever the form believes; what
 * is in the browser is enough to disable a button and say why.
 */

import { ApiError, authorizedFetch, type Session } from './api'

export type VenueRecord = {
  id: string
  name: string
  location: string
  /** `venues.capacity`, NOT NULL in the schema — always a number. */
  capacity: number
  /**
   * `venues.facilities`, `accessibility_features`, `operating_hours` and
   * `supported_layouts` are all nullable columns. The server flattens a null to
   * an empty string, so these are always strings and an empty one means
   * "nothing recorded" — which the page shows as such rather than as a blank.
   */
  facilities: string
  accessibilityFeatures: string
  operatingHours: string
  /** `venues.supported_layouts`, the column US9.1a added. */
  supportedLayouts: string
  createdAt: string
  updatedAt: string
}

/**
 * What the form sends to create or update a venue (US9.1a, US9.1b).
 *
 * `id` and `createdAt` are absent on purpose: US9.1b says every field is
 * editable except the system-generated ones, and the surest way to honour that
 * is to have nowhere for them to be sent from.
 */
export type VenueInput = {
  name: string
  location: string
  /** Required and positive. null is "the box is empty", which the form refuses. */
  capacity: number | null
  facilities: string
  accessibilityFeatures: string
  operatingHours: string
  supportedLayouts: string
}

/** An empty form — also what Clear resets the filters to. */
export const EMPTY_VENUE: VenueInput = {
  name: '',
  location: '',
  capacity: null,
  facilities: '',
  accessibilityFeatures: '',
  operatingHours: '',
  supportedLayouts: '',
}

/**
 * US9.3: narrow the catalogue by capacity, location and accessibility.
 *
 * Every applied filter has to match — AND, not OR. Held as the strings the
 * inputs hold, so the page has one representation of its own form rather than
 * parsing on every keystroke; `venueQuery` is where they become a request.
 */
export type VenueFilters = {
  /** A whole number of people, as typed. Empty means no floor. */
  minCapacity: string
  location: string
  accessibility: string
}

export const NO_FILTERS: VenueFilters = {
  minCapacity: '',
  location: '',
  accessibility: '',
}

/** Whether anything was actually asked for — a blank box is not a filter. */
export function hasFilters(filters: VenueFilters): boolean {
  return (
    filters.minCapacity.trim() !== '' ||
    filters.location.trim() !== '' ||
    filters.accessibility.trim() !== ''
  )
}

/**
 * The filters as a query string, or '' when none are applied.
 *
 * Empty and whitespace-only values are left out rather than sent as blanks, so
 * an untouched form asks for the whole catalogue in the same request US9.2
 * always made.
 */
export function venueQuery(filters: VenueFilters): string {
  const params = new URLSearchParams()
  const minCapacity = filters.minCapacity.trim()
  const location = filters.location.trim()
  const accessibility = filters.accessibility.trim()

  if (minCapacity) params.set('minCapacity', minCapacity)
  if (location) params.set('location', location)
  if (accessibility) params.set('accessibility', accessibility)

  const query = params.toString()
  return query ? `?${query}` : ''
}

/** Raised when a write is refused by a rule — a duplicate name, a bad field. */
export class VenueRuleError extends Error {}

/**
 * Turn the API's rule refusals into the one error the pages handle inline.
 *
 * 409 is a name already taken, 400 an incomplete record and 403 a role that may
 * not write. All three belong in the page the user is already on, unlike a 401,
 * which has to bubble up and end the session.
 */
function asRuleError(error: unknown): never {
  if (error instanceof ApiError && [400, 403, 409].includes(error.status)) {
    throw new VenueRuleError(error.message)
  }
  throw error
}

/**
 * US9.2 and US9.3: the catalogue, narrowed by whatever was asked for.
 *
 * A filter the server cannot read comes back 400, and it is the one failure
 * here the reader can fix themselves — so it reaches the page as its own
 * sentence, the way a refused write does. Everything else stays an `ApiError`
 * for the page to describe as the unexpected failure it is.
 */
export async function listVenues(
  session: Session,
  filters: VenueFilters = NO_FILTERS,
): Promise<VenueRecord[]> {
  try {
    const response = await authorizedFetch(`/venues${venueQuery(filters)}`, session.token)
    return (await response.json()) as VenueRecord[]
  } catch (error) {
    if (error instanceof ApiError && error.status === 400) {
      throw new VenueRuleError(error.message)
    }
    throw error
  }
}

/** The venue, or null when there is no such record. */
export async function getVenue(id: string, session: Session): Promise<VenueRecord | null> {
  try {
    const response = await authorizedFetch(`/venues/${id}`, session.token)
    return (await response.json()) as VenueRecord
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

/** US9.1a: add a venue to the catalogue. Venue Staff only — the server checks. */
export async function createVenue(
  input: VenueInput,
  session: Session,
): Promise<VenueRecord> {
  try {
    const response = await authorizedFetch('/venues', session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return (await response.json()) as VenueRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US9.1b: update a venue. Everything but the system-generated fields. */
export async function saveVenue(
  id: string,
  input: VenueInput,
  session: Session,
): Promise<VenueRecord> {
  try {
    const response = await authorizedFetch(`/venues/${id}`, session.token, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return (await response.json()) as VenueRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/** US9.1c: remove a venue. A hard delete, and there is no undo to offer. */
export async function deleteVenue(id: string, session: Session): Promise<void> {
  try {
    await authorizedFetch(`/venues/${id}`, session.token, { method: 'DELETE' })
  } catch (error) {
    return asRuleError(error)
  }
}

/** A detail the database has no value for, said in words rather than left blank. */
export const NOT_RECORDED = 'Not recorded'

export function detailOrNotRecorded(value: string): string {
  return value.trim() === '' ? NOT_RECORDED : value
}

/**
 * Capacity as the catalogue reads it — "500 people", with the singular handled
 * because a two-person meeting room is a real venue.
 */
export function formatCapacity(capacity: number): string {
  if (!Number.isFinite(capacity) || capacity <= 0) return NOT_RECORDED
  return `${capacity.toLocaleString()} ${capacity === 1 ? 'person' : 'people'}`
}

/**
 * Read a capacity field: the number the column will hold, or 'invalid'.
 *
 * US9.1a requires a positive integer, so an empty box is null ("not filled in
 * yet", which the form refuses on submit) and anything that is not a positive
 * whole number is 'invalid'. Kept here beside `formatCapacity` so reading and
 * writing the same column agree about what it accepts.
 */
export function parseCapacity(raw: string): number | null | 'invalid' {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (!/^\d+$/.test(trimmed)) return 'invalid'
  const value = Number(trimmed)
  return value > 0 ? value : 'invalid'
}

/** A capacity as the form shows it — null becomes an empty field. */
export function capacityField(value: number | null): string {
  return value === null ? '' : String(value)
}

/**
 * US9.1a: name, location and a positive capacity are required; the rest is not.
 *
 * Returns the first problem as a sentence, or '' when the record is complete.
 * The server checks all of this again and its refusal is the rule — this is so
 * the form can say what is missing without a round trip.
 */
export function validateVenue(input: VenueInput): string {
  if (!input.name.trim()) return 'Give the venue a name.'
  if (!input.location.trim()) return 'Give the venue a location.'
  if (input.capacity === null) return 'Give the venue a capacity.'
  if (!Number.isInteger(input.capacity) || input.capacity < 1) {
    return 'Capacity must be a positive whole number of people.'
  }
  return ''
}
