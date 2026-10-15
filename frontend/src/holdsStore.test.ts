/** US14.3: the hold form's own check, which mirrors the server's rules. */

import { describe, expect, it } from 'vitest'
import { validateHold, type HoldInput } from './holdsStore'

const NOW = '2027-10-01T09:00'

const HOLD: HoldInput = {
  eventId: '900',
  startsAt: '2027-11-02T09:00',
  endsAt: '2027-11-02T17:00',
  expiresAt: '2027-10-08T17:00',
}

describe('validateHold (US14.3)', () => {
  it('TC-HF08 accepts a complete hold', () => {
    expect(validateHold(HOLD, NOW)).toBe('')
  })

  it.each([
    [{ eventId: '' }, 'Choose the event to hold this venue for.'],
    [{ startsAt: '' }, 'Give the booking a start time.'],
    [{ endsAt: '' }, 'Give the booking an end time.'],
    [{ endsAt: '2027-11-02T09:00' }, 'The booking must end after it starts.'],
    [{ expiresAt: '' }, 'Give the hold an expiry date and time.'],
    [{ expiresAt: '2027-09-30T09:00' }, 'The hold must expire in the future.'],
    [{ expiresAt: NOW }, 'The hold must expire in the future.'],
    [{ expiresAt: '2027-11-02T09:01' }, 'The hold must expire no later than the booking starts.'],
  ])('TC-HF09 refuses %o', (overrides, message) => {
    expect(validateHold({ ...HOLD, ...overrides }, NOW)).toBe(message)
  })

  it('TC-HF10 accepts expiry a minute from now and exactly at the start', () => {
    expect(validateHold({ ...HOLD, expiresAt: '2027-10-01T09:01' }, NOW)).toBe('')
    expect(validateHold({ ...HOLD, expiresAt: HOLD.startsAt }, NOW)).toBe('')
  })
})
