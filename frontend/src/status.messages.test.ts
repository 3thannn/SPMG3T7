/** The refusal sentences and visibility rules status.test.ts does not reach. */

import { describe, expect, it } from 'vitest'
import {
  bookingRefusalMessage,
  canViewStatus,
  checkBooking,
  clarificationRefusalMessage,
  isClarificationRequest,
  submitRefusalMessage,
  type EventStatus,
} from './status'

describe('US8.6 — the Coordinator Lead sees every event but drafts', () => {
  it.each([
    ['Submitted', true],
    ['Draft', false],
  ] as const)('%s: %s', (status, visible) => {
    expect(canViewStatus('Event Coordinator Lead', '3', { organiserId: '1', status })).toBe(
      visible,
    )
  })
})

describe('US4.2 — why an event cannot be submitted', () => {
  it.each([
    [
      'already-submitted',
      'This event has already been submitted. An event can only be submitted once.',
    ],
    ['not-owner', 'Only the Organiser who owns this event can submit it.'],
    ['not-draft', 'Only a Draft event can be submitted.'],
  ] as const)('%s', (reason, sentence) => {
    expect(submitRefusalMessage(reason)).toBe(sentence)
  })
})

describe('refusals for an event that has not been submitted', () => {
  it('US7.3: there is nothing to review', () => {
    expect(clarificationRefusalMessage('not-yet-submitted')).toBe(
      'This event has not been submitted yet, so there is nothing to review.',
    )
  })

  it('US14.1: a draft cannot have venues requested', () => {
    const check = checkBooking({ status: 'Draft' as EventStatus })

    expect(check).toEqual({ allowed: false, reason: 'not-yet-submitted' })
    expect(bookingRefusalMessage('not-yet-submitted')).toBe(
      'This event has not been submitted yet, so no venues can be requested for it.',
    )
  })
})

describe('US7.3 — spotting a clarification request in the history', () => {
  const base = { from: 'Submitted' as EventStatus, at: 'now', byId: '2', byName: 'Priya' }

  it('is a move to Under Review with a question', () => {
    expect(
      isClarificationRequest({ ...base, to: 'Under Review', notes: 'Which room layout?' }),
    ).toBe(true)
  })

  it('is not a decision with a reason', () => {
    expect(isClarificationRequest({ ...base, to: 'Rejected', notes: 'No budget.' })).toBe(false)
  })
})
