/**
 * The unavailable-dates card on a venue record — US12.1.
 *
 * Two halves, as in the story: a Coordinator reads the blackout periods when
 * viewing the venue, and Venue Staff record one by giving a start and an end
 * that is not before it. Every test pins `today` so Now/Upcoming/Past do not
 * depend on the day the suite runs.
 */

import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VenueUnavailability from './VenueUnavailability'
import {
  formatDateRange,
  listUnavailability,
  markUnavailable,
  type UnavailabilityRecord,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listUnavailability: vi.fn(),
  markUnavailable: vi.fn(),
}))

const listMock = vi.mocked(listUnavailability)
const markMock = vi.mocked(markUnavailable)

beforeEach(() => {
  listMock.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })
const venueStaff = buildSession({ role: 'Venue Staff', id: '3', name: 'Sam' })

const TODAY = '2026-11-04'

function range(overrides: Partial<UnavailabilityRecord> = {}): UnavailabilityRecord {
  return {
    id: '101',
    venueId: '1',
    startDate: '2026-11-02',
    endDate: '2026-11-06',
    reasonType: 'other',
    otherReason: 'Annual maintenance',
    createdAt: '2026-10-01T09:00:00',
    ...overrides,
  }
}

function renderFor(session = coordinator, mayMark = false) {
  return render(
    <VenueUnavailability venueId="1" session={session} mayMark={mayMark} today={TODAY} />,
  )
}

function renderForStaff() {
  return renderFor(venueStaff, true)
}

async function fill(start: string, end: string, reasonType = 'maintenance', otherReason = '') {
  const user = userEvent.setup()
  if (start) await user.type(screen.getByLabelText('Start date'), start)
  if (end) await user.type(screen.getByLabelText('End date'), end)
  // Only select reason if a value is provided (allows testing validation when reasonType is empty)
  if (reasonType) await user.selectOptions(screen.getByLabelText('Reason'), reasonType)
  if (reasonType === 'other' && otherReason) {
    await user.type(screen.getByLabelText('Custom reason'), otherReason)
  }
  await user.click(screen.getByRole('button', { name: 'Mark unavailable' }))
}

function upcomingList() {
  return screen.getByRole('list', { name: 'Current and upcoming unavailable dates' })
}

it('records the range and adds it to the list', async () => {
  markMock.mockResolvedValue(range({ id: '200', reasonType: 'other', otherReason: 'Roof repair' }))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06', 'other', 'Roof repair')

  expect(markMock).toHaveBeenCalledWith(
    '1',
    { startDate: '2026-11-02', endDate: '2026-11-06', reasonType: 'other', otherReason: 'Roof repair' },
    venueStaff,
  )
  expect(await within(upcomingList()).findByText('Roof repair')).toBeInTheDocument()
})

it('says the range was saved and clears the form for the next one', async () => {
  markMock.mockResolvedValue(range({ flaggedBookingsCount: 2 }))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06')

  expect(await screen.findByText(/^Marked unavailable:/)).toHaveTextContent(
    formatDateRange('2026-11-02', '2026-11-06'),
  )
  expect(screen.getByLabelText('Start date')).toHaveValue('')
  expect(screen.getByLabelText('End date')).toHaveValue('')
  expect(screen.getByText(/^Marked unavailable:/)).toHaveTextContent(
    '2 bookings flagged as needing replacement.',
  )
})
