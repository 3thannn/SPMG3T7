/**
 * What an event request needs — US2.1, reopened in Sprint 3.
 *
 * The customer made five more answers mandatory on submit: venue requirements,
 * preferred layout, accessibility needs, equipment needs and registration
 * needs. Layout, facilities and accessibility are picked from fixed lists in
 * the venue catalogue's own words (US9.1a); equipment and registration needs
 * are described in words. Any of the five can be answered "None / Not
 * required" instead, so a field that does not apply is answered, not skipped.
 *
 * This mirrors backend/app/event_needs.py, which is the enforcement point. The
 * lists must stay identical: the server refuses a value that is not on them.
 *
 * Values travel as text, the way the catalogue stores its lists: a
 * multi-choice answer is its options joined with ", ". Empty means "not
 * answered yet", which only a draft may leave (US2.2).
 */

export const NOT_REQUIRED = 'None / Not required'

const SEPARATOR = ', '

export const LAYOUT_OPTIONS = [
  'Theatre',
  'Classroom',
  'Boardroom',
  'Banquet',
  'Cabaret',
  'Standing',
  'Reception',
  'Breakout tables',
  'Workshop',
  'Exhibition',
  'Concert',
  'Fixed tiered seating',
] as const

export const FACILITY_OPTIONS = [
  'Stage',
  'AV system',
  'PA system',
  'Sound system',
  'Projector',
  'Screen',
  'Whiteboard',
  'Video conferencing',
  'Recording equipment',
  'Lectern',
  'Interpretation booth',
  'Catering area',
  'Kitchenette',
  'Green room',
  'Power outlets',
  'Outdoor seating',
] as const

export const ACCESSIBILITY_OPTIONS = [
  'Wheelchair access',
  'Step-free access',
  'Accessible toilets',
  'Lift',
  'Hearing loop',
  'Reserved seating',
] as const

/** A cap for readability, matching the server's. */
export const FREE_TEXT_MAX = 1000

export type EventNeeds = {
  venueRequirements: string
  preferredLayout: string
  accessibilityNeeds: string
  equipmentNeeds: string
  registrationNeeds: string
}

export const NO_NEEDS: EventNeeds = {
  venueRequirements: '',
  preferredLayout: '',
  accessibilityNeeds: '',
  equipmentNeeds: '',
  registrationNeeds: '',
}

/** In the order the form shows them, which is also the order errors are reported. */
export const NEED_KEYS = Object.keys(NO_NEEDS) as (keyof EventNeeds)[]

/** What each field says when it is left unanswered at submission. */
export const MISSING_MESSAGES: Record<keyof EventNeeds, string> = {
  venueRequirements: `Choose the venue requirements, or ${NOT_REQUIRED}.`,
  preferredLayout: `Choose a preferred layout, or ${NOT_REQUIRED}.`,
  accessibilityNeeds: `Choose the accessibility needs, or ${NOT_REQUIRED}.`,
  equipmentNeeds: `Describe the equipment needs, or choose ${NOT_REQUIRED}.`,
  registrationNeeds: `Describe the registration needs, or choose ${NOT_REQUIRED}.`,
}

/** An event's answers, with any the payload lacks read as unanswered. */
export function needsOf(source: Partial<EventNeeds>): EventNeeds {
  return {
    venueRequirements: source.venueRequirements ?? '',
    preferredLayout: source.preferredLayout ?? '',
    accessibilityNeeds: source.accessibilityNeeds ?? '',
    equipmentNeeds: source.equipmentNeeds ?? '',
    registrationNeeds: source.registrationNeeds ?? '',
  }
}

/** The options a multi-choice answer holds. */
export function listedNeeds(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

/**
 * The answer after ticking or unticking one checkbox.
 *
 * "None / Not required" and the real options exclude each other: ticking one
 * clears the other. The result is in list order whatever order things were
 * ticked in, so the same choices always read the same.
 */
export function toggleNeed(
  value: string,
  option: string,
  checked: boolean,
  options: readonly string[],
): string {
  if (option === NOT_REQUIRED) return checked ? NOT_REQUIRED : ''
  const chosen = new Set(listedNeeds(value).filter((item) => item !== NOT_REQUIRED))
  if (checked) chosen.add(option)
  else chosen.delete(option)
  return options.filter((item) => chosen.has(item)).join(SEPARATOR)
}

/** Every field a submission has left unanswered, keyed by field. */
export function missingNeeds(needs: EventNeeds): Partial<Record<keyof EventNeeds, string>> {
  const errors: Partial<Record<keyof EventNeeds, string>> = {}
  for (const key of NEED_KEYS) {
    if (!needs[key].trim()) errors[key] = MISSING_MESSAGES[key]
  }
  return errors
}

/** The first unanswered field's message, in form order, or null. */
export function firstMissingNeed(needs: EventNeeds): string | null {
  return Object.values(missingNeeds(needs))[0] ?? null
}
