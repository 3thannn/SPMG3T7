/**
 * US2.1 (Sprint 3): the fixed lists and rules behind the event needs fields.
 *
 * The server (backend/app/event_needs.py) is the enforcement point and refuses
 * any value off its lists. That the two lists match is asserted on the backend
 * side (tests/test_event_needs.py), which can read this file without loosening
 * Vite's file-serving guard.
 */

import { describe, expect, it } from 'vitest'
import {
  ACCESSIBILITY_OPTIONS,
  FACILITY_OPTIONS,
  LAYOUT_OPTIONS,
  MISSING_MESSAGES,
  NEED_KEYS,
  NO_NEEDS,
  NOT_REQUIRED,
  firstMissingNeed,
  listedNeeds,
  missingNeeds,
  needsOf,
  toggleNeed,
} from './eventNeeds'
import { ANSWERED_NEEDS } from './test/eventNeeds'

describe('the fixed lists', () => {
  it.each([
    ['layouts', LAYOUT_OPTIONS],
    ['facilities', FACILITY_OPTIONS],
    ['accessibility needs', ACCESSIBILITY_OPTIONS],
  ] as const)('%s: no option contains the separator, repeats, or is the none answer', (_, options) => {
    expect(options.every((option) => !option.includes(','))).toBe(true)
    expect(new Set(options).size).toBe(options.length)
    expect(options).not.toContain(NOT_REQUIRED)
  })

  it('use the venue catalogue’s words', () => {
    expect(LAYOUT_OPTIONS).toEqual(expect.arrayContaining(['Theatre', 'Classroom', 'Banquet']))
    expect(FACILITY_OPTIONS).toEqual(expect.arrayContaining(['Stage', 'Projector', 'AV system']))
    expect(ACCESSIBILITY_OPTIONS).toEqual(
      expect.arrayContaining(['Wheelchair access', 'Hearing loop']),
    )
  })

  it('name the five needs in form order', () => {
    expect(NEED_KEYS).toEqual([
      'venueRequirements',
      'preferredLayout',
      'accessibilityNeeds',
      'equipmentNeeds',
      'registrationNeeds',
    ])
  })
})

describe('needsOf', () => {
  it('reads every answer an event has', () => {
    expect(needsOf({ ...ANSWERED_NEEDS })).toEqual(ANSWERED_NEEDS)
  })

  it('reads an answer the payload lacks as unanswered', () => {
    expect(needsOf({})).toEqual(NO_NEEDS)
    expect(needsOf({ preferredLayout: 'Banquet' })).toEqual({
      ...NO_NEEDS,
      preferredLayout: 'Banquet',
    })
  })

  it('keeps only the needs, not the rest of the record', () => {
    expect(Object.keys(needsOf({ ...ANSWERED_NEEDS, title: 'x' } as never))).toEqual(NEED_KEYS)
  })
})

describe('listedNeeds', () => {
  it.each([
    ['', []],
    ['  ', []],
    ['Stage', ['Stage']],
    ['Stage, Projector', ['Stage', 'Projector']],
    [' Stage ,, Projector ,', ['Stage', 'Projector']],
  ])('reads %o', (value, expected) => {
    expect(listedNeeds(value)).toEqual(expected)
  })
})

describe('toggleNeed', () => {
  const options = FACILITY_OPTIONS

  it('adds an option', () => {
    expect(toggleNeed('', 'Projector', true, options)).toBe('Projector')
  })

  it('keeps the list order whatever order things were ticked in', () => {
    expect(toggleNeed('Projector', 'Stage', true, options)).toBe('Stage, Projector')
  })

  it('removes an option', () => {
    expect(toggleNeed('Stage, Projector', 'Stage', false, options)).toBe('Projector')
  })

  it('reads as unanswered once the last option is removed', () => {
    expect(toggleNeed('Stage', 'Stage', false, options)).toBe('')
  })

  it('ticking None / Not required clears the options', () => {
    expect(toggleNeed('Stage, Projector', NOT_REQUIRED, true, options)).toBe(NOT_REQUIRED)
  })

  it('unticking None / Not required leaves it unanswered', () => {
    expect(toggleNeed(NOT_REQUIRED, NOT_REQUIRED, false, options)).toBe('')
  })

  it('ticking an option replaces None / Not required', () => {
    expect(toggleNeed(NOT_REQUIRED, 'Lectern', true, options)).toBe('Lectern')
  })

  it('drops a value that is not on the list', () => {
    expect(toggleNeed('Helipad', 'Stage', true, options)).toBe('Stage')
  })
})

describe('missingNeeds and firstMissingNeed', () => {
  it('finds nothing missing once every need is answered', () => {
    expect(missingNeeds(ANSWERED_NEEDS)).toEqual({})
    expect(firstMissingNeed(ANSWERED_NEEDS)).toBeNull()
  })

  it('counts None / Not required as an answer', () => {
    const notRequired = Object.fromEntries(NEED_KEYS.map((key) => [key, NOT_REQUIRED]))
    expect(missingNeeds(needsOf(notRequired))).toEqual({})
  })

  it('names every unanswered need, blank or whitespace', () => {
    expect(missingNeeds({ ...NO_NEEDS, equipmentNeeds: '  ' })).toEqual(MISSING_MESSAGES)
  })

  it.each(NEED_KEYS)('reports %s on its own', (key) => {
    const needs = { ...ANSWERED_NEEDS, [key]: '' }
    expect(missingNeeds(needs)).toEqual({ [key]: MISSING_MESSAGES[key] })
    expect(firstMissingNeed(needs)).toBe(MISSING_MESSAGES[key])
  })

  it('reports the first unanswered need in form order', () => {
    expect(firstMissingNeed(NO_NEEDS)).toBe(
      'Choose the venue requirements, or None / Not required.',
    )
    expect(
      firstMissingNeed({ ...ANSWERED_NEEDS, accessibilityNeeds: '', registrationNeeds: '' }),
    ).toBe('Choose the accessibility needs, or None / Not required.')
  })
})
