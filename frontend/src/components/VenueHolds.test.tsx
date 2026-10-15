/**
 * Venue Staff's tentative holds card — US14.3.
 *
 * The rules (who may hold, for which events, the expiry) are the server's and
 * are tested in backend/tests/test_venue_holds.py. This card's job is listing
 * the venue's holds, expired ones marked, and placing a new one.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
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
import { EventRuleError } from '../eventsStore'
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

it('TC-HF11 lists the venue holds and marks expired ones', async () => {
  listHoldsMock.mockResolvedValue([
    hold(),
    hold({ id: '102', eventTitle: 'Careers Fair', holdExpired: true }),
  ])
  renderCard()

  const rows = within(
    await screen.findByRole('list', { name: 'Holds on this venue' }),
  ).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Open Day')
  expect(rows[0]).toHaveTextContent('Held')
  expect(rows[0]).toHaveTextContent('by Sam')
  expect(rows[1]).toHaveTextContent('Careers Fair')
  expect(rows[1]).toHaveTextContent('Expired')
  expect(listHoldsMock).toHaveBeenCalledWith('1', staff)
})

it('TC-HF12 says when there are no holds', async () => {
  renderCard()
  expect(await screen.findByText('No holds on this venue.')).toBeInTheDocument()
})

it('TC-HF13 choosing an event starts the times at the event times', async () => {
  renderCard()
  await userEvent.selectOptions(
    await screen.findByLabelText('Event'),
    await screen.findByRole('option', { name: 'Open Day — Priya' }),
  )

  expect(screen.getByLabelText('Starts')).toHaveValue('2027-11-02T09:00')
  expect(screen.getByLabelText('Ends')).toHaveValue('2027-11-02T17:00')
})

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

it('TC-HF15 requires an expiry before asking the server', async () => {
  renderCard()
  await userEvent.selectOptions(
    await screen.findByLabelText('Event'),
    await screen.findByRole('option', { name: 'Open Day — Priya' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Place hold' }))

  expect(screen.getByRole('alert')).toHaveTextContent('Give the hold an expiry date and time.')
  expect(placeHoldMock).not.toHaveBeenCalled()
})

it('TC-HF16 shows the server refusal', async () => {
  placeHoldMock.mockRejectedValue(
    new EventRuleError('Assign a Coordinator to this event before holding a venue for it.'),
  )
  renderCard()
  await userEvent.selectOptions(
    await screen.findByLabelText('Event'),
    await screen.findByRole('option', { name: 'Open Day — Priya' }),
  )
  await userEvent.type(screen.getByLabelText('Hold expires'), '2027-10-08T17:00')
  await userEvent.click(screen.getByRole('button', { name: 'Place hold' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Assign a Coordinator')
})

it('TC-HF17 explains when no event can take a hold', async () => {
  listEventsMock.mockResolvedValue([])
  renderCard()
  expect(await screen.findByText(/No events can take a hold right now/)).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Place hold' })).toBeDisabled())
})
