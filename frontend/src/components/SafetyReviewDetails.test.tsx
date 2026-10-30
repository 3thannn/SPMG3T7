import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SafetyReviewDetails from './SafetyReviewDetails'
import {
  getSafetyReview,
  type ReviewedEquipment,
  type ReviewedVenue,
  type SafetyReview,
} from '../eventsStore'
import { ApiError } from '../api'
import { formatRecordedAt } from '../status'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getSafetyReview: vi.fn(),
}))

const reviewMock = vi.mocked(getSafetyReview)
const officer = buildSession({ role: 'Safety Officer', id: '5', name: 'Alex' })

function venue(overrides: Partial<ReviewedVenue> = {}): ReviewedVenue {
  return {
    bookingId: '1',
    venueId: '50',
    venueName: 'Riverside Hall',
    location: 'Block C, Level 2',
    status: 'Confirmed',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    capacity: 100,
    headcount: 30,
    overCapacity: false,
    requiredLayout: 'Theatre',
    supportedLayouts: 'Theatre, Banquet',
    facilities: 'Stage, PA system',
    accessibilityFeatures: 'Step-free access, hearing loop',
    accessibilityNeeds: ['Hearing loop', 'Wheelchair access'],
    operatingHours: '08:00-22:00',
    setupMinutes: 30,
    turnaroundMinutes: 45,
    closures: [],
    ...overrides,
  }
}

function equipment(overrides: Partial<ReviewedEquipment> = {}): ReviewedEquipment {
  return {
    id: '7',
    type: 'Projector',
    quantity: 2,
    technicalRequirements: 'HDMI',
    supportNotes: 'Tested',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    ...overrides,
  }
}

function review(overrides: Partial<SafetyReview> = {}): SafetyReview {
  return {
    eventId: '101',
    title: 'Open House',
    status: 'Pending Safety Check',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    expectedAttendance: 30,
    accessibilityNeeds: 'Wheelchair access',
    preferredLayout: 'Theatre',
    venueRequirements: 'Stage, Projector',
    waitingSince: '2099-01-05T09:00:00',
    venues: [venue()],
    equipment: [equipment()],
    ...overrides,
  }
}

/** The text of the <dd> under a given <dt>, within a container. */
function fact(container: HTMLElement, label: string): string {
  const term = within(container).getByText(label, { selector: 'dt' })
  return term.nextElementSibling?.textContent ?? ''
}

afterEach(() => {
  vi.resetAllMocks()
})

describe('loading', () => {
  it('says it is loading, then asks for this event', () => {
    reviewMock.mockReturnValue(new Promise(() => {}))
    render(<SafetyReviewDetails eventId="101" session={officer} />)

    expect(screen.getByRole('heading', { name: 'Safety review' })).toBeInTheDocument()
    expect(screen.getByText('Loading the safety review…')).toBeInTheDocument()
    expect(reviewMock).toHaveBeenCalledWith('101', officer)
  })

  it('says when the review cannot be loaded', async () => {
    reviewMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    render(<SafetyReviewDetails eventId="101" session={officer} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/^Could not load the safety review\./)
  })

  it('ignores an answer that arrives after it has gone', async () => {
    let resolve!: (value: SafetyReview) => void
    reviewMock.mockReturnValue(new Promise((res) => (resolve = res)))
    render(<SafetyReviewDetails eventId="101" session={officer} />).unmount()
    resolve(review())

    let reject!: (error: unknown) => void
    const failing = new Promise<SafetyReview>((_res, rej) => (reject = rej))
    reviewMock.mockReturnValue(failing)
    render(<SafetyReviewDetails eventId="101" session={officer} />).unmount()
    reject(new Error('gone'))
    await expect(failing).rejects.toThrow('gone')
  })
})

describe('the event (AC2)', () => {
  it('shows the expected attendance and the event accessibility requirements', async () => {
    reviewMock.mockResolvedValue(review())
    const { container } = render(<SafetyReviewDetails eventId="101" session={officer} />)
    await screen.findByRole('list', { name: 'Booked venues' })

    const facts = container.querySelector('.safety-review-facts') as HTMLElement
    expect(fact(facts, 'Expected attendance')).toBe('30 people')
    expect(fact(facts, 'Accessibility requirements')).toBe('Wheelchair access')
    expect(fact(facts, 'Preferred layout')).toBe('Theatre')
    expect(fact(facts, 'Venue requirements')).toBe('Stage, Projector')
    expect(fact(facts, 'Waiting since')).toBe(formatRecordedAt('2099-01-05T09:00:00'))
  })

  it('says what was not given', async () => {
    reviewMock.mockResolvedValue(
      review({
        expectedAttendance: null,
        accessibilityNeeds: '',
        preferredLayout: ' ',
        venueRequirements: '',
        venues: [],
        equipment: [],
      }),
    )
    const { container } = render(<SafetyReviewDetails eventId="101" session={officer} />)
    expect(await screen.findByText('No venue is booked for this event.')).toBeInTheDocument()

    const facts = container.querySelector('.safety-review-facts') as HTMLElement
    expect(fact(facts, 'Expected attendance')).toBe('Not estimated')
    expect(fact(facts, 'Accessibility requirements')).toBe('Not stated')
    expect(fact(facts, 'Preferred layout')).toBe('Not stated')
    expect(fact(facts, 'Venue requirements')).toBe('Not stated')
    expect(screen.getByText('No equipment is reserved for this event.')).toBeInTheDocument()
  })
})

