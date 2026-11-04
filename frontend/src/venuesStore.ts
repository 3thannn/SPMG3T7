/**
 * Venue data access — US9.1a-c, US9.2, US9.3, US9.4 and US12.1.
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
  /**
   * US9.4: whole minutes the venue is still occupied before each booking
   * (setup) and after it (turnaround). The server always sends both; optional
   * so fixtures that predate US9.4 still type-check, and read as 0 when absent.
   */
  setupMinutes?: number
  turnaroundMinutes?: number
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
  /** US9.4: whole minutes, 0 to `MINUTES_MAX`. */
  setupMinutes: number
  turnaroundMinutes: number
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
  setupMinutes: 0,
  turnaroundMinutes: 0,
}

/** One booking in a US9.4 conflict: its own times and what it really occupies. */
export type BookingWindow = {
  bookingId: string
  eventId: string
  startsAt: string
  endsAt: string
  occupiedFrom: string
  occupiedTo: string
}

export type VenueConflict = {
  first: BookingWindow
  second: BookingWindow
  /** True when the new setup or turnaround time is what made the pair clash. */
  causedByChange: boolean
}

/**
 * US9.4 kicks off US15.2's re-check when setup or turnaround changes. Bookings
 * that now clash are listed here; nothing is cancelled or removed.
 */
export type VenueRecheck = {
  setupMinutes: number
  turnaroundMinutes: number
  checkedBookings: number
  conflicts: VenueConflict[]
  /**
   * US15.2: bookings this change marked "Conflict – review needed", with their
   * Coordinators notified. Optional so an older server's answer reads as none.
   */
  flaggedBookingIds?: string[]
  /** US15.2: flagged bookings whose clash this change resolved. */
  clearedBookingIds?: string[]
}

/** What saving a venue returns: the record, plus the re-check when one ran. */
export type SavedVenue = VenueRecord & { recheck?: VenueRecheck | null }

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
  /**
   * US12.1: the dates being planned for, as YYYY-MM-DD from a date input. A
   * venue marked unavailable on any of them is left out. Either alone means
   * that one day; both empty means no dates were asked about.
   */
  availableFrom: string
  availableTo: string
  /** The brief's "supported layout", matched as part of the venue's layouts. */
  layout: string
  /** Comma-separated, as typed. The venue must list every one. */
  facilities: string
  /**
   * The time the venue is needed, as YYYY-MM-DDTHH:MM from datetime inputs. A
   * venue with a booking or a blackout then is left out. The server wants both
   * or neither, and says so.
   */
  startsAt: string
  endsAt: string
}

export const NO_FILTERS: VenueFilters = {
  minCapacity: '',
  location: '',
  accessibility: '',
  availableFrom: '',
  availableTo: '',
  layout: '',
  facilities: '',
  startsAt: '',
  endsAt: '',
}

/** Whether anything was actually asked for — a blank box is not a filter. */
export function hasFilters(filters: VenueFilters): boolean {
  return (
    filters.minCapacity.trim() !== '' ||
    filters.location.trim() !== '' ||
    filters.accessibility.trim() !== '' ||
    filters.layout.trim() !== '' ||
    filters.facilities.trim() !== '' ||
    filters.startsAt.trim() !== '' ||
    filters.endsAt.trim() !== '' ||
    hasDates(filters)
  )
}

/**
 * The planning dates as the list's summary says them: "on 4 Nov 2026" for one
 * day, "2 Nov 2026 – 6 Nov 2026" for a range. Either box alone is one day,
 * which is how the server reads it too.
 */
export function describeDates(filters: VenueFilters): string {
  const from = filters.availableFrom.trim()
  const to = filters.availableTo.trim()
  if (from && to && from !== to) return formatDateRange(from, to)
  return `on ${formatDate(from || to)}`
}

