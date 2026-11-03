import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import { MISSING_MESSAGES, NO_NEEDS, NOT_REQUIRED } from '../eventNeeds'
import {
  EventRuleError,
  approveSafetyCheck,
  cancelEvent,
  completeEvent,
  getEvent,
  getSafetyReadiness,
  getSafetyReview,
  listBookings,
  saveEvent,
  sendForSafetyCheck,
  submitEvent,
  type EventRecord,
} from '../eventsStore'
import { getRegistrationSettings } from '../registrationStore'
import { ANSWERED_NEEDS } from '../test/eventNeeds'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  listBookings: vi.fn(async () => []),
  getEvent: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
  completeEvent: vi.fn(),
  // US4.6: cancelling from the page.
  cancelEvent: vi.fn(),
  // US4.4: the safety check panel loads its own readiness.
  getSafetyReadiness: vi.fn(async () => ({ ready: true, reason: '', message: '' })),
  sendForSafetyCheck: vi.fn(),
  approveSafetyCheck: vi.fn(),
  // US17.1: the Safety Officer's review loads its own data; left pending here.
  getSafetyReview: vi.fn(() => new Promise(() => {})),
  // US17.2: the panel reads the earlier decisions. None, unless a test says so.
  listSafetyDecisions: vi.fn(async () => []),
}))

// US14.1: the venue bookings card loads its own data. These tests are not about
// it, so it gets no bookings and an empty catalogue. The empty answers are the
// mocks' own implementations rather than a beforeEach, because the card mounts
// only once the event has loaded and its effect can run after this file's
// resetAllMocks; a reset restores an implementation given to vi.fn.
vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listVenues: vi.fn(async () => []),
}))

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEventEquipmentRequests: vi.fn(async () => []),
  listEquipment: vi.fn(async () => []),
}))

// US20.1: the registration card loads its own settings. Off, as on a new event,
// for the same reason the cards above get empty answers.
vi.mock('../registrationStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../registrationStore')>()),
  getRegistrationSettings: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    defaultCapacity: 20,
  })),
  // US20.3: and, for the Organiser and the assigned Coordinator, who registered.
  listEventRegistrations: vi.fn(async (eventId: string) => ({
    eventId,
    open: false,
    capacity: null,
    registered: 0,
    placesLeft: null,
    registrations: [],
  })),
}))

const getEventMock = vi.mocked(getEvent)
const saveEventMock = vi.mocked(saveEvent)
const submitEventMock = vi.mocked(submitEvent)
const completeEventMock = vi.mocked(completeEvent)
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

it('shows a failed event load and retries without leaving the page stuck loading', async () => {
  const user = userEvent.setup()
  getEventMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValue(event)
  render(<EventDetailPage eventId="101" session={organiser} />)
  expect(await screen.findByRole('alert')).toHaveTextContent(/could not load this event/i)
  expect(screen.queryByText(/Loading event/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry loading event' }))
  expect(await screen.findByLabelText('Title')).toHaveValue(event.title)
  expect(getEventMock).toHaveBeenCalledTimes(2)
})

const event: EventRecord = {
  id: '101',
  title: 'Working title',
  purpose: 'Purpose',
  description: 'Notes',
  startsAt: '2026-11-02T18:00',
  endsAt: undefined,
  expectedAttendance: 20,
  status: 'Draft',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:00:00',
  history: [],
}

// Fixture events are dated November 2026. Against the real clock they would
// start failing as "in the past" once those days went by, so today is pinned
// before all of them. Only Date is faked: timers stay real for user-event.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-01T09:00:00') })
})

afterEach(() => {
  vi.useRealTimers()
  vi.resetAllMocks()
})

