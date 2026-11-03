/**
 * Venue Staff's tentative holds card — US14.3.
 *
 * The rules (who may hold, for which events, the expiry) are the server's and
 * are tested in backend/tests/test_venue_holds.py. This card's job is listing
 * the venue's holds, expired ones marked, and placing a new one.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VenueHolds from './VenueHolds'
import {
  listHoldableEvents,
  listHolds,
  placeHold,
  type HoldableEvent,
  type HoldRecord,
} from '../holdsStore'
import { buildSession } from '../test/sessions'

vi.mock('../holdsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../holdsStore')>()),
  listHolds: vi.fn(),
  listHoldableEvents: vi.fn(),
  placeHold: vi.fn(),
}))

const listHoldsMock = vi.mocked(listHolds)
const listEventsMock = vi.mocked(listHoldableEvents)
const placeHoldMock = vi.mocked(placeHold)

const staff = buildSession({ role: 'Venue Staff', id: '4', name: 'Sam' })
const NOW = '2027-10-01T09:00'

const OPEN_DAY: HoldableEvent = {
  id: '900',
  title: 'Open Day',
  status: 'Approved',
  coordinatorName: 'Priya',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
}

function hold(overrides: Partial<HoldRecord> = {}): HoldRecord {
  return {
    id: '101',
    eventId: '900',
    eventTitle: 'Open Day',
    venueId: '1',
    venueName: 'Great Hall',
    startsAt: '2027-11-02T09:00:00',
    endsAt: '2027-11-02T17:00:00',
    status: 'Held',
    requestedAt: '2027-10-01T09:00:00',
    headcount: 300,
    requiredLayout: '',
    requiredFacilities: [],
    accessibilityNeeds: [],
    cancellation: null,
    holdExpiresAt: '2027-10-08T17:00:00',
    holdExpired: false,
    heldByName: 'Sam',
    ...overrides,
  }
}

beforeEach(() => {
  listHoldsMock.mockResolvedValue([])
  listEventsMock.mockResolvedValue([OPEN_DAY])
})

afterEach(() => {
  vi.resetAllMocks()
})

function renderCard() {
  return render(<VenueHolds venueId="1" session={staff} now={NOW} />)
}

it('TC-HF14 places a hold and lists it', async () => {
  placeHoldMock.mockResolvedValue(hold())
  renderCard()
  await userEvent.selectOptions(
    await screen.findByLabelText('Event'),
    await screen.findByRole('option', { name: 'Open Day — Priya' }),
  )
  await userEvent.type(screen.getByLabelText('Hold expires'), '2027-10-08T17:00')
  await userEvent.click(screen.getByRole('button', { name: 'Place hold' }))

  expect(placeHoldMock).toHaveBeenCalledWith(
    '1',
    {
      eventId: '900',
      startsAt: '2027-11-02T09:00',
      endsAt: '2027-11-02T17:00',
      expiresAt: '2027-10-08T17:00',
    },
    staff,
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Held for Open Day until')
  expect(
    within(screen.getByRole('list', { name: 'Holds on this venue' })).getByText('Open Day'),
  ).toBeInTheDocument()
})