describe('each booked venue (AC2)', () => {
  it('shows capacity, layout, accessibility and known restrictions', async () => {
    reviewMock.mockResolvedValue(
      review({
        venues: [
          venue({
            closures: [
              { startDate: '2099-12-01', endDate: '2099-12-03', reason: 'Renovation' },
              { startDate: '2099-12-24', endDate: '2099-12-24', reason: '' },
            ],
          }),
        ],
      }),
    )
    render(<SafetyReviewDetails eventId="101" session={officer} />)
    const list = await screen.findByRole('list', { name: 'Booked venues' })
    const [card] = within(list).getAllByRole('listitem').filter((item) => item.parentElement === list)

    expect(within(card).getByText('Riverside Hall')).toBeInTheDocument()
    expect(within(card).getByText(/Block C, Level 2/)).toBeInTheDocument()
    expect(fact(card, 'Capacity')).toBe('100 people')
    expect(fact(card, 'Headcount')).toBe('30 people')
    expect(fact(card, 'Layout')).toBe('Theatre · supports Theatre, Banquet')
    expect(fact(card, 'Venue accessibility')).toBe('Step-free access, hearing loop')
    expect(fact(card, 'Accessibility asked for')).toBe('Hearing loop, Wheelchair access')
    expect(fact(card, 'Facilities')).toBe('Stage, PA system')
    expect(within(card).getByRole('heading', { name: 'Known restrictions' })).toBeInTheDocument()
    expect(within(card).getByText('Operating hours: 08:00-22:00')).toBeInTheDocument()
    expect(
      within(card).getByText('Setup 30 minutes before, turnaround 45 minutes after'),
    ).toBeInTheDocument()
    expect(within(card).getByText(/^Unavailable .* – .*: Renovation$/)).toBeInTheDocument()
    const oneDay = within(card).getByText(/^Unavailable [^–]*$/)
    expect(oneDay.textContent).not.toContain(':')
    expect(card).not.toHaveClass('is-warning')
    expect(within(card).queryByRole('note')).not.toBeInTheDocument()
  })

  it('warns when more people are booked in than the venue holds', async () => {
    reviewMock.mockResolvedValue(
      review({ venues: [venue({ headcount: 120, overCapacity: true })] }),
    )
    render(<SafetyReviewDetails eventId="101" session={officer} />)

    expect(await screen.findByRole('note')).toHaveTextContent(
      'More people are booked into this venue than it holds.',
    )
    expect(screen.getByRole('note').closest('li')).toHaveClass('is-warning')
  })

  it('says what a venue has not recorded', async () => {
    reviewMock.mockResolvedValue(
      review({
        venues: [
          venue({
            location: '',
            capacity: null,
            headcount: null,
            requiredLayout: '',
            supportedLayouts: '',
            facilities: '',
            accessibilityFeatures: '',
            accessibilityNeeds: [],
            operatingHours: '',
            setupMinutes: 1,
            turnaroundMinutes: 0,
          }),
        ],
      }),
    )
    render(<SafetyReviewDetails eventId="101" session={officer} />)
    const list = await screen.findByRole('list', { name: 'Booked venues' })
    const card = list.firstElementChild as HTMLElement

    expect(within(card).queryByText(/·/, { selector: 'span' })).not.toBeInTheDocument()
    expect(fact(card, 'Capacity')).toBe('Unknown')
    expect(fact(card, 'Headcount')).toBe('Not set')
    expect(fact(card, 'Layout')).toBe('None requested · supports None recorded')
    expect(fact(card, 'Venue accessibility')).toBe('None recorded')
    expect(fact(card, 'Accessibility asked for')).toBe('None')
    expect(fact(card, 'Facilities')).toBe('None recorded')
    expect(within(card).getByText('Operating hours: None recorded')).toBeInTheDocument()
    expect(
      within(card).getByText('Setup 1 minute before, turnaround 0 minutes after'),
    ).toBeInTheDocument()
    expect(within(card).getByText('No upcoming unavailability')).toBeInTheDocument()
  })

  it('lists several venues in the order the server sends', async () => {
    reviewMock.mockResolvedValue(
      review({ venues: [venue(), venue({ bookingId: '2', venueName: 'Breakout Room' })] }),
    )
    render(<SafetyReviewDetails eventId="101" session={officer} />)
    const list = await screen.findByRole('list', { name: 'Booked venues' })

    const names = [...list.children].map((item) => item.querySelector('strong')?.textContent)
    expect(names).toEqual(['Riverside Hall', 'Breakout Room'])
  })
})

describe('reserved equipment (AC2)', () => {
  it('shows each line with its quantity, time and notes', async () => {
    reviewMock.mockResolvedValue(
      review({
        equipment: [
          equipment(),
          equipment({ id: '8', type: 'Microphone', quantity: 4, technicalRequirements: '', supportNotes: '' }),
        ],
      }),
    )
    render(<SafetyReviewDetails eventId="101" session={officer} />)
    const list = await screen.findByRole('list', { name: 'Reserved equipment' })
    const [projector, microphone] = within(list).getAllByRole('listitem')

    expect(within(projector).getByText('Projector × 2')).toBeInTheDocument()
    expect(within(projector).getByText('Technical requirements: HDMI')).toBeInTheDocument()
    expect(within(projector).getByText('Support notes: Tested')).toBeInTheDocument()
    expect(within(microphone).getByText('Microphone × 4')).toBeInTheDocument()
    expect(within(microphone).queryByText(/Technical requirements/)).not.toBeInTheDocument()
    expect(within(microphone).queryByText(/Support notes/)).not.toBeInTheDocument()
  })
})

describe('read-only (AC3)', () => {
  it('offers nothing to edit or press', async () => {
    reviewMock.mockResolvedValue(review())
    render(<SafetyReviewDetails eventId="101" session={officer} />)
    await screen.findByRole('list', { name: 'Booked venues' })

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})
