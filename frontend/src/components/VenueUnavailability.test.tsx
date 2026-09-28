/**
 * The unavailable-dates card on a venue record — US12.1.
 *
 * Two halves, as in the story: a Coordinator reads the blackout periods when
 * viewing the venue, and Venue Staff record one by giving a start and an end
 * that is not before it. Every test pins `today` so Now/Upcoming/Past do not
 * depend on the day the suite runs.
 */

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VenueUnavailability from './VenueUnavailability'
import {
  REASON_MAX,
  VenueRuleError,
  formatDate,
  formatDateRange,
  listUnavailability,
  markUnavailable,
  type UnavailabilityRecord,
} from '../venuesStore'
import { ApiError } from '../api'
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
    reason: 'Annual maintenance',
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

async function fill(start: string, end: string, reason = '') {
  const user = userEvent.setup()
  if (start) await user.type(screen.getByLabelText('Start date'), start)
  if (end) await user.type(screen.getByLabelText('End date'), end)
  if (reason) await user.type(screen.getByLabelText('Reason (optional)'), reason)
  await user.click(screen.getByRole('button', { name: 'Mark unavailable' }))
}

function upcomingList() {
  return screen.getByRole('list', { name: 'Current and upcoming unavailable dates' })
}

// --- AC4: Coordinators view the ranges ---------------------------------------

it('asks for this venue’s ranges', async () => {
  renderFor()

  await waitFor(() => expect(listMock).toHaveBeenCalledWith('1', coordinator))
})

it('says it is loading until the ranges arrive', () => {
  listMock.mockReturnValue(new Promise(() => {}))

  renderFor()

  expect(screen.getByText('Loading unavailable dates…')).toBeInTheDocument()
})

it('says plainly when nothing is recorded', async () => {
  renderFor()

  expect(
    await screen.findByText('No current or upcoming unavailable dates recorded.'),
  ).toBeInTheDocument()
})

it('lists each range with its dates and reason', async () => {
  listMock.mockResolvedValue([range()])

  renderFor()

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent(formatDateRange('2026-11-02', '2026-11-06'))
  expect(row).toHaveTextContent('Annual maintenance')
})

it('says a range has no reason rather than leaving a gap', async () => {
  listMock.mockResolvedValue([range({ reason: '' })])

  renderFor()

  expect(await screen.findByText('No reason given')).toBeInTheDocument()
})

it('shows a one-day range as that one day', async () => {
  listMock.mockResolvedValue([range({ startDate: '2026-12-25', endDate: '2026-12-25' })])

  renderFor()

  const row = within(await screen.findByRole('list')).getByRole('listitem')
  expect(row).toHaveTextContent(formatDate('2026-12-25'))
  expect(row).not.toHaveTextContent('–')
})

