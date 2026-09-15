import { describe, expect, it } from 'vitest'
import { displayEventTitle, hasDraftContent } from './draftRules'

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
})

describe('displayEventTitle', () => {
  it('uses a fallback only when the title has no letter or number', () => {
    expect(displayEventTitle('---')).toBe('Untitled event')
    expect(displayEventTitle('  Event  ')).toBe('  Event  ')
  })
})
