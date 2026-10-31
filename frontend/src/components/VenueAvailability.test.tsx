/**
 * US12.3: what is taking up a venue over a date range.
 *
 * The server decides what is listed and in what order (see
 * backend/tests/test_venue_availability_us12_3.py); this card asks for the
 * range picked and shows each entry by type.
 */

import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import VenueAvailability from './VenueAvailability'
import {
  VenueRuleError,
  addDays,
  asSingaporeTime,
  defaultAvailabilityRange,
  getAvailability,
  validateAvailabilityRange,
  type AvailabilityEntry,
  type VenueAvailability as Availability,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getAvailability: vi.fn(),
}))

const getAvailabilityMock = vi.mocked(getAvailability)

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const session = buildSession({ role: 'Venue Staff', id: '3', name: 'Sam', email: 'sam@example.edu' })
const TODAY = '2027-03-01'

function entry(overrides: Partial<AvailabilityEntry>): AvailabilityEntry {
  return {
    kind: 'confirmed',
    startsAt: '2027-03-03T09:30',
    endsAt: '2027-03-03T12:45',
    bookingId: '1',
    eventId: '1',
    eventTitle: 'Faculty Welcome Night',
    eventStartsAt: '2027-03-03T10:00',
    eventEndsAt: '2027-03-03T12:00',
    holdExpiresAt: '',
    periodId: '',
    startDate: '',
    endDate: '',
    reasonType: '',
    otherReason: '',
    ...overrides,
  }
}

function answer(entries: AvailabilityEntry[], overrides: Partial<Availability> = {}) {
  getAvailabilityMock.mockResolvedValue({
    venueId: '1',
    from: '2027-03-01',
    to: '2027-03-14',
    setupMinutes: 30,
    turnaroundMinutes: 45,
    entries,
    ...overrides,
  })
}

const EVERY_KIND = [
  entry({}),
  entry({
    kind: 'requested',
    bookingId: '2',
    eventTitle: '',
    eventId: '',
    startsAt: '2027-03-04T09:30',
    endsAt: '2027-03-04T12:45',
  }),
  entry({
    kind: 'unavailable',
    bookingId: '',
    eventId: '',
    eventTitle: '',
    eventStartsAt: '',
    eventEndsAt: '',
    startsAt: '2027-03-05T00:00',
    endsAt: '2027-03-07T00:00',
    periodId: '7',
    startDate: '2027-03-05',
    endDate: '2027-03-06',
    reasonType: 'other',
    otherReason: 'Floor polishing',
  }),
  entry({
    kind: 'hold',
    bookingId: '3',
    eventTitle: 'Open Day',
    startsAt: '2027-03-08T13:30',
    endsAt: '2027-03-08T16:45',
    eventStartsAt: '2027-03-08T14:00',
    eventEndsAt: '2027-03-08T16:00',
    holdExpiresAt: '2027-03-04T17:00',
  }),
]

async function rows() {
  const list = await screen.findByRole('list', { name: /What is taking up this venue/ })
  return within(list).getAllByRole('listitem')
}

describe('AC1: the range', () => {
  it('asks for the next 14 days to start with', async () => {
    answer([])

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(screen.getByLabelText('From')).toHaveValue('2027-03-01')
    expect(screen.getByLabelText('To')).toHaveValue('2027-03-14')
    await screen.findByText(/Showing/)
    expect(getAvailabilityMock).toHaveBeenCalledWith(
      '1',
      { from: '2027-03-01', to: '2027-03-14' },
      session,
    )
  })

  it('asks again for the range picked', async () => {
    answer([])
    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)
    await screen.findByText(/Showing/)

    const from = screen.getByLabelText('From')
    const to = screen.getByLabelText('To')
    await userEvent.clear(from)
    await userEvent.type(from, '2027-04-01')
    await userEvent.clear(to)
    await userEvent.type(to, '2027-04-30')
    await userEvent.click(screen.getByRole('button', { name: 'Show' }))

    expect(getAvailabilityMock).toHaveBeenLastCalledWith(
      '1',
      { from: '2027-04-01', to: '2027-04-30' },
      session,
    )
  })

  it('says what is wrong with a range before asking', async () => {
    answer([])
    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)
    await screen.findByText(/Showing/)

    const to = screen.getByLabelText('To')
    await userEvent.clear(to)
    await userEvent.type(to, '2027-02-01')
    await userEvent.click(screen.getByRole('button', { name: 'Show' }))

    expect(screen.getByRole('alert')).toHaveTextContent(
      'The to date cannot be earlier than the from date.',
    )
    expect(getAvailabilityMock).toHaveBeenCalledTimes(1)
  })

  it("shows the server's reason when it refuses a range", async () => {
    getAvailabilityMock.mockRejectedValue(new VenueRuleError('Pick a range of 366 days or fewer.'))

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Pick a range of 366 days or fewer.')
  })
})