it('gives a Coordinator nothing to write with', async () => {
  listMock.mockResolvedValue([range()])

  renderFor()
  await screen.findByRole('list')

  expect(screen.queryByRole('button', { name: 'Mark unavailable' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Start date')).not.toBeInTheDocument()
})

it('says the dates could not be loaded rather than that there are none', async () => {
  listMock.mockRejectedValue(new Error('network down'))

  renderFor()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /Could not load the unavailable dates/,
  )
  expect(screen.queryByText(/No current or upcoming/)).not.toBeInTheDocument()
})

it('points a server fault at the backend log', async () => {
  listMock.mockRejectedValue(new ApiError('Request failed.', 'unknown', 500))

  renderFor()

  expect(await screen.findByRole('alert')).toHaveTextContent(/HTTP 500/)
})

// --- Now, upcoming and past, at the boundaries -------------------------------

it.each([
  ['starts today', { startDate: TODAY, endDate: '2026-11-10' }, 'Now'],
  ['ends today', { startDate: '2026-11-01', endDate: TODAY }, 'Now'],
  ['is today only', { startDate: TODAY, endDate: TODAY }, 'Now'],
  ['starts tomorrow', { startDate: '2026-11-05', endDate: '2026-11-06' }, 'Upcoming'],
])('tags a range that %s as %s', async (_, dates, label) => {
  listMock.mockResolvedValue([range(dates)])

  renderFor()

  expect(within(await screen.findByRole('list')).getByText(label)).toBeInTheDocument()
})

it('folds a range that ended yesterday away under Past', async () => {
  listMock.mockResolvedValue([range({ startDate: '2026-10-01', endDate: '2026-11-03' })])

  renderFor()

  const past = await screen.findByText('Past (1)')
  expect(past.closest('details')).not.toHaveAttribute('open')
  expect(screen.queryByRole('list', { name: /Current and upcoming/ })).not.toBeInTheDocument()
  expect(screen.getByText('No current or upcoming unavailable dates recorded.')).toBeInTheDocument()
})

it('keeps current and upcoming ranges apart from past ones', async () => {
  listMock.mockResolvedValue([
    range({ id: '1', startDate: '2026-01-01', endDate: '2026-01-02', reason: 'Old' }),
    range({ id: '2', startDate: '2026-12-24', endDate: '2026-12-26', reason: 'Christmas' }),
  ])

  renderFor()

  expect(within(await screen.findByRole('list', { name: /Current and upcoming/ })).getByText('Christmas')).toBeInTheDocument()
  const past = screen.getByRole('list', { name: 'Past unavailable dates', hidden: true })
  expect(within(past).getByText('Old')).toBeInTheDocument()
})

// --- The closed-today banner: "don't consider it" ------------------------------

it('warns when the venue is unavailable today', async () => {
  listMock.mockResolvedValue([range()])

  renderFor()

  const banner = await screen.findByText(/Unavailable today/)
  expect(banner.closest('p')).toHaveTextContent(`through ${formatDate('2026-11-06')}`)
})

it('gives the last day of overlapping closures, not the first to end', async () => {
  listMock.mockResolvedValue([
    range({ id: '1', startDate: '2026-11-01', endDate: '2026-11-06' }),
    range({ id: '2', startDate: '2026-11-03', endDate: '2026-11-20' }),
  ])

  renderFor()

  const banner = (await screen.findByText(/Unavailable today/)).closest('p')
  expect(banner).toHaveTextContent(`through ${formatDate('2026-11-20')}`)
})

it('does not warn about a closure that has not started', async () => {
  listMock.mockResolvedValue([range({ startDate: '2026-11-05', endDate: '2026-11-06' })])

  renderFor()
  await screen.findByRole('list')

  expect(screen.queryByText(/Unavailable today/)).not.toBeInTheDocument()
})

it('does not warn about a closure that is over', async () => {
  listMock.mockResolvedValue([range({ startDate: '2026-10-01', endDate: '2026-11-03' })])

  renderFor()
  await screen.findByText('Past (1)')

  expect(screen.queryByText(/Unavailable today/)).not.toBeInTheDocument()
})

// --- AC1-3: Venue Staff record a range -----------------------------------------

it('offers Venue Staff a start, an end and a reason', async () => {
  renderForStaff()

  expect(await screen.findByLabelText('Start date')).toHaveAttribute('type', 'date')
  expect(screen.getByLabelText('End date')).toHaveAttribute('type', 'date')
  expect(screen.getByLabelText('Reason (optional)')).toHaveAttribute(
    'maxLength',
    String(REASON_MAX),
  )
})

it('records the range and adds it to the list', async () => {
  markMock.mockResolvedValue(range({ id: '200', reason: 'Roof repair' }))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06', 'Roof repair')

  expect(markMock).toHaveBeenCalledWith(
    '1',
    { startDate: '2026-11-02', endDate: '2026-11-06', reason: 'Roof repair' },
    venueStaff,
  )
  expect(await within(upcomingList()).findByText('Roof repair')).toBeInTheDocument()
})

it('says the range was saved and clears the form for the next one', async () => {
  markMock.mockResolvedValue(range())
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06')

  expect(await screen.findByText(/^Marked unavailable:/)).toHaveTextContent(
    formatDateRange('2026-11-02', '2026-11-06'),
  )
  expect(screen.getByLabelText('Start date')).toHaveValue('')
  expect(screen.getByLabelText('End date')).toHaveValue('')
})

it('drops the saved message as soon as the next range is started', async () => {
  markMock.mockResolvedValue(range())
  renderForStaff()
  await screen.findByLabelText('Start date')
  await fill('2026-11-02', '2026-11-06')
  await screen.findByText(/^Marked unavailable:/)

  await userEvent.type(screen.getByLabelText('Start date'), '2026-12-01')

  expect(screen.queryByText(/^Marked unavailable:/)).not.toBeInTheDocument()
})

it('puts a new range in date order, not at the end', async () => {
  listMock.mockResolvedValue([
    range({ id: '1', startDate: '2026-12-24', endDate: '2026-12-26', reason: 'Christmas' }),
  ])
  markMock.mockResolvedValue(
    range({ id: '2', startDate: '2026-11-10', endDate: '2026-11-11', reason: 'Inspection' }),
  )
  renderForStaff()
  await screen.findByText('Christmas')

  await fill('2026-11-10', '2026-11-11', 'Inspection')

  await within(upcomingList()).findByText('Inspection')
  const reasons = within(upcomingList())
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.unavailability-reason')?.textContent)
  expect(reasons).toEqual(['Inspection', 'Christmas'])
})

it('orders ranges starting the same day by their end', async () => {
  listMock.mockResolvedValue([
    range({ id: '1', startDate: '2026-11-10', endDate: '2026-11-20', reason: 'Long' }),
  ])
  markMock.mockResolvedValue(
    range({ id: '2', startDate: '2026-11-10', endDate: '2026-11-11', reason: 'Short' }),
  )
  renderForStaff()
  await screen.findByText('Long')

  await fill('2026-11-10', '2026-11-11', 'Short')

  await within(upcomingList()).findByText('Short')
  const reasons = within(upcomingList())
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.unavailability-reason')?.textContent)
  expect(reasons).toEqual(['Short', 'Long'])
})

it('shows the closed-today warning once a range covering today is saved', async () => {
  markMock.mockResolvedValue(range({ startDate: TODAY, endDate: TODAY }))
  renderForStaff()
  await screen.findByText('No current or upcoming unavailable dates recorded.')

  await fill(TODAY, TODAY)

  expect(await screen.findByText(/Unavailable today/)).toBeInTheDocument()
})

it('accepts a one-day range, the same date twice', async () => {
  markMock.mockResolvedValue(range({ startDate: TODAY, endDate: TODAY }))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill(TODAY, TODAY)

  expect(markMock).toHaveBeenCalledWith(
    '1',
    expect.objectContaining({ startDate: TODAY, endDate: TODAY }),
    venueStaff,
  )
})

it('trims the reason before sending it', async () => {
  markMock.mockResolvedValue(range())
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06', '  Roof repair  ')

  expect(markMock).toHaveBeenCalledWith(
    '1',
    expect.objectContaining({ reason: 'Roof repair' }),
    venueStaff,
  )
})

it('will not let past dates be picked', async () => {
  renderForStaff()
  await screen.findByLabelText('Start date')

  expect(screen.getByLabelText('Start date')).toHaveAttribute('min', TODAY)
  expect(screen.getByLabelText('End date')).toHaveAttribute('min', TODAY)
})

it('will not let the end date be picked before the start', async () => {
  renderForStaff()
  await screen.findByLabelText('Start date')

  await userEvent.type(screen.getByLabelText('Start date'), '2026-11-02')

  expect(screen.getByLabelText('End date')).toHaveAttribute('min', '2026-11-02')
})

// --- AC2 and the other refusals, before and after the server -------------------

it.each([
  ['no dates', '', '', 'Give the start date.'],
  ['no start', '', '2026-11-06', 'Give the start date.'],
  ['no end', '2026-11-02', '', 'Give the end date.'],
  ['an end the day before the start', '2026-11-02', '2026-11-01', 'The end date cannot be earlier than the start date.'],
])('refuses %s without asking the server', async (_, start, end, message) => {
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill(start, end)

  expect(screen.getByRole('alert')).toHaveTextContent(message)
  expect(markMock).not.toHaveBeenCalled()
})

it('shows the server’s reason when it refuses the range', async () => {
  markMock.mockRejectedValue(new VenueRuleError('The end date cannot be earlier than the start date.'))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06')

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The end date cannot be earlier than the start date.',
  )
})

it('keeps what was typed when saving fails, so it can be retried', async () => {
  markMock.mockRejectedValue(new Error('network down'))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06')

  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not save these dates/)
  expect(screen.getByLabelText('Start date')).toHaveValue('2026-11-02')
  expect(screen.getByLabelText('End date')).toHaveValue('2026-11-06')
})