it('saves a description-only edit without trimming its whitespace', async () => {
  const user = userEvent.setup()
  const saved = {
    ...event,
    title: '',
    purpose: '',
    description: '  Continue planning here.  ',
    startsAt: '',
    expectedAttendance: null,
  }
  getEventMock.mockResolvedValue(event)
  saveEventMock.mockResolvedValue(saved)

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.clear(await screen.findByLabelText('Title'))
  await user.clear(screen.getByLabelText('Purpose'))
  await user.clear(screen.getByLabelText('Description'))
  await user.clear(screen.getByLabelText('Starts'))
  await user.clear(screen.getByLabelText('Expected attendance'))
  await user.type(screen.getByLabelText('Description'), '  Continue planning here.  ')
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(saveEventMock).toHaveBeenCalled())
  expect(saveEventMock).toHaveBeenCalledWith(
    '101',
    {
      title: '',
      purpose: '',
      description: '  Continue planning here.  ',
      startsAt: '',
      endsAt: null,
      expectedAttendance: null,
      ...NO_NEEDS,
    },
    organiser,
  )
})

it('rejects punctuation-only edits as an empty draft', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({
    ...event,
    title: '',
    purpose: '',
    description: '',
    startsAt: '',
    expectedAttendance: null,
  })

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.type(await screen.findByLabelText('Description'), '---')
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/at least one letter or number/i)
  expect(saveEventMock).not.toHaveBeenCalled()
})

it('keeps submission strict for a titleless partial draft', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({
    ...event,
    title: '',
    description: 'Planning notes',
  })

  render(<EventDetailPage eventId="101" session={organiser} />)

  expect(await screen.findByRole('heading', { name: 'Untitled event' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Submit event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the event a title.')
  expect(saveEventMock).not.toHaveBeenCalled()
  expect(submitEventMock).not.toHaveBeenCalled()
})

const coordinator = buildSession({ role: 'Event Coordinator', id: '9', name: 'Priya' })

const submittedEvent: EventRecord = {
  id: '101',
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks.',
  startsAt: '2026-11-02T18:00',
  expectedAttendance: 120,
  status: 'Submitted',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:05:00',
  history: [
    { from: null, to: 'Draft', at: '2026-09-08T10:00:00', byId: '1', byName: 'Dylan' },
    { from: 'Draft', to: 'Submitted', at: '2026-09-08T10:05:00', byId: '1', byName: 'Dylan' },
  ],
}

it('shows every captured field as read-only text to a Coordinator', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Faculty Welcome Night')).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Dylan/)).toBeInTheDocument()
  expect(screen.getByText('Welcome the new intake.')).toBeInTheDocument()
  expect(screen.getByText('Talks.')).toBeInTheDocument()
  expect(screen.getByText('120 people')).toBeInTheDocument()
})

it('does not render a Draft if an invalid API response returns one to a Coordinator', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Draft' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Not available for your role')).toBeInTheDocument()
  expect(screen.queryByText('Faculty Welcome Night')).not.toBeInTheDocument()
})

it('offers no edit actions to a Coordinator, who does not own the event', async () => {
  // Narrowed by US7.3: a Coordinator does now get one input on this page, the
  // clarification box. What they still cannot do is edit or submit the event.
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('button', { name: /save draft/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /submit event/i })).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/^title$/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/^purpose$/i)).not.toBeInTheDocument()
  expect(
    screen.getByText(/only the owning Organiser can edit or submit it/i),
  ).toBeInTheDocument()
})

it('shows the full status history, not just the current status', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Faculty Welcome Night')
  expect(screen.getByText('Created as')).toBeInTheDocument()
  expect(screen.getAllByText('Submitted').length).toBeGreaterThan(0)
})

it('shows when the event was created, in Singapore time', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, createdAt: '2026-10-22T15:51:40' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  // created_at is naive UTC, so 15:51 there is 23:51 in Singapore.
  expect(await screen.findByText(/Created 22 Oct 2026, 23:51/)).toBeInTheDocument()
})

