/**
 * Venue Staff's tentative holds card — US14.3 and US14.6.
 *
 * The rules (who may change a hold, the expiry) are the server's and are
 * tested in backend/tests/test_venue_holds.py. This card's job is listing the
 * venue's holds, expired ones marked, and changing a hold's expiry or
 * releasing it.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VenueHolds from './VenueHolds'
import { listHolds, releaseHold, updateHold, type HoldRecord } from '../holdsStore'
import { EventRuleError } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../holdsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../holdsStore')>()),
  listHolds: vi.fn(),
  updateHold: vi.fn(),
  releaseHold: vi.fn(),
}))

const listHoldsMock = vi.mocked(listHolds)
const updateHoldMock = vi.mocked(updateHold)
const releaseHoldMock = vi.mocked(releaseHold)

const staff = buildSession({ role: 'Venue Staff', id: '4', name: 'Sam' })
const NOW = '2027-10-01T09:00'

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
  listHoldsMock.mockResolvedValue([hold()])
})

afterEach(() => {
  vi.resetAllMocks()
})

function renderCard() {
  return render(<VenueHolds venueId="1" session={staff} now={NOW} />)
}

it('TC-HF14 lists the holds, with who approved them and until when', async () => {
  renderCard()
  const list = await screen.findByRole('list', { name: 'Holds on this venue' })
  expect(within(list).getByText('Open Day')).toBeInTheDocument()
  expect(within(list).getByText(/approved by Sam/)).toBeInTheDocument()
})

it('TC-HF15 changes a hold expiry and says the Coordinator was told', async () => {
  updateHoldMock.mockResolvedValue(hold({ holdExpiresAt: '2027-10-15T12:00:00' }))
  renderCard()
  await userEvent.click(
    await screen.findByRole('button', { name: 'Change the expiry of the hold for Open Day' }),
  )
  const input = screen.getByLabelText('New expiry')
  await userEvent.clear(input)
  await userEvent.type(input, '2027-10-15T12:00')
  await userEvent.click(screen.getByRole('button', { name: 'Save expiry' }))

  expect(updateHoldMock).toHaveBeenCalledWith('101', '2027-10-15T12:00', staff)
  expect(await screen.findByRole('status')).toHaveTextContent('Its Coordinator has been told.')
})

it('TC-HF16 refuses an expiry after the booking starts without asking the server', async () => {
  renderCard()
  await userEvent.click(
    await screen.findByRole('button', { name: 'Change the expiry of the hold for Open Day' }),
  )
  const input = screen.getByLabelText('New expiry')
  await userEvent.clear(input)
  await userEvent.type(input, '2027-11-03T09:00')
  await userEvent.click(screen.getByRole('button', { name: 'Save expiry' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The hold must expire no later than the booking starts.',
  )
  expect(updateHoldMock).not.toHaveBeenCalled()
})

it('TC-HF17 releases a hold with a reason and takes it off the list', async () => {
  releaseHoldMock.mockResolvedValue(hold({ status: 'Cancelled' }))
  renderCard()
  await userEvent.click(await screen.findByRole('button', { name: 'Release the hold for Open Day' }))
  await userEvent.type(screen.getByLabelText('Reason for releasing'), 'Hall needed for exams.')
  await userEvent.click(screen.getByRole('button', { name: 'Release hold' }))

  expect(releaseHoldMock).toHaveBeenCalledWith('101', 'Hall needed for exams.', staff)
  expect(await screen.findByRole('status')).toHaveTextContent('Released the hold for Open Day.')
  expect(screen.getByText('No holds on this venue.')).toBeInTheDocument()
})

it('TC-HF18 asks for a reason before releasing', async () => {
  renderCard()
  await userEvent.click(await screen.findByRole('button', { name: 'Release the hold for Open Day' }))
  await userEvent.click(screen.getByRole('button', { name: 'Release hold' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Give the Coordinator a reason for releasing this hold.',
  )
  expect(releaseHoldMock).not.toHaveBeenCalled()
})

it('TC-HF19 shows the server refusal, and offers no actions on an expired hold', async () => {
  listHoldsMock.mockResolvedValue([
    hold(),
    hold({ id: '102', eventTitle: 'Gala', holdExpired: true, status: 'Expired' }),
  ])
  releaseHoldMock.mockRejectedValue(new EventRuleError('This hold has already been released.'))
  renderCard()
  await userEvent.click(await screen.findByRole('button', { name: 'Release the hold for Open Day' }))
  await userEvent.type(screen.getByLabelText('Reason for releasing'), 'Closed.')
  await userEvent.click(screen.getByRole('button', { name: 'Release hold' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('This hold has already been released.')
  expect(screen.queryByRole('button', { name: 'Release the hold for Gala' })).toBeNull()
})
