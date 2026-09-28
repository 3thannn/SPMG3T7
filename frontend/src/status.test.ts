import { describe, expect, it } from 'vitest'
import {
  EVENT_STATUSES,
  canViewStatus,
  checkSubmit,
  statusNoteKind,
  type EventStatus,
} from './status'

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

describe('status audit notes', () => {
  it('distinguishes rejection reasons from clarification requests', () => {
    const base = { from: 'Under Review' as EventStatus, at: 'now', byId: '2', byName: 'Priya' }
    expect(statusNoteKind({ ...base, to: 'Rejected', notes: 'No capacity.' })).toBe('rejection')
    expect(statusNoteKind({ ...base, to: 'Under Review', notes: 'Please clarify.' })).toBe(
      'clarification',
    )
    expect(statusNoteKind({ ...base, to: 'Approved', notes: '' })).toBeNull()
  })
})

describe('US4.1 — who can see a status', () => {
  it('shows an Organiser the events they own', () => {
    expect(canViewStatus('Event Organiser', 'user_1', owned)).toBe(true)
  })

  it('hides another Organiser’s event', () => {
    expect(canViewStatus('Event Organiser', 'user_2', owned)).toBe(false)
  })

  it('hides Draft events from Coordinators', () => {
    expect(canViewStatus('Event Coordinator', 'anyone', owned)).toBe(false)
  })

  it.each(['Submitted', 'Under Review', 'Approved'] as EventStatus[])(
    'shows a Coordinator an event after submission when it is %s',
    (status) => {
      expect(canViewStatus('Event Coordinator', 'anyone', { ...owned, status })).toBe(true)
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
