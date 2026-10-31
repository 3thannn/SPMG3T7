/**
 * The small paths each page's own test file does not reach: links that route
 * in place, filters, an event with no date yet, a load that fails after the
 * page has gone, and the sign-in form's fallback messages. Each page's data
 * calls are mocked; the pages themselves are real.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AttendPage from './AttendPage'
import EquipmentQueuePage from './EquipmentQueuePage'
import EventsPage from './EventsPage'
import LandingPage from './LandingPage'
import MyRegistrationsPage from './MyRegistrationsPage'
import NotificationsPage from './NotificationsPage'
import SignInPage from './SignInPage'
import TeamAssignmentsPage from './TeamAssignmentsPage'
import VenueDetailPage from './VenueDetailPage'
import VenueFormPage from './VenueFormPage'
import VenuesPage from './VenuesPage'
import TopNav from '../components/TopNav'
import EquipmentReservation from '../components/EquipmentReservation'
import EventRegistration from '../components/EventRegistration'
import { ApiError, login } from '../api'
import { getEquipmentAvailability, listEquipmentQueue, type EquipmentRequest } from '../equipmentStore'
import { listEvents, type EventRecord } from '../eventsStore'
import { listNotifications } from '../notificationsStore'
import {
  getRegistrationSettings,
  listMyRegistrations,
  listOpenEvents,
  type MyRegistration,
  type OpenEvent,
} from '../registrationStore'
import { listCoordinators, listUnassignedEvents } from '../unassignedQueueStore'
import { getVenue, listVenues, type VenueRecord } from '../venuesStore'
import UnassignedQueuePage from './UnassignedQueuePage'
import { buildSession } from '../test/sessions'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  login: vi.fn(),
}))
vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listEvents: vi.fn(),
}))
vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipmentQueue: vi.fn(),
  getEquipmentAvailability: vi.fn(),
}))
vi.mock('../notificationsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../notificationsStore')>()),
  listNotifications: vi.fn(async () => []),
}))
vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  listOpenEvents: vi.fn(),
  listMyRegistrations: vi.fn(),
  getRegistrationSettings: vi.fn(),
}))
vi.mock('../unassignedQueueStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../unassignedQueueStore')>()),
  listUnassignedEvents: vi.fn(),
  listCoordinators: vi.fn(),
}))
vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(),
  getVenue: vi.fn(),
  listUnavailability: vi.fn(async () => []),
}))
vi.mock('../holdsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../holdsStore')>()),
  listHolds: vi.fn(async () => []),
  listHoldableEvents: vi.fn(async () => []),
}))

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const lead = buildSession({ role: 'Event Coordinator Lead', id: '3', name: 'Jordan' })
const staff = buildSession({ role: 'Venue Staff', id: '4', name: 'Sam' })
const support = buildSession({ role: 'Technical Support', id: '6', name: 'Bryan' })
const attendee = buildSession({ role: 'Attendee', id: '20', name: 'Casey' })

const UNREACHABLE = new TypeError('Failed to fetch')

function event(overrides: Partial<EventRecord>): EventRecord {
  return {
    id: '7',
    title: 'Open Day',
    purpose: 'Welcome',
    description: '',
    startsAt: '2027-11-02T09:00',
    endsAt: '2027-11-02T17:00',
    expectedAttendance: 40,
    status: 'Submitted',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-10-01T09:00:00',
    updatedAt: '2026-10-01T09:00:00',
    history: [],
    ...overrides,
  }
}

const GREAT_HALL: VenueRecord = {
  id: '3',
  name: 'Great Hall',
  location: 'Main Campus',
  capacity: 500,
  facilities: '',
  accessibilityFeatures: '',
  operatingHours: '',
  supportedLayouts: '',
  createdAt: '2026-01-05T09:00:00',
  updatedAt: '2026-01-05T09:00:00',
}

beforeEach(() => {
  window.location.hash = ''
})

afterEach(() => {
  vi.resetAllMocks()
  vi.mocked(listNotifications).mockResolvedValue([])
})

describe('Events (US4.1)', () => {
  it('filters by status and opens an event in place', async () => {
    const user = userEvent.setup()
    vi.mocked(listEvents).mockResolvedValue([
      event({ id: '7', title: 'Open Day', status: 'Submitted' }),
      event({ id: '8', title: 'Alumni Night', status: 'Draft' }),
    ])
    render(<EventsPage session={organiser} />)
    const filters = await screen.findByRole('group', { name: 'Filter by status' })

    await user.click(within(filters).getByRole('button', { name: /Draft/ }))
    expect(screen.queryByText('Open Day')).not.toBeInTheDocument()

    await user.click(within(filters).getByRole('button', { name: 'All' }))
    await user.click(screen.getByText('Open Day'))

    expect(window.location.hash).toBe('#/events/7')
  })

  it('offers New event in the header and on an empty list', async () => {
    const user = userEvent.setup()
    vi.mocked(listEvents).mockResolvedValue([])
    render(<EventsPage session={organiser} />)
    await screen.findByText('No events yet')

    const [header, empty] = screen.getAllByRole('button', { name: 'New event' })
    await user.click(empty)
    expect(window.location.hash).toBe('#/events/new')

    window.location.hash = ''
    await user.click(header)
    expect(window.location.hash).toBe('#/events/new')
  })
})

describe('the landing page', () => {
  it.each([
    [null, 'Sign in', '#/signin'],
    [null, 'Create an event', '#/signin'],
    [organiser, 'Go to events', `#${organiser.home}`],
    [organiser, 'Create an event', '#/events/new'],
  ] as const)('%#: %s goes to %s', async (session, button, hash) => {
    const user = userEvent.setup()
    render(<LandingPage session={session} />)

    await user.click(screen.getByRole('button', { name: new RegExp(button) }))

    expect(window.location.hash).toBe(hash)
  })
})

describe('the top bar', () => {
  it('the brand goes home and Sign in goes to the form', async () => {
    const user = userEvent.setup()
    window.location.hash = '#/venues'
    render(<TopNav route="/venues" session={null} onSignOut={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(window.location.hash).toBe('#/signin')

    await user.click(document.querySelector('.topnav-brand')!)
    expect(window.location.hash).toBe('#/')
  })
})

describe('Attendee pages (US20.1, US20.2)', () => {
  const OPEN: OpenEvent = {
    id: '7',
    title: 'Open Day',
    startsAt: '',
    endsAt: '',
    venues: [],
    placesLeft: 5,
    registered: true,
  }

  it('an event with no date yet says so, and links to My Registrations', async () => {
    const user = userEvent.setup()
    vi.mocked(listOpenEvents).mockResolvedValue([OPEN, { ...OPEN, id: '8', startsAt: '2027-11-02T09:00', endsAt: '' }])
    render(<AttendPage session={attendee} />)

    expect(await screen.findByText('To be announced')).toBeInTheDocument()

    await user.click(screen.getAllByRole('link', { name: 'My Registrations' })[0])

    expect(window.location.hash).toBe('#/my-registrations')
  })

  it('a registration with no date says so; with none, it points to Upcoming Events', async () => {
    const user = userEvent.setup()
    const mine: MyRegistration = {
      id: '1',
      eventId: '7',
      title: 'Open Day',
      startsAt: '',
      endsAt: '',
      venues: [],
      status: 'Registered',
      name: 'Casey',
      email: 'casey@example.com',
      registeredAt: '2026-10-01T09:00:00',
      withdrawnAt: '',
      canWithdraw: true,
      canRegisterAgain: false,
      placesLeft: null,
    }
    vi.mocked(listMyRegistrations).mockResolvedValueOnce([
      mine,
      { ...mine, id: '2', startsAt: '2027-11-02T09:00' },
    ])
    const { unmount } = render(<MyRegistrationsPage session={attendee} />)
    expect(await screen.findByText('To be announced')).toBeInTheDocument()
    unmount()

    vi.mocked(listMyRegistrations).mockResolvedValueOnce([])
    render(<MyRegistrationsPage session={attendee} />)
    await user.click(await screen.findByRole('link', { name: 'Upcoming Events' }))

    expect(window.location.hash).toBe('#/attend')
  })
})

it('the equipment queue says when it could not be loaded (US19)', async () => {
  vi.mocked(listEquipmentQueue).mockRejectedValue(UNREACHABLE)
  render(<EquipmentQueuePage session={support} />)

  expect(await screen.findByText(/Could not load equipment requests/)).toBeInTheDocument()
})

describe('answers that land after the page has gone', () => {
  it.each([
    ['Notifications', () => render(<NotificationsPage session={organiser} />), listNotifications],
    ['the equipment queue', () => render(<EquipmentQueuePage session={support} />), listEquipmentQueue],
  ] as const)('%s ignores a failure', async (_page, show, call) => {
    let fail!: (error: Error) => void
    vi.mocked(call).mockReturnValueOnce(new Promise((_resolve, reject) => (fail = reject)) as never)
    const { unmount } = show()

    unmount()
    fail(UNREACHABLE)
    await Promise.resolve()

    expect(call).toHaveBeenCalledTimes(1)
  })

  it('the venue catalogue ignores a failure', async () => {
    let fail!: (error: Error) => void
    vi.mocked(listVenues).mockReturnValueOnce(new Promise((_resolve, reject) => (fail = reject)))
    const { unmount } = render(<VenuesPage session={staff} />)

    unmount()
    fail(UNREACHABLE)
    await Promise.resolve()

    expect(listVenues).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['the venue page', () => render(<VenueDetailPage venueId="3" session={staff} />)],
    ['the venue form', () => render(<VenueFormPage venueId="3" session={staff} />)],
  ])('%s ignores a venue', async (_page, show) => {
    let deliver!: (venue: VenueRecord | null) => void
    vi.mocked(getVenue).mockReturnValueOnce(new Promise((resolve) => (deliver = resolve)))
    const { unmount } = show()

    unmount()
    deliver(GREAT_HALL)
    await Promise.resolve()

    expect(getVenue).toHaveBeenCalledTimes(1)
  })

  it('the registration card ignores its settings', async () => {
    let deliver!: (settings: never) => void
    vi.mocked(getRegistrationSettings).mockReturnValueOnce(new Promise((resolve) => (deliver = resolve)))
    const { unmount } = render(
      <EventRegistration event={event({ status: 'Confirmed', coordinatorId: '2' })} session={organiser} />,
    )

    unmount()
    deliver({ eventId: '7', open: false } as never)
    await Promise.resolve()

    expect(getRegistrationSettings).toHaveBeenCalledTimes(1)
  })

  it('the queue still works when the coordinators cannot be loaded', async () => {
    vi.mocked(listUnassignedEvents).mockResolvedValue([
      {
        id: '7',
        title: 'Open Day',
        purpose: null,
        description: null,
        startsAt: null,
        expectedAttendance: null,
        status: 'Submitted',
        organiserId: '1',
        organiserName: 'Dylan',
        submittedAt: '2026-10-01T09:00:00',
        coordinatorId: null,
      },
    ])
    vi.mocked(listCoordinators).mockRejectedValue(UNREACHABLE)
    render(<UnassignedQueuePage session={lead} />)

    expect(await screen.findByText('Open Day')).toBeInTheDocument()
  })
})

describe('venue pages route in place (US9.1-9.3)', () => {
  it('from the catalogue: Add venue, a card, and Add venue on an empty catalogue', async () => {
    const user = userEvent.setup()
    vi.mocked(listVenues).mockResolvedValueOnce([GREAT_HALL])
    const { unmount } = render(<VenuesPage session={staff} />)

    await user.click(await screen.findByText('Great Hall'))
    expect(window.location.hash).toBe('#/venues/3')

    await user.click(screen.getByRole('button', { name: 'Add venue' }))
    expect(window.location.hash).toBe('#/venues/new')
    unmount()

    window.location.hash = ''
    vi.mocked(listVenues).mockResolvedValueOnce([])
    render(<VenuesPage session={staff} />)
    await screen.findByText('No venues yet')
    const [, emptyState] = screen.getAllByRole('button', { name: 'Add venue' })
    await user.click(emptyState)
    expect(window.location.hash).toBe('#/venues/new')
  })

  it('clears the filters from a search that found nothing', async () => {
    const user = userEvent.setup()
    vi.mocked(listVenues).mockResolvedValue([])
    render(<VenuesPage session={staff} />)

    await user.type(await screen.findByLabelText(/Minimum capacity/), '900')
    await user.click(screen.getByRole('button', { name: /Search|Apply/ }))
    await user.click(await screen.findByRole('button', { name: 'Clear filters' }))

    await waitFor(() => expect(listVenues).toHaveBeenLastCalledWith(staff, expect.objectContaining({ minCapacity: '' })))
  })

  it('from a venue: back, edit, and back from a missing one', async () => {
    const user = userEvent.setup()
    vi.mocked(getVenue).mockResolvedValueOnce(GREAT_HALL)
    const { unmount } = render(<VenueDetailPage venueId="3" session={staff} />)

    await user.click(await screen.findByRole('button', { name: 'Edit venue' }))
    expect(window.location.hash).toBe('#/venues/3/edit')

    await user.click(screen.getByRole('link', { name: /Back|venues/i }))
    expect(window.location.hash).toBe('#/venues')
    unmount()

    window.location.hash = ''
    vi.mocked(getVenue).mockResolvedValueOnce(null)
    render(<VenueDetailPage venueId="99" session={staff} />)
    await screen.findByText('That venue is not in the catalogue.')
    await user.click(screen.getAllByRole('button')[0])
    expect(window.location.hash).toBe('#/venues')
  })

  it('from the form: back, cancel, and back from a missing venue', async () => {
    const user = userEvent.setup()
    vi.mocked(getVenue).mockResolvedValueOnce(GREAT_HALL)
    const { unmount } = render(<VenueFormPage venueId="3" session={staff} />)

    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(window.location.hash).toBe('#/venues/3')

    await user.click(screen.getByRole('link', { name: /Back|venue/i }))
    expect(window.location.hash).toBe('#/venues/3')
    unmount()

    window.location.hash = ''
    vi.mocked(getVenue).mockResolvedValueOnce(null)
    render(<VenueFormPage venueId="99" session={staff} />)
    await screen.findByText('Venue not found')
    await user.click(screen.getAllByRole('button')[0])
    expect(window.location.hash).toBe('#/venues')
  })
})

describe('sign-in fallbacks (US1.1)', () => {
  async function signIn() {
    const user = userEvent.setup()
    render(<SignInPage onSignedIn={() => {}} notice="" />)
    await user.type(screen.getByLabelText(/Email/), 'organiser@spmg3t7.edu')
    await user.type(screen.getByLabelText(/Password/), 'Sprint1!demo')
    await user.click(screen.getByRole('button', { name: /Sign in/ }))
  }

  it("shows the API's own message for a failure that is not a credential problem", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError('The API is restarting.', 'unknown', 503))
    await signIn()

    expect(await screen.findByText('The API is restarting.')).toBeInTheDocument()
  })

  it('says something went wrong when what failed is not even an error', async () => {
    vi.mocked(login).mockRejectedValue('boom')
    await signIn()

    expect(await screen.findByText('Something went wrong. Try again.')).toBeInTheDocument()
  })
})

it('Team assignments lists unassigned events first, whatever order they arrive in (US8.5)', async () => {
  vi.mocked(listEvents).mockResolvedValue([
    event({ id: '7', coordinatorId: '2', coordinatorName: 'Priya Nair' }),
    event({ id: '8', coordinatorId: undefined }),
    event({ id: '9', coordinatorId: '5', coordinatorName: 'Alex Lim' }),
  ])
  render(<TeamAssignmentsPage session={lead} />)

  const options = await screen.findAllByRole('option')
  const names = options.map((option) => option.textContent ?? '')
  expect(names).toEqual([
    'All Coordinators (3)',
    'Unassigned (1)',
    'Alex Lim (1)',
    'Priya Nair (1)',
  ])
})

it('the reservation card reloads availability on request (US19.3)', async () => {
  const user = userEvent.setup()
  vi.mocked(getEquipmentAvailability).mockResolvedValue([])
  const request = {
    id: '17',
    version: 3,
    quantity: 1,
    requestedEquipmentId: '5',
    status: 'Requested',
  } as EquipmentRequest
  render(
    <EquipmentReservation request={request} session={support} onRefresh={async () => {}} onDecided={() => {}} />,
  )
  await screen.findByText(/No item has been selected/)

  await user.click(screen.getByRole('button', { name: 'Refresh availability' }))

  await waitFor(() => expect(getEquipmentAvailability).toHaveBeenCalledTimes(2))
})