describe('AC2: everything taking up the venue, labelled by type', () => {
  it('lists the entries in the order the server sends, each with its type', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const labels = (await rows()).map((row) => row.querySelector('.availability-tag')?.textContent)
    expect(labels).toEqual(['Confirmed booking', 'Requested booking', 'Unavailable', 'Tentative hold'])
  })

  it('shows when a hold expires', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const hold = (await rows())[3]
    expect(hold).toHaveTextContent('Open Day')
    expect(hold).toHaveTextContent(/Hold expires 04 Mar 2027,? 17:00/)
  })

  it('shows a closure as its days and reason', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const closed = (await rows())[2]
    expect(closed).toHaveTextContent('Floor polishing')
    expect(closed.querySelector('.availability-when')).toHaveTextContent('05 Mar 2027 – 06 Mar 2027')
  })

  it("names another event's booking by number only", async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect((await rows())[1]).toHaveTextContent('Booking #2 for another event')
  })

  it('lists two closures that start on the same day', async () => {
    const closure = EVERY_KIND[2]
    answer([
      closure,
      { ...closure, periodId: '8', endDate: '2027-03-09', otherReason: 'Rewiring' },
    ])

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const [first, second] = await rows()
    expect(first).toHaveTextContent('Floor polishing')
    expect(second).toHaveTextContent('Rewiring')
  })

  it('says so when nothing is taking up the venue', async () => {
    answer([])

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(await screen.findByText(/Nothing is booked, held or closed here/)).toBeInTheDocument()
  })

  it('says what went wrong when the list cannot load', async () => {
    getAvailabilityMock.mockRejectedValue(new Error('network down'))

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})

describe('AC3: the full occupied window', () => {
  it('leads with the window and gives the event times under it', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const confirmed = (await rows())[0]
    expect(confirmed.querySelector('.availability-when')).toHaveTextContent(/09:30 – 12:45/)
    expect(confirmed).toHaveTextContent(/Event .*10:00 – 12:00/)
  })

  it('says how much setup and turnaround the times include', async () => {
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(await screen.findByText(/Showing/)).toHaveTextContent(
      'Booking times include 30 minutes setup and 45 minutes turnaround.',
    )
  })

  it('says nothing about it for a venue with none', async () => {
    answer(EVERY_KIND, { setupMinutes: 0, turnaroundMinutes: 0 })

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    expect(await screen.findByText(/Showing/)).not.toHaveTextContent('setup')
  })
})

describe('times read the same in any timezone', () => {
  afterEach(() => vi.unstubAllEnvs())

  it.each(['UTC', 'Asia/Singapore', 'America/New_York'])('in %s', async (timezone) => {
    vi.stubEnv('TZ', timezone)
    answer(EVERY_KIND)

    render(<VenueAvailability venueId="1" session={session} today={TODAY} />)

    const [confirmed, , , hold] = await rows()
    expect(confirmed.querySelector('.availability-when')).toHaveTextContent(
      '03 Mar 2027, 09:30 – 12:45',
    )
    expect(hold).toHaveTextContent(/Hold expires 04 Mar 2027,? 17:00/)
  })

  it('leaves a time that already says its zone alone', () => {
    expect(asSingaporeTime('2027-03-03T09:30')).toBe('2027-03-03T09:30+08:00')
    expect(asSingaporeTime('2027-03-03T01:30Z')).toBe('2027-03-03T01:30Z')
    expect(asSingaporeTime('2027-03-03T09:30+08:00')).toBe('2027-03-03T09:30+08:00')
    expect(asSingaporeTime('')).toBe('')
  })
})

describe('the range helpers', () => {
  it('moves a date by whole days across a month end', () => {
    expect(addDays('2027-02-27', 3)).toBe('2027-03-02')
    expect(addDays('2027-03-01', -1)).toBe('2027-02-28')
  })

  it('makes the default range 14 days long, today included', () => {
    expect(defaultAvailabilityRange('2027-12-25')).toEqual({ from: '2027-12-25', to: '2028-01-07' })
  })

  it.each([
    [{ from: '', to: '2027-03-01' }, 'Choose a from date.'],
    [{ from: '2027-03-01', to: '' }, 'Choose a to date.'],
    [{ from: '2027-03-02', to: '2027-03-01' }, 'The to date cannot be earlier than the from date.'],
    [{ from: '2027-01-01', to: '2028-01-02' }, 'Pick a range of 366 days or fewer.'],
    [{ from: '2027-03-01', to: '2027-03-01' }, ''],
    [{ from: '2027-01-01', to: '2028-01-01' }, ''],
  ])('checks %o', (range, problem) => {
    expect(validateAvailabilityRange(range)).toBe(problem)
  })
})