it.each([coordinator, organiser])('keeps status history about event transitions for %s', async (session) => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Planning', coordinatorId: coordinator.id })
  render(<EventDetailPage eventId="101" session={session} />)
  expect(await screen.findByRole('heading', { name: 'Status history' })).toBeInTheDocument()
  expect(screen.getByText('Event status transitions and requested changes.')).toBeInTheDocument()
  const entries = document.querySelectorAll('ol.timeline > li')
  expect(entries[0]).toHaveTextContent('Created as')
  expect(entries[0]).toHaveTextContent('Status: Draft')
  expect(screen.queryByText(/Microphone request/)).not.toBeInTheDocument()
})

it('shows the venue bookings for a submitted event under its details (US14.1)', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Venue bookings' })).toBeInTheDocument()
  await waitFor(() => expect(vi.mocked(listBookings)).toHaveBeenCalledWith('101', coordinator))
})

it('shows no venue bookings card on a Draft, which cannot have any', async () => {
  getEventMock.mockResolvedValue(event)

  render(<EventDetailPage eventId="101" session={organiser} />)

  await screen.findByLabelText('Title')
  expect(screen.queryByRole('heading', { name: 'Venue bookings' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Equipment requests' })).not.toBeInTheDocument()
  expect(vi.mocked(listBookings)).not.toHaveBeenCalled()
})

it('shows the registration card for a submitted event, and none on a Draft (US20.1)', async () => {
  getEventMock.mockResolvedValue(submittedEvent)
  const { unmount } = render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByRole('heading', { name: 'Registration' })).toBeInTheDocument()
  expect(await screen.findByText('Registration is off.')).toBeInTheDocument()
  await waitFor(() =>
    expect(vi.mocked(getRegistrationSettings)).toHaveBeenCalledWith('101', coordinator),
  )
  unmount()

  getEventMock.mockResolvedValue(event)
  render(<EventDetailPage eventId="101" session={organiser} />)
  await screen.findByLabelText('Title')
  expect(screen.queryByRole('heading', { name: 'Registration' })).not.toBeInTheDocument()
})

it('lets the assigned Coordinator complete an ended Confirmed event', async () => {
  const user = userEvent.setup()
  const confirmed = {
    ...submittedEvent, status: 'Confirmed' as const,
    coordinatorId: coordinator.id, endsAt: '2020-01-01T17:00',
  }
  getEventMock.mockResolvedValue(confirmed)
  completeEventMock.mockResolvedValue({ ...confirmed, status: 'Completed' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Mark Completed' }))
  expect(completeEventMock).toHaveBeenCalledWith('101', coordinator)
  expect(await screen.findByRole('status')).toHaveTextContent('Completed.')
  expect(screen.queryByRole('button', { name: 'Mark Completed' })).not.toBeInTheDocument()
})

it('does not offer completion before the end time or to another Coordinator', async () => {
  const future = {
    ...submittedEvent, status: 'Confirmed' as const,
    coordinatorId: coordinator.id, endsAt: '2099-01-01T17:00',
  }
  getEventMock.mockResolvedValue(future)
  const view = render(<EventDetailPage eventId="101" session={coordinator} />)
  expect(await screen.findByRole('button', { name: 'Mark Completed' })).toBeDisabled()

  view.unmount()
  getEventMock.mockResolvedValue({ ...future, coordinatorId: 'someone-else' })
  render(<EventDetailPage eventId="101" session={coordinator} />)
  await screen.findByText('Faculty Welcome Night')
  expect(screen.queryByRole('button', { name: 'Mark Completed' })).not.toBeInTheDocument()
})

// --- US5.3: a Confirmed event's details are locked -------------------------------

describe('US5.3: a Confirmed event is locked', () => {
  // The server gives Coordinators events:edit (US5.2); test/sessions.ts does not
  // yet, so these tests add it.
  const editor = { ...coordinator, permissions: [...coordinator.permissions, 'events:edit' as const] }
  const confirmedEvent = {
    ...submittedEvent,
    status: 'Confirmed' as const,
    coordinatorId: coordinator.id,
    endsAt: '2099-01-01T17:00',
  }

  it('shows a Coordinator the details read-only, with no Save, and says why', async () => {
    getEventMock.mockResolvedValue(confirmedEvent)

    render(<EventDetailPage eventId="101" session={editor} />)

    expect(
      await screen.findByText(
        'This event is confirmed. Changes need to go through a change request. The Organiser requests them, and you review them here.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    expect(screen.queryByText(/You are editing this event/)).not.toBeInTheDocument()
  })

  it('points the Organiser to a change request', async () => {
    getEventMock.mockResolvedValue(confirmedEvent)

    render(<EventDetailPage eventId="101" session={organiser} />)

    expect(
      await screen.findByText(
        'This event is confirmed. Changes need to go through a change request. Request changes and the Coordinator will review them.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeInTheDocument()
  })

  it('still lets a Coordinator edit a Planning event', async () => {
    getEventMock.mockResolvedValue({ ...confirmedEvent, status: 'Planning' })

    render(<EventDetailPage eventId="101" session={editor} />)

    expect(await screen.findByLabelText('Title')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })
})

// --- US2.1 (Sprint 3): the customer's mandatory event needs ----------------------

const answeredDraft: EventRecord = {
  ...event,
  description: 'Talks and a campus tour.',
  endsAt: '2026-11-02T21:00',
  ...ANSWERED_NEEDS,
}

it('shows each need as read-only text, and says when one is not stated', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, ...ANSWERED_NEEDS, equipmentNeeds: '' })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  expect(await screen.findByText('Venue requirements')).toBeInTheDocument()
  expect(screen.getByText('Stage, Projector')).toBeInTheDocument()
  expect(screen.getByText('Theatre')).toBeInTheDocument()
  expect(screen.getByText('Wheelchair access')).toBeInTheDocument()
  expect(screen.getByText(NOT_REQUIRED)).toBeInTheDocument()
  const equipment = screen.getByText('Equipment needs')
  expect(equipment.nextElementSibling).toHaveTextContent('Not stated.')
})

it('reads every need as not stated on an event saved before they existed', async () => {
  getEventMock.mockResolvedValue(submittedEvent)

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByText('Registration needs')
  expect(screen.getAllByText('Not stated.')).toHaveLength(5)
})

it('fills the draft form with the event’s needs and saves a changed one', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue(answeredDraft)
  saveEventMock.mockResolvedValue({ ...answeredDraft, preferredLayout: 'Banquet' })

  render(<EventDetailPage eventId="101" session={organiser} />)

  const layout = await screen.findByLabelText('Preferred layout')
  expect(layout).toHaveValue('Theatre')
  // Nothing has changed yet, so there is nothing to save.
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled()

  await user.selectOptions(layout, 'Banquet')
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(saveEventMock).toHaveBeenCalled())
  expect(saveEventMock.mock.calls[0][1]).toEqual(
    expect.objectContaining({ ...ANSWERED_NEEDS, preferredLayout: 'Banquet' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Saved. Status is still Draft.')
})

it('saves a draft with needs left unanswered', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue(event)
  saveEventMock.mockResolvedValue(event)

  render(<EventDetailPage eventId="101" session={organiser} />)

  const access = await screen.findByRole('group', { name: 'Accessibility needs' })
  await user.click(within(access).getByLabelText('Lift'))
  await user.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(saveEventMock).toHaveBeenCalled())
  expect(saveEventMock.mock.calls[0][1]).toEqual(
    expect.objectContaining({ ...NO_NEEDS, accessibilityNeeds: 'Lift' }),
  )
})

it.each([
  ['venueRequirements' as const],
  ['preferredLayout' as const],
  ['accessibilityNeeds' as const],
  ['equipmentNeeds' as const],
  ['registrationNeeds' as const],
])('blocks submitting a draft whose %s is unanswered, and says so', async (key) => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({ ...answeredDraft, [key]: '' })

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.click(await screen.findByRole('button', { name: 'Submit event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(MISSING_MESSAGES[key])
  expect(saveEventMock).not.toHaveBeenCalled()
  expect(submitEventMock).not.toHaveBeenCalled()
})

it('blocks submitting a draft with no description', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({ ...answeredDraft, description: '' })

  render(<EventDetailPage eventId="101" session={organiser} />)

  await user.click(await screen.findByRole('button', { name: 'Submit event' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the event a description.')
  expect(submitEventMock).not.toHaveBeenCalled()
})

it('submits a complete draft with its needs, trimming the described ones', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue(answeredDraft)
  saveEventMock.mockResolvedValue(answeredDraft)
  submitEventMock.mockResolvedValue({ ...answeredDraft, status: 'Submitted' })

  render(<EventDetailPage eventId="101" session={organiser} />)

  const registration = await screen.findByRole('group', { name: 'Registration needs' })
  await user.click(within(registration).getByLabelText(NOT_REQUIRED))
  await user.type(within(registration).getByRole('textbox'), '  Online sign-up  ')
  await user.click(screen.getByRole('button', { name: 'Submit event' }))

  await waitFor(() => expect(submitEventMock).toHaveBeenCalledWith('101', organiser))
  expect(saveEventMock.mock.calls[0][1]).toEqual(
    expect.objectContaining({ ...ANSWERED_NEEDS, registrationNeeds: 'Online sign-up' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent('Submitted.')
})

/* ---------- US4.4: Pending Safety Check ---------- */

const officer = buildSession({ role: 'Safety Officer', id: '5', name: 'Alex' })

it('lets the assigned Coordinator send a ready Planning event for its safety check', async () => {
  const user = userEvent.setup()
  const planning = { ...submittedEvent, status: 'Planning' as const, coordinatorId: coordinator.id }
  getEventMock.mockResolvedValue(planning)
  vi.mocked(sendForSafetyCheck).mockResolvedValue({
    ...planning,
    status: 'Pending Safety Check',
  })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Send for safety check' }))

  expect(vi.mocked(getSafetyReadiness)).toHaveBeenCalledWith('101', coordinator)
  expect(await screen.findByText(/The event is now Pending Safety Check\./)).toBeInTheDocument()
  expect(screen.getByText(/Waiting for the Safety Officer/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Send for safety check' })).not.toBeInTheDocument()
})

it('shows the Safety Officer the decision, but not the bookings or equipment cards', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Pending Safety Check' })

  render(<EventDetailPage eventId="101" session={officer} />)

  expect(await screen.findByRole('heading', { name: 'Safety check decision' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '← Safety review' })).toHaveAttribute(
    'href',
    '#/safety-review',
  )
  expect(screen.queryByRole('heading', { name: 'Venue bookings' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Equipment requests' })).not.toBeInTheDocument()
  expect(vi.mocked(listBookings)).not.toHaveBeenCalled()
})

it('US17.2 shows an approved safety check as awaiting the Coordinator', async () => {
  getEventMock.mockResolvedValue({
    ...submittedEvent,
    status: 'Pending Safety Check',
    safetyApproved: true,
  })

  render(<EventDetailPage eventId="101" session={officer} />)

  expect(
    await screen.findByText('Safety approved, awaiting Coordinator confirmation'),
  ).toBeInTheDocument()
  expect(
    screen.getByText(/You approved this safety check\. The Coordinator confirms the event/),
  ).toBeInTheDocument()
})

it('takes the Safety Officer back to their queue', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Pending Safety Check' })

  render(<EventDetailPage eventId="101" session={officer} />)
  await user.click(await screen.findByRole('link', { name: '← Safety review' }))

  expect(window.location.hash).toBe('#/safety-review')
})

/** US17.2: a decision waits for the review it is made on, so these tests load one. */
const WAITING_SINCE = '2026-10-20T09:00:00'
const loadedReview = () =>
  vi.mocked(getSafetyReview).mockResolvedValue({
    eventId: '101', title: submittedEvent.title, status: 'Pending Safety Check',
    startsAt: '', endsAt: '', expectedAttendance: null, accessibilityNeeds: '',
    preferredLayout: '', venueRequirements: '', waitingSince: WAITING_SINCE,
    venues: [], equipment: [],
  })

/** The approve button, once the review has loaded and enabled it. */
async function approveButton() {
  const button = await screen.findByRole('button', { name: 'Approve safety check' })
  await waitFor(() => expect(button).toBeEnabled())
  return button
}

it('shows the Safety Officer the outcome of their approval', async () => {
  const user = userEvent.setup()
  const pending = { ...submittedEvent, status: 'Pending Safety Check' as const }
  getEventMock.mockResolvedValue(pending)
  loadedReview()
  vi.mocked(approveSafetyCheck).mockResolvedValue({ ...pending, safetyApproved: true })

  render(<EventDetailPage eventId="101" session={officer} />)
  await user.click(await approveButton())

  expect(vi.mocked(approveSafetyCheck)).toHaveBeenCalledWith('101', WAITING_SINCE, officer)

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Approved. The Coordinator confirms the event once everything else is in place.',
  )
  expect(screen.queryByRole('heading', { name: 'Safety check decision' })).not.toBeInTheDocument()
  // US4.7: the event waits for its Coordinator now, and the page says so.
  expect(screen.getByText(/You approved this safety check/)).toBeInTheDocument()
})

it('shows the Safety Officer why a decision was refused', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Pending Safety Check' })
  loadedReview()
  vi.mocked(approveSafetyCheck).mockRejectedValue(
    new EventRuleError('This safety check was already decided. Refresh it and try again.'),
  )

  render(<EventDetailPage eventId="101" session={officer} />)
  await user.click(await approveButton())

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'This safety check was already decided. Refresh it and try again.',
  )
})

it('refuses the Safety Officer an event that is no longer waiting for them', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Confirmed' })

  render(<EventDetailPage eventId="101" session={officer} />)

  expect(await screen.findByRole('heading', { name: 'Not available for your role' })).toBeInTheDocument()
})

it('sends the Safety Officer back to their queue from a missing event', async () => {
  const user = userEvent.setup()
  getEventMock.mockResolvedValue(null)

  render(<EventDetailPage eventId="101" session={officer} />)
  await user.click(await screen.findByRole('button', { name: 'Back to safety review' }))

  expect(window.location.hash).toBe('#/safety-review')
})

/* ---------- US17.1: the Safety Officer's read-only review ---------- */

it('shows the Safety Officer the safety review of a waiting event', async () => {
  getEventMock.mockResolvedValue({ ...submittedEvent, status: 'Pending Safety Check' })

  render(<EventDetailPage eventId="101" session={officer} />)

  expect(await screen.findByRole('heading', { name: 'Safety review' })).toBeInTheDocument()
  expect(vi.mocked(getSafetyReview)).toHaveBeenCalledWith('101', officer)
  // Read-only: the details are not an editable form for them.
  expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
})

it('shows no safety review to anyone else', async () => {
  getEventMock.mockResolvedValue({
    ...submittedEvent, status: 'Pending Safety Check', coordinatorId: coordinator.id,
  })

  render(<EventDetailPage eventId="101" session={coordinator} />)

  await screen.findByRole('heading', { name: 'Safety check' })
  expect(screen.queryByRole('heading', { name: 'Safety review' })).not.toBeInTheDocument()
  expect(vi.mocked(getSafetyReview)).not.toHaveBeenCalled()
})

/* ---------- US4.6: cancelling an event ---------- */

const cancelledBy = (byName: string, byId: string) => ({
  from: 'Planning' as const,
  to: 'Cancelled' as const,
  at: '2026-10-21T09:00:00',
  byId,
  byName,
  notes: 'Funding was withdrawn.',
  kind: 'cancellation' as const,
})

it('lets the assigned Coordinator cancel the event, and then shows it read-only', async () => {
  const user = userEvent.setup()
  const planning = { ...submittedEvent, status: 'Planning' as const, coordinatorId: coordinator.id }
  getEventMock.mockResolvedValue(planning)
  vi.mocked(cancelEvent).mockResolvedValue({
    ...planning,
    status: 'Cancelled',
    history: [...planning.history, cancelledBy('Priya', coordinator.id)],
  })

  render(<EventDetailPage eventId="101" session={coordinator} />)
  await user.click(await screen.findByRole('button', { name: 'Cancel this event…' }))
  await user.type(
    screen.getByLabelText('Why is this event being cancelled?'),
    'Funding was withdrawn.',
  )
  await user.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

  expect(vi.mocked(cancelEvent)).toHaveBeenCalledWith('101', 'Funding was withdrawn.', coordinator)
  expect(await screen.findByRole('status')).toHaveTextContent(/^Cancelled\. Its venue bookings/)
  const notice = screen.getByRole('note')
  expect(notice).toHaveTextContent(/Cancelled by Priya on/)
  expect(notice).toHaveTextContent('Reason: Funding was withdrawn.')
  expect(screen.queryByRole('heading', { name: 'Cancel event' })).not.toBeInTheDocument()
  // The history labels the note as the reason, not as a request.
  expect(screen.getByText('Cancellation reason')).toBeInTheDocument()
  // The bookings card reloads, so it shows what the cancellation released.
  await waitFor(() => expect(vi.mocked(listBookings)).toHaveBeenCalledTimes(2))
})

it('shows the owning Organiser a cancelled event as read-only, with nothing waiting', async () => {
  getEventMock.mockResolvedValue({
    ...submittedEvent,
    status: 'Cancelled',
    coordinatorId: coordinator.id,
    // US11.1: left waiting when the event was cancelled; nobody can answer it now.
    changeRequested: true,
    pendingChanges: [
      { field: 'name', label: 'Title', oldValue: 'A', newValue: 'B', important: false },
    ],
    history: [...submittedEvent.history, cancelledBy('Dylan', organiser.id)],
  })

  render(<EventDetailPage eventId="101" session={organiser} />)

  expect(await screen.findByRole('note')).toHaveTextContent('This event is read-only.')
  expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Requested changes' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Cancel this event…' })).not.toBeInTheDocument()
  expect(screen.queryByText(/has already been decided/)).not.toBeInTheDocument()
})

it('lets the Organiser cancel their own Draft', async () => {
  getEventMock.mockResolvedValue(event)

  render(<EventDetailPage eventId="101" session={organiser} />)

  expect(await screen.findByRole('button', { name: 'Cancel this event…' })).toBeInTheDocument()
})

it('gives an editing Coordinator no form on a cancelled event', async () => {
  // The server grants Coordinators events:edit (US5.2); the shared test
  // session leaves it out, so it is added here to reach the editable path.
  const editor = buildSession({
    role: 'Event Coordinator',
    id: coordinator.id,
    permissions: [...coordinator.permissions, 'events:edit'],
  })
  getEventMock.mockResolvedValue({
    ...submittedEvent,
    status: 'Cancelled',
    coordinatorId: editor.id,
    history: [...submittedEvent.history, cancelledBy('Priya', editor.id)],
  })

  render(<EventDetailPage eventId="101" session={editor} />)

  expect(await screen.findByRole('note')).toHaveTextContent('This event is read-only.')
  expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Changes are tracked and logged/)).not.toBeInTheDocument()
})


it.each(['Completed', 'Rejected'] as const)('keeps %s events read-only for Coordinators with edit permission', async (status) => {
  const editor = { ...coordinator, permissions: [...coordinator.permissions, 'events:edit' as const] }
  getEventMock.mockResolvedValue({ ...submittedEvent, status, coordinatorId: editor.id })
  render(<EventDetailPage eventId="101" session={editor} />)
  await screen.findByRole('heading', { name: submittedEvent.title })
  expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
})
