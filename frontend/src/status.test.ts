import { describe, expect, it } from 'vitest'
import {
  EVENT_STATUSES,
} from './status'



describe('US4.1 — the fixed label set', () => {
  it('carries exactly the agreed statuses, in order', () => {
    expect(EVENT_STATUSES).toEqual([
      'Draft',
      'Submitted',
      'Under Review',
      'Approved',
      'Planning',
      // US4.4: added between Planning and Confirmed.
      'Pending Safety Check',
      'Confirmed',
      'Completed',
      'Cancelled',
      'Rejected',
    ])
  })
})