it('cannot be sent twice while it is saving', async () => {
  markMock.mockReturnValue(new Promise(() => {}))
  renderForStaff()
  await screen.findByLabelText('Start date')

  await fill('2026-11-02', '2026-11-06')

  const button = screen.getByRole('button', { name: 'Saving…' })
  expect(button).toBeDisabled()
  expect(screen.getByLabelText('Start date')).toBeDisabled()
})

it('clears an earlier refusal once a range is accepted', async () => {
  markMock.mockResolvedValue(range())
  renderForStaff()
  await screen.findByLabelText('Start date')
  await fill('2026-11-02', '')
  expect(screen.getByRole('alert')).toHaveTextContent('Give the end date.')

  await fill('', '2026-11-06')

  await screen.findByText(/^Marked unavailable:/)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// --- Edges of the card's own state ---------------------------------------------

it('finds the last day of overlapping closures whichever order they come in', async () => {
  listMock.mockResolvedValue([
    range({ id: '1', startDate: '2026-11-01', endDate: '2026-11-20' }),
    range({ id: '2', startDate: '2026-11-03', endDate: '2026-11-06' }),
  ])

  renderFor()

  const banner = (await screen.findByText(/Unavailable today/)).closest('p')
  expect(banner).toHaveTextContent(`through ${formatDate('2026-11-20')}`)
})

it('still saves a range when the list could not be loaded, and says so', async () => {
  listMock.mockRejectedValue(new Error('network down'))
  markMock.mockResolvedValue(range())
  renderForStaff()
  await screen.findByText(/Could not load the unavailable dates/)

  await fill('2026-11-02', '2026-11-06')

  expect(await screen.findByText(/^Marked unavailable:/)).toBeInTheDocument()
  // The list stays in its error state rather than pretending to be complete.
  expect(screen.getByText(/Could not load the unavailable dates/)).toBeInTheDocument()
})

it('ignores a load that fails after the card has gone', async () => {
  let fail: (reason: unknown) => void = () => {}
  listMock.mockReturnValue(
    new Promise((_, reject) => {
      fail = reject
    }),
  )
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  const { unmount } = renderFor()

  unmount()
  fail(new Error('network down'))
  await Promise.resolve()

  expect(errors).not.toHaveBeenCalled()
  errors.mockRestore()
})

it('ignores a load that succeeds after the card has gone', async () => {
  let succeed: (ranges: UnavailabilityRecord[]) => void = () => {}
  listMock.mockReturnValue(
    new Promise((resolve) => {
      succeed = resolve
    }),
  )
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  const { unmount } = renderFor()

  unmount()
  succeed([range()])
  await Promise.resolve()

  expect(errors).not.toHaveBeenCalled()
  errors.mockRestore()
})