/** Whether the list is narrowed to the venues free on some dates (US12.1). */
export function hasDates(filters: VenueFilters): boolean {
  return filters.availableFrom.trim() !== '' || filters.availableTo.trim() !== ''
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
  const availableFrom = filters.availableFrom.trim()
  const availableTo = filters.availableTo.trim()

  if (minCapacity) params.set('minCapacity', minCapacity)
  if (location) params.set('location', location)
  if (accessibility) params.set('accessibility', accessibility)
  if (availableFrom) params.set('availableFrom', availableFrom)
  if (availableTo) params.set('availableTo', availableTo)
  for (const name of ['layout', 'facilities', 'startsAt', 'endsAt'] as const) {
    const value = filters[name].trim()
    if (value) params.set(name, value)
  }

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
/**
 * Week 9 (G7/A7): the layouts an event request may prefer. The standard names,
 * then every other layout a venue in the catalogue lists, so a layout Venue
 * Staff add can be chosen. Any signed-in user may read it.
 */
export async function listLayoutOptions(session: Session): Promise<string[]> {
  const response = await authorizedFetch('/venues/layouts', session.token)
  return (await response.json()) as string[]
}

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
): Promise<SavedVenue> {
  try {
    const response = await authorizedFetch(`/venues/${id}`, session.token, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return (await response.json()) as SavedVenue
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

// --- US9.4: setup and turnaround time -----------------------------------------

/**
 * The server's ceiling: a day. Team-chosen, not customer-confirmed — more than
 * a day to set up or reset a room is a typing mistake.
 */
export const MINUTES_MAX = 1440

const MINUTE_LABELS = { setup: 'setup time', turnaround: 'turnaround time' } as const
export type MinutesField = keyof typeof MINUTE_LABELS

/**
 * Read a setup or turnaround box: whole minutes, 0 to `MINUTES_MAX`. An empty
 * box is 0, the story's default. Returns the minutes or the sentence the
 * server would send, so the form and the API say the same thing.
 */
export function parseMinutes(raw: string, which: MinutesField): number | string {
  const label = MINUTE_LABELS[which]
  const trimmed = raw.trim()
  if (!trimmed) return 0
  if (/^-\d+$/.test(trimmed)) return `The ${label} cannot be negative.`
  if (!/^\d+$/.test(trimmed)) return `Give the ${label} as a whole number of minutes, 0 or more.`
  const value = Number(trimmed)
  if (value > MINUTES_MAX) {
    return `Keep the ${label} to ${MINUTES_MAX} minutes (24 hours) or fewer.`
  }
  return value
}

/** A stored value as the form shows it; a record that predates US9.4 shows 0. */
export function minutesField(value: number | undefined): string {
  return String(value ?? 0)
}

/** "None", "1 minute", "45 minutes", "90 minutes (1 h 30 min)". */
export function formatMinutes(value: number | undefined): string {
  const minutes = value ?? 0
  if (minutes <= 0) return 'None'
  if (minutes === 1) return '1 minute'
  if (minutes < 60) return `${minutes} minutes`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return `${minutes} minutes (${hours} h${rest ? ` ${rest} min` : ''})`
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
  for (const which of ['setup', 'turnaround'] as const) {
    const value = which === 'setup' ? input.setupMinutes : input.turnaroundMinutes
    const read = parseMinutes(String(value), which)
    if (typeof read === 'string') return read
  }
  return ''
}

// --- US12.1: blackout periods -------------------------------------------------

/**
 * US12.2: Structured reason types for venue unavailability.
 */
export const UNAVAILABILITY_REASON_TYPES = {
  maintenance: 'Maintenance',
  equipment_failure: 'Equipment failure',
  renovation: 'Renovation',
  safety_concern: 'Safety concern',
  other: 'Other',
} as const

export type UnavailabilityReasonType = keyof typeof UNAVAILABILITY_REASON_TYPES

/**
 * A date range a venue cannot be used — maintenance, a closure. Both dates are
 * YYYY-MM-DD and inclusive, so a one-day closure has the same start and end.
 *
 * US12.2: Now includes structured reason type and optional other_reason.
 */
export type UnavailabilityRecord = {
  id: string
  venueId: string
  startDate: string
  endDate: string
  /** US12.2: Structured reason type. */
  reasonType: UnavailabilityReasonType
  /** US12.2: Custom reason when reasonType is 'other', otherwise empty. */
  otherReason: string
  /** US12.2: Number of bookings flagged by this unavailability. Optional for backward compatibility. */
  flaggedBookingsCount?: number
  createdAt: string
}

/** What the Venue Staff form sends. */
export type UnavailabilityInput = {
  startDate: string
  endDate: string
  /** US12.2: Structured reason type. */
  reasonType: UnavailabilityReasonType | ''
  /** US12.2: Custom reason when reasonType is 'other'. */
  otherReason: string
}

export const EMPTY_UNAVAILABILITY: UnavailabilityInput = {
  startDate: '',
  endDate: '',
  reasonType: '',
  otherReason: '',
}

/** The server's cap on a reason. Mirrored so the form can say so before sending. */
export const REASON_MAX = 500

/** A venue's blackout periods, soonest first — the server's order. */
export async function listUnavailability(
  venueId: string,
  session: Session,
): Promise<UnavailabilityRecord[]> {
  const response = await authorizedFetch(`/venues/${venueId}/unavailability`, session.token)
  return (await response.json()) as UnavailabilityRecord[]
}

/** US12.1: Venue Staff mark a venue unavailable for a date range. */
export async function markUnavailable(
  venueId: string,
  input: UnavailabilityInput,
  session: Session,
): Promise<UnavailabilityRecord> {
  try {
    const response = await authorizedFetch(`/venues/${venueId}/unavailability`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    return (await response.json()) as UnavailabilityRecord
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * US12.1/US12.2: validate unavailability input.
 *
 * Both dates are required, the end may not be before the start, a reason type
 * is required, and when "other" is selected, a custom reason must be provided.
 *
 * Returns the first problem as a sentence, or '' when the range is complete.
 * The server checks again; this is so the form can say what is wrong without a
 * round trip. Dates from a date input are YYYY-MM-DD, which sort as text in the
 * same order as on the calendar, so they are compared as strings.
 */
export function validateUnavailability(input: UnavailabilityInput): string {
  if (!input.startDate.trim()) return 'Give the start date.'
  if (!input.endDate.trim()) return 'Give the end date.'
  if (input.endDate < input.startDate) return 'The end date cannot be earlier than the start date.'

  // US12.2: Validate reason type
  if (!input.reasonType) return 'Select a reason for the unavailability.'
  if (!Object.keys(UNAVAILABILITY_REASON_TYPES).includes(input.reasonType)) {
    return 'Select a valid reason type.'
  }

  // US12.2: Validate other_reason when type is "other"
  if (input.reasonType === 'other') {
    const otherReason = input.otherReason.trim()
    if (!otherReason) return 'Give a custom reason when selecting "Other".'
    if (otherReason.length > REASON_MAX) {
      return `Keep the custom reason to ${REASON_MAX} characters or fewer.`
    }
  }

  return ''
}

/**
 * Today as YYYY-MM-DD in the viewer's own time zone.
 *
 * Not `toISOString`, which is UTC: in Singapore that would still be yesterday
 * until 8am, and a closure starting today would read as upcoming all morning.
 */
export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export type RangeTiming = 'current' | 'upcoming' | 'past'

/** Where a range sits relative to `today`, both ends included. */
export function rangeTiming(
  range: { startDate: string; endDate: string },
  today: string,
): RangeTiming {
  if (range.endDate < today) return 'past'
  if (range.startDate > today) return 'upcoming'
  return 'current'
}

/**
 * "2 Nov 2026". Read as a local calendar day rather than through `new Date(iso)`,
 * which takes a bare date as UTC midnight and can show the day before.
 */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return iso
  const [, year, month, day] = match
  return new Date(Number(year), Number(month) - 1, Number(day)).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** "2 Nov 2026 – 6 Nov 2026", or just the day when the range is one day. */
export function formatDateRange(startDate: string, endDate: string): string {
  if (!endDate || startDate === endDate) return formatDate(startDate)
  if (!startDate) return formatDate(endDate)
  return `${formatDate(startDate)} – ${formatDate(endDate)}`
}

/**
 * US12.2: Format the reason for display.
 *
 * Shows the custom text when type is "other", otherwise the human-readable label.
 */
export function formatUnavailabilityReason(
  record: Pick<UnavailabilityRecord, 'reasonType' | 'otherReason'>,
): string {
  if (record.reasonType === 'other') {
    return record.otherReason || 'No reason given'
  }
  return UNAVAILABILITY_REASON_TYPES[record.reasonType] || 'No reason given'
}

// -- US12.3: what is taking up a venue ------------------------------------------

export type AvailabilityKind = 'confirmed' | 'requested' | 'hold' | 'unavailable'

/** AC2: each entry labelled by type. */
export const AVAILABILITY_KIND_LABELS: Record<AvailabilityKind, string> = {
  confirmed: 'Confirmed booking',
  requested: 'Requested booking',
  hold: 'Tentative hold',
  unavailable: 'Unavailable',
}

/**
 * One thing occupying a venue. Fields that do not apply to its kind are empty.
 * Times are "YYYY-MM-DDTHH:MM" in the venue's local time.
 */
export type AvailabilityEntry = {
  kind: AvailabilityKind
  /** A booking's full occupied window, setup and turnaround included; a period's whole days. */
  startsAt: string
  endsAt: string
  bookingId: string
  /** Empty when the viewer may not see which event it is. */
  eventId: string
  eventTitle: string
  /** The booking's own times, without setup and turnaround. */
  eventStartsAt: string
  eventEndsAt: string
  holdExpiresAt: string
  periodId: string
  startDate: string
  endDate: string
  reasonType: UnavailabilityReasonType | ''
  otherReason: string
}

export type VenueAvailability = {
  venueId: string
  /** The range the server used, both days included. */
  from: string
  to: string
  setupMinutes: number
  turnaroundMinutes: number
  entries: AvailabilityEntry[]
}

export type AvailabilityRange = { from: string; to: string }

/**
 * A server time marked as Singapore time, so a browser elsewhere reads it right.
 *
 * Booking times come as naive Singapore local time ("2027-03-03T09:30"), and a
 * browser reads a naive time as its own local time. The formatters then show
 * it in Singapore time, which would move it by the difference anywhere else.
 */
export function asSingaporeTime(iso: string): string {
  return !iso || /(Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}+08:00`
}

/** AC1: the range shown before anyone picks one, today included. */
export const AVAILABILITY_DEFAULT_DAYS = 14
/** The server's cap, mirrored so the form can say so before sending. */
export const AVAILABILITY_MAX_DAYS = 366

/** A YYYY-MM-DD date moved by whole days, worked in UTC so no clock change can shift it. */
export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

/** AC1: the next 14 days. */
export function defaultAvailabilityRange(today: string = todayIso()): AvailabilityRange {
  return { from: today, to: addDays(today, AVAILABILITY_DEFAULT_DAYS - 1) }
}

/** The first problem with a picked range, or '' when it can be asked for. */
export function validateAvailabilityRange({ from, to }: AvailabilityRange): string {
  if (!from) return 'Choose a from date.'
  if (!to) return 'Choose a to date.'
  if (to < from) return 'The to date cannot be earlier than the from date.'
  if (addDays(from, AVAILABILITY_MAX_DAYS - 1) < to) {
    return `Pick a range of ${AVAILABILITY_MAX_DAYS} days or fewer.`
  }
  return ''
}

/** US12.3: everything taking up a venue over a range, in time order. */
export async function getAvailability(
  venueId: string,
  range: AvailabilityRange,
  session: Session,
): Promise<VenueAvailability> {
  const query = new URLSearchParams({ from: range.from, to: range.to })
  try {
    const response = await authorizedFetch(`/venues/${venueId}/availability?${query}`, session.token)
    return (await response.json()) as VenueAvailability
  } catch (error) {
    return asRuleError(error)
  }
}

/**
 * The items a venue lists in one of its free-text fields, as written.
 *
 * The catalogue holds these two ways: plain lists ("Theatre, standing") and
 * Postgres array literals ('{stage,"AV system"}'), left by a seed script that
 * wrote arrays into TEXT columns. The server reads both the same way for
 * US18.1's suitability check (`listed_items`); this copy only offers the
 * booking form its suggestions.
 */
export function listedItems(text: string): string[] {
  const trimmed = text.trim()
  let raw: string[]
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    raw = []
    let current = ''
    let quoted = false
    let escaped = false
    for (const character of trimmed.slice(1, -1)) {
      if (escaped) {
        current += character
        escaped = false
      } else if (character === '\\' && quoted) {
        escaped = true
      } else if (character === '"') {
        quoted = !quoted
      } else if (character === ',' && !quoted) {
        raw.push(current)
        current = ''
      } else {
        current += character
      }
    }
    raw.push(current)
  } else {
    raw = trimmed.split(/[,;\n]/)
  }
  return raw.map((item) => item.trim()).filter(Boolean)
}
