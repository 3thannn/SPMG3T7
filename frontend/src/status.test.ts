import { describe, expect, it } from 'vitest'
import {
  EVENT_STATUSES,
  REQUESTABLE,
  canViewStatus,
  changeRequestRefusalMessage,
  checkChangeRequest,
  checkSubmit,
  statusNoteKind,
  statusNoteLabel,
  type ChangeRequestRefusal,
  type EventStatus,
  type StatusNoteKind,
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

describe('US11.1 — change request notes in the history', () => {
  const base = { from: 'Submitted' as EventStatus, to: 'Under Review' as EventStatus, at: 'now' }

  it('reads a change-request note by its kind, not by its status', () => {
    expect(
      statusNoteKind({ ...base, byId: '1', byName: 'Dylan', notes: 'Note.', kind: 'change-request' }),
    ).toBe('change-request')
  })

  it('falls back to the US7.3/US7.1 reading when the kind is empty', () => {
    expect(statusNoteKind({ ...base, byId: '2', byName: 'Priya', notes: 'Why?', kind: '' })).toBe(
      'clarification',
    )
  })

  it('ignores a kind on an entry with no note', () => {
    expect(
      statusNoteKind({ ...base, byId: '1', byName: 'Dylan', notes: ' ', kind: 'change-request' }),
    ).toBeNull()
  })

  it.each([
    ['clarification', 'Requested by Coordinator'],
    ['rejection', 'Rejection reason'],
    ['change-request', 'Change requested by Organiser'],
  ] as [StatusNoteKind, string][])('labels a %s note "%s"', (kind, label) => {
    expect(statusNoteLabel(kind)).toBe(label)
  })
})

describe('US11.1 — who may request changes, and when', () => {
  const event = (status: EventStatus, changeRequested?: boolean) => ({
    status,
    organiserId: 'user_1',
    changeRequested,
  })

  it('allows requests through Planning', () => {
    expect(REQUESTABLE).toEqual(['Submitted', 'Under Review', 'Approved', 'Planning'])
  })

  it.each(['Submitted', 'Under Review', 'Approved', 'Planning'] as EventStatus[])('allows the owner on %s', (status) => {
    expect(checkChangeRequest(event(status), 'user_1')).toEqual({ allowed: true })
    expect(checkChangeRequest(event(status, false), 'user_1')).toEqual({ allowed: true })
  })

  it('refuses someone else first, whatever the state', () => {
    expect(checkChangeRequest(event('Draft', true), 'user_2')).toEqual({
      allowed: false,
      reason: 'not-owner',
    })
  })

  it('sends a Draft back to being edited directly', () => {
    expect(checkChangeRequest(event('Draft'), 'user_1')).toEqual({
      allowed: false,
      reason: 'not-submitted',
    })
  })

  it.each(['Rejected', 'Confirmed', 'Completed', 'Cancelled'] as EventStatus[])(
    'refuses a decided event (%s)',
    (status) => {
      expect(checkChangeRequest(event(status), 'user_1')).toEqual({
        allowed: false,
        reason: 'already-decided',
      })
    },
  )

  it('allows one request at a time', () => {
    expect(checkChangeRequest(event('Under Review', true), 'user_1')).toEqual({
      allowed: false,
      reason: 'already-pending',
    })
  })

  it.each([
    ['not-owner', 'Only the Organiser who owns this event can request changes to it.'],
    ['not-submitted', 'This event is still a Draft. Edit it directly, then submit it.'],
    [
      'already-decided',
      'This event has already been decided, so changes can no longer be requested.',
    ],
    [
      'already-pending',
      "A change request for this event is already awaiting the Coordinator's review.",
    ],
  ] as [ChangeRequestRefusal, string][])('explains %s as the server does', (reason, message) => {
    expect(changeRequestRefusalMessage(reason)).toBe(message)
  })
})
