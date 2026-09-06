import { describe, expect, it } from 'vitest'
import { EVENT_STATUSES, canViewStatus, checkSubmit, type EventStatus } from './status'

const owned = { status: 'Draft' as EventStatus, organiserId: 'user_1' }

describe('US4.1 — the fixed label set', () => {
  it('carries exactly the nine agreed statuses, in order', () => {
    expect(EVENT_STATUSES).toEqual([
      'Draft',
      'Submitted',
      'Under Review',
      'Approved',
      'Planning',
      'Confirmed',
      'Completed',
      'Cancelled',
      'Rejected',
    ])
  })
})

describe('US4.1 — who can see a status', () => {
  it('shows an Organiser the events they own', () => {
    expect(canViewStatus('Organiser', 'user_1', owned)).toBe(true)
  })

  it('hides another Organiser’s event', () => {
    expect(canViewStatus('Organiser', 'user_2', owned)).toBe(false)
  })

  it('shows any Coordinator every event, per the Sprint 1 scope', () => {
    expect(canViewStatus('Coordinator', 'anyone', owned)).toBe(true)
  })

  it.each(['Venue Staff', 'Technical Support', 'Attendee'] as const)(
    'keeps %s out of scope for Sprint 1',
    (role) => {
      expect(canViewStatus(role, 'user_1', owned)).toBe(false)
    },
  )
})

describe('US4.2 — submitting exactly once', () => {
  it('allows the owning Organiser to submit a Draft', () => {
    expect(checkSubmit(owned, 'user_1')).toEqual({ allowed: true })
  })

  it('refuses a second submit on an already-submitted event', () => {
    const submitted = { status: 'Submitted' as EventStatus, organiserId: 'user_1' }

    expect(checkSubmit(submitted, 'user_1')).toEqual({
      allowed: false,
      reason: 'already-submitted',
    })
  })

  it('refuses anyone who does not own the event', () => {
    expect(checkSubmit(owned, 'user_2')).toEqual({ allowed: false, reason: 'not-owner' })
  })

  it('refuses statuses beyond Draft, which are out of Sprint 1 scope', () => {
    const approved = { status: 'Approved' as EventStatus, organiserId: 'user_1' }

    expect(checkSubmit(approved, 'user_1')).toEqual({ allowed: false, reason: 'not-draft' })
  })
})
