import { describe, expect, it } from 'vitest'
import { displayEventTitle, hasDraftContent, submissionError } from './draftRules'
import { NOT_REQUIRED } from './eventNeeds'

const emptyDraft = {
  title: '',
  purpose: '',
  description: '',
  startsAt: '',
  endsAt: '',
  expectedAttendance: null,
}

describe('hasDraftContent', () => {
  it('rejects whitespace and punctuation without changing the values', () => {
    const draft = { ...emptyDraft, title: '  ', description: '\n---\t' }

    expect(hasDraftContent(draft)).toBe(false)
    expect(draft).toEqual({ ...emptyDraft, title: '  ', description: '\n---\t' })
  })

  it('accepts Unicode letters and numbers in any field', () => {
    expect(hasDraftContent({ ...emptyDraft, description: '活动' })).toBe(true)
    expect(hasDraftContent({ ...emptyDraft, expectedAttendance: 0 })).toBe(true)
  })

  it('counts an answered need as content (US2.1, Sprint 3)', () => {
    expect(hasDraftContent({ ...emptyDraft, preferredLayout: 'Banquet' })).toBe(true)
    expect(hasDraftContent({ ...emptyDraft, registrationNeeds: NOT_REQUIRED })).toBe(true)
    expect(hasDraftContent({ ...emptyDraft, equipmentNeeds: ' ' })).toBe(false)
  })
})

describe('displayEventTitle', () => {
  it('uses a fallback only when the title has no letter or number', () => {
    expect(displayEventTitle('---')).toBe('Untitled event')
    expect(displayEventTitle('  Event  ')).toBe('  Event  ')
  })
})

describe('submissionError — shared by US4.2 submit and US11.1 change requests', () => {
  const TODAY = '2027-01-15'
  const complete = {
    title: 'Faculty Welcome Night',
    purpose: 'Welcome the new intake.',
    description: 'Talks and a campus tour.',
    startsAt: '2027-11-02T18:00',
    endsAt: '2027-11-02T21:00',
    expectedAttendance: '120',
    venueRequirements: 'Stage, Projector',
    preferredLayout: 'Theatre',
    accessibilityNeeds: 'Wheelchair access',
    equipmentNeeds: 'Two wireless microphones',
    registrationNeeds: NOT_REQUIRED,
  }

  it('accepts a complete event', () => {
    expect(submissionError(complete, TODAY)).toBeNull()
  })

  it.each([
    [{ title: '  ' }, 'Give the event a title.'],
    [{ startsAt: '' }, 'Give the event a date.'],
    [{ endsAt: ' ' }, 'Give the event an end date.'],
    [{ endsAt: '2027-11-02T18:00' }, 'The end date must be after the start date.'],
    [{ endsAt: '2027-11-02T17:59' }, 'The end date must be after the start date.'],
    [{ purpose: '' }, 'Give the event a purpose.'],
    [{ expectedAttendance: ' ' }, 'Give the expected attendance.'],
    [{ expectedAttendance: '12.5' }, 'Enter a whole number of people.'],
    [{ expectedAttendance: '-1' }, 'Enter a whole number of people.'],
    [{ expectedAttendance: 'many' }, 'Enter a whole number of people.'],
    [{ expectedAttendance: '0' }, 'Expected attendance must be at least 1.'],
    [{ expectedAttendance: '2147483648' }, 'Expected attendance must be 2,147,483,647 or fewer.'],
    [
      { startsAt: '2027-01-14T23:59', endsAt: '2027-01-15T01:00' },
      'The start date cannot be in the past.',
    ],
    // US2.1 (Sprint 3): the customer's additional mandatory fields.
    [{ description: '\t\n ' }, 'Give the event a description.'],
    [{ venueRequirements: '' }, 'Choose the venue requirements, or None / Not required.'],
    [{ preferredLayout: '' }, 'Choose a preferred layout, or None / Not required.'],
    [{ accessibilityNeeds: ' ' }, 'Choose the accessibility needs, or None / Not required.'],
    [{ equipmentNeeds: '' }, 'Describe the equipment needs, or choose None / Not required.'],
    [
      { registrationNeeds: '' },
      'Describe the registration needs, or choose None / Not required.',
    ],
  ])('refuses %o', (change, message) => {
    expect(submissionError({ ...complete, ...change }, TODAY)).toBe(message)
  })

  it.each([
    [{ expectedAttendance: '1' }],
    [{ expectedAttendance: ' 7 ' }],
    [{ expectedAttendance: '2147483647' }],
    [{ endsAt: '2027-11-02T18:01' }],
    [{ startsAt: '2027-01-15T00:00', endsAt: '2027-01-15T01:00' }],
    [
      {
        venueRequirements: NOT_REQUIRED,
        preferredLayout: NOT_REQUIRED,
        accessibilityNeeds: NOT_REQUIRED,
        equipmentNeeds: NOT_REQUIRED,
      },
    ],
  ])('accepts the boundary %o', (change) => {
    expect(submissionError({ ...complete, ...change }, TODAY)).toBeNull()
  })

  it('reports the first problem in form order', () => {
    expect(submissionError({ ...complete, title: '', purpose: '' }, TODAY)).toBe(
      'Give the event a title.',
    )
    expect(
      submissionError({ ...complete, description: '', venueRequirements: '' }, TODAY),
    ).toBe('Give the event a description.')
    expect(
      submissionError({ ...complete, preferredLayout: '', registrationNeeds: '' }, TODAY),
    ).toBe('Choose a preferred layout, or None / Not required.')
  })
})
