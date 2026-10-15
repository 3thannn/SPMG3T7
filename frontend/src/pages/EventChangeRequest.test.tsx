/**
 * US11.1 on the event detail page — an Organiser requests changes to a
 * submitted event, and the Coordinator reviews them.
 *
 * Whether a request is allowed, what counts as a change and which changes are
 * important are the server's call, tested in
 * backend/tests/test_change_requests.py. This page's job, asserted here:
 *
 * AC1  the Organiser can open the existing edit form on their submitted event;
 * AC2  they can edit the permitted details and submit them for review — the
 *      page sends what was typed and shows the event Under Review;
 * AC3  the proposed changes are visible to the Coordinator;
 * AC4  important changes are identified as such;
 * AC5  the Coordinator can review them and approve or reject before deciding.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import {
  EventRuleError,
  approveEventChange,
  getEvent,
  rejectEventChange,
  requestEventChange,
  saveEvent,
  submitEvent,
  type EventRecord,
  type ProposedChange,
} from '../eventsStore'
import { ApiError } from '../api'
import { formatTimestamp } from '../status'
import { ANSWERED_NEEDS } from '../test/eventNeeds'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getEvent: vi.fn(),
  requestEventChange: vi.fn(),
  approveEventChange: vi.fn(),
  rejectEventChange: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
}))

vi.mock('../components/EventBookings', () => ({
  default: () => null,
}))

vi.mock('../components/EventEquipment', () => ({ default: () => null }))

const getEventMock = vi.mocked(getEvent)
const requestEventChangeMock = vi.mocked(requestEventChange)
const approveEventChangeMock = vi.mocked(approveEventChange)
const rejectEventChangeMock = vi.mocked(rejectEventChange)
const saveEventMock = vi.mocked(saveEvent)
const submitEventMock = vi.mocked(submitEvent)

afterEach(() => {
  vi.resetAllMocks()
})

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const coordinator = buildSession({
  role: 'Event Coordinator',
  id: '2',
  name: 'Priya',
  email: 'priya@example.edu',
})

function submitted(overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Faculty Welcome Night',
    purpose: 'Welcome the new intake.',
    description: 'Talks.',
    startsAt: '2027-11-02T18:00',
    endsAt: '2027-11-02T21:00',
    expectedAttendance: 120,
    ...ANSWERED_NEEDS,
    status: 'Submitted',
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2026-09-01T09:00:00',
    updatedAt: '2026-09-02T09:00:00',
    changeRequested: false,
    pendingChanges: [],
    history: [
      { from: null, to: 'Draft', at: '2026-09-01T09:00:00', byId: '1', byName: 'Dylan' },
      {
        from: 'Draft',
        to: 'Submitted',
        at: '2026-09-02T09:00:00',
        byId: '1',
        byName: 'Dylan',
        notes: '',
      },
    ],
    ...overrides,
  }
}

const TITLE_CHANGE: ProposedChange = {
  field: 'name',
  label: 'Title',
  oldValue: 'Faculty Welcome Night',
  newValue: 'Welcome Night',
  important: false,
}
const DATE_CHANGE: ProposedChange = {
  field: 'proposed_date',
  label: 'Starts',
  oldValue: '2027-11-02T18:00',
  newValue: '2027-11-02T19:00',
  important: true,
}
const ATTENDANCE_CHANGE: ProposedChange = {
  field: 'expected_attendance',
  label: 'Expected attendance',
  oldValue: '120',
  newValue: '150',
  important: true,
}
const CLEARED_END: ProposedChange = {
  field: 'end_date',
  label: 'Ends',
  oldValue: '2027-11-02T21:00',
  newValue: '',
  important: true,
}

/** The same event once the Organiser has asked for changes. */
function pending(
  changes: ProposedChange[] = [TITLE_CHANGE, DATE_CHANGE],
  note = 'Moved to 19:00.',
): EventRecord {
  const base = submitted()
  return {
    ...base,
    status: 'Under Review',
    changeRequested: true,
    pendingChanges: changes,
    history: [
      ...base.history,
      {
        from: 'Submitted',
        to: 'Under Review',
        at: '2026-09-03T09:00:00',
        byId: '1',
        byName: 'Dylan',
        notes: note,
        kind: 'change-request',
      },
    ],
  }
}

const ANSWERED_AT = '2026-09-04T09:00:00'

/**
 * The event after the Coordinator has answered the request. The answer is on
 * `lastChangeReview`, not in the history: the status did not move.
 */
function answered(approved: boolean, note: string): EventRecord {
  const base = pending()
  return {
    ...base,
    title: approved ? 'Welcome Night' : base.title,
    changeRequested: false,
    pendingChanges: [],
    lastChangeReview: {
      outcome: approved ? 'approved' : 'rejected', at: ANSWERED_AT, note,
      requestNote: 'Please adjust the welcome programme.',
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function openAs(session = organiser, event = submitted()) {
  getEventMock.mockResolvedValue(event)
  render(<EventDetailPage eventId={event.id} session={session} />)
  await screen.findByRole('heading', { level: 1 })
}

async function openProposalForm() {
  const user = userEvent.setup()
  await openAs()
  await user.click(screen.getByRole('button', { name: 'Request changes' }))
  return user
}

// --- AC1: the Organiser opens the existing edit form ---------------------------

describe('AC1 — opening the edit form on a submitted event', () => {
  it('offers the owner "Request changes" instead of editing or submitting', async () => {
    await openAs()

    expect(screen.getByRole('button', { name: 'Request changes' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Submit event' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(
      screen.getByText(/no longer edited directly\. Request changes and the Coordinator/),
    ).toBeInTheDocument()
  })

  it('opens the same edit form, filled with the current details', async () => {
    await openProposalForm()

    expect(screen.getByLabelText('Title')).toHaveValue('Faculty Welcome Night')
    expect(screen.getByLabelText('Starts')).toHaveValue('2027-11-02T18:00')
    expect(screen.getByLabelText('Ends')).toHaveValue('2027-11-02T21:00')
    expect(screen.getByLabelText('Purpose')).toHaveValue('Welcome the new intake.')
    expect(screen.getByLabelText('Expected attendance')).toHaveValue(120)
    expect(screen.getByLabelText('Description')).toHaveValue('Talks.')
    expect(screen.getByLabelText('Note for the Coordinator (optional)')).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
    expect(screen.getByText(/keeps its current details until they approve/)).toBeInTheDocument()
  })

  it('is offered on an event already Under Review, to answer a clarification', async () => {
    await openAs(organiser, submitted({ status: 'Under Review' }))

    expect(screen.getByRole('button', { name: 'Request changes' })).toBeEnabled()
  })

  it('cancelling closes the form and discards what was typed', async () => {
    const user = await openProposalForm()
    await user.clear(screen.getByLabelText('Title'))
    await user.type(screen.getByLabelText('Title'), 'Typo')
    await user.type(screen.getByLabelText('Note for the Coordinator (optional)'), 'x')

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Request changes' }))
    expect(screen.getByLabelText('Title')).toHaveValue('Faculty Welcome Night')
    expect(screen.getByLabelText('Note for the Coordinator (optional)')).toHaveValue('')
    expect(requestEventChangeMock).not.toHaveBeenCalled()
  })

  it('still lets the owner edit and submit a Draft directly', async () => {
    await openAs(organiser, submitted({ status: 'Draft', history: [] }))

    expect(screen.getByRole('button', { name: 'Save draft' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit event' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
  })

  it('a Draft still submits through the shared submission rules', async () => {
    // US4.2 and US11.1 now share one validation rule; submitting must not regress.
    const draftEvent = submitted({ status: 'Draft', history: [] })
    saveEventMock.mockResolvedValue(draftEvent)
    submitEventMock.mockResolvedValue(submitted())
    const user = userEvent.setup()
    await openAs(organiser, draftEvent)

    await user.click(screen.getByRole('button', { name: 'Submit event' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Submitted.')
    expect(saveEventMock).toHaveBeenCalledWith(
      '101',
      expect.objectContaining({ title: 'Faculty Welcome Night', expectedAttendance: 120 }),
      organiser,
    )
    expect(submitEventMock).toHaveBeenCalledWith('101', organiser)
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeInTheDocument()
  })

  it('a Draft that is incomplete is not submitted', async () => {
    const user = userEvent.setup()
    await openAs(organiser, submitted({ status: 'Draft', purpose: '', history: [] }))

    await user.click(screen.getByRole('button', { name: 'Submit event' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Give the event a purpose.')
    expect(submitEventMock).not.toHaveBeenCalled()
  })

  it.each([
    ['Rejected', 'already been decided'],
    ['Confirmed', 'already been decided'],
  ] as const)('is not offered on a %s event, and says why', async (status, why) => {
    await openAs(organiser, submitted({ status }))

    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
    expect(screen.getByText(new RegExp(why))).toBeInTheDocument()
  })

  it('is not offered to a Coordinator', async () => {
    await openAs(coordinator)

    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
  })
})

// --- AC2: editing and submitting for review ------------------------------------

describe('AC2 — submitting the proposed changes for review', () => {
  it('keeps "Submit change request" disabled until something changes', async () => {
    const user = await openProposalForm()
    const submit = screen.getByRole('button', { name: 'Submit change request' })

    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Title'), '!')
    expect(submit).toBeEnabled()
  })

  it('sends every field as typed, plus the trimmed note', async () => {
    requestEventChangeMock.mockResolvedValue(pending())
    const user = await openProposalForm()
    await user.clear(screen.getByLabelText('Title'))
    await user.type(screen.getByLabelText('Title'), 'Welcome Night')
    await user.clear(screen.getByLabelText('Expected attendance'))
    await user.type(screen.getByLabelText('Expected attendance'), '150')
    await user.type(
      screen.getByLabelText('Note for the Coordinator (optional)'),
      '  Moved to 19:00.  ',
    )

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    await waitFor(() => expect(requestEventChangeMock).toHaveBeenCalledTimes(1))
    expect(requestEventChangeMock).toHaveBeenCalledWith(
      '101',
      {
        title: 'Welcome Night',
        purpose: 'Welcome the new intake.',
        description: 'Talks.',
        startsAt: '2027-11-02T18:00',
        endsAt: '2027-11-02T21:00',
        expectedAttendance: 150,
        ...ANSWERED_NEEDS,
      },
      'Moved to 19:00.',
      organiser,
    )
  })

  it('shows the event Under Review and the request awaiting review', async () => {
    requestEventChangeMock.mockResolvedValue(pending())
    const user = await openProposalForm()
    await user.type(screen.getByLabelText('Title'), '!')

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Change request sent. The event is now Under Review and the Coordinator will review your changes.',
    )
    expect(screen.getAllByText('Under Review').length).toBeGreaterThan(0)
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Requested changes' })).toBeInTheDocument()
    expect(screen.getByText(/Awaiting the Coordinator.s review/)).toBeInTheDocument()
    expect(
      screen.getByText(/already awaiting the Coordinator's review/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument()
  })

  it('records the request, with its note, in the history', async () => {
    await openAs(organiser, pending())

    expect(screen.getByText('Change requested by Organiser')).toBeInTheDocument()
    expect(screen.getByText('Moved to 19:00.')).toBeInTheDocument()
  })

  it('does not offer the owner the Coordinator’s approve and reject controls', async () => {
    await openAs(organiser, pending())

    expect(screen.queryByRole('button', { name: 'Approve changes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject changes' })).not.toBeInTheDocument()
  })

  it('labels the button while the request is being sent', async () => {
    const reply = deferred<EventRecord>()
    requestEventChangeMock.mockReturnValue(reply.promise)
    const user = await openProposalForm()
    await user.type(screen.getByLabelText('Title'), '!')

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    reply.resolve(pending())
    await screen.findByRole('heading', { name: 'Requested changes' })
  })

  it.each([
    ['Title', '', 'Give the event a title.'],
    ['Ends', '2027-11-02T18:00', 'The end date must be after the start date.'],
    ['Expected attendance', '0', 'Expected attendance must be at least 1.'],
    ['Starts', '2020-01-01T10:00', 'The start date cannot be in the past.'],
  ])('refuses to send when %s is "%s"', async (label, value, message) => {
    const user = await openProposalForm()
    await user.clear(screen.getByLabelText(label))
    if (value) await user.type(screen.getByLabelText(label), value)

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(requestEventChangeMock).not.toHaveBeenCalled()
  })

  it('shows the server’s refusal and keeps what was typed', async () => {
    requestEventChangeMock.mockRejectedValue(
      new EventRuleError(
        "A change request for this event is already awaiting the Coordinator's review.",
      ),
    )
    const user = await openProposalForm()
    await user.type(screen.getByLabelText('Title'), '!')
    await user.type(screen.getByLabelText('Note for the Coordinator (optional)'), 'Please')

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "A change request for this event is already awaiting the Coordinator's review.",
    )
    expect(screen.getByLabelText('Title')).toHaveValue('Faculty Welcome Night!')
    expect(screen.getByLabelText('Note for the Coordinator (optional)')).toHaveValue('Please')
  })

  it('explains an unexpected failure', async () => {
    requestEventChangeMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const user = await openProposalForm()
    await user.type(screen.getByLabelText('Title'), '!')

    await user.click(screen.getByRole('button', { name: 'Submit change request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not send the change request. The API answered HTTP 500',
    )
  })
})

// --- AC3 + AC4: the Coordinator sees them, important ones flagged --------------

describe('AC3/AC4 — the Coordinator sees the proposal, important changes flagged', () => {
  it('lists each proposed change, current value beside the proposed one', async () => {
    await openAs(coordinator, pending([TITLE_CHANGE, ATTENDANCE_CHANGE]))

    const list = screen.getByRole('list', { name: 'Proposed changes' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(list).getByText('Title')).toBeInTheDocument()
    expect(within(list).getByText('Welcome Night')).toBeInTheDocument()
    expect(within(list).getByText('Faculty Welcome Night')).toBeInTheDocument()
    expect(within(list).getByText('150 people')).toBeInTheDocument()
    expect(within(list).getByText('120 people')).toBeInTheDocument()
  })

  it('tags date/time and attendance changes as important, and lists them first', async () => {
    await openAs(coordinator, pending([TITLE_CHANGE, DATE_CHANGE, ATTENDANCE_CHANGE]))

    const rows = within(screen.getByRole('list', { name: 'Proposed changes' })).getAllByRole(
      'listitem',
    )
    expect(rows.map((row) => within(row).queryByText('Important') !== null)).toEqual([
      true,
      true,
      false,
    ])
    expect(rows[0]).toHaveTextContent('Starts')
    expect(rows[0]).toHaveTextContent(formatTimestamp('2027-11-02T19:00'))
    expect(rows[2]).toHaveTextContent('Title')
  })

  it('shows a cleared value as "Not set"', async () => {
    await openAs(coordinator, pending([CLEARED_END]))

    expect(
      within(screen.getByRole('list', { name: 'Proposed changes' })).getByText('Not set'),
    ).toBeInTheDocument()
  })

  it('shows the Organiser’s note in the history', async () => {
    await openAs(coordinator, pending())

    expect(screen.getByText('Change requested by Organiser')).toBeInTheDocument()
    expect(screen.getByText('Moved to 19:00.')).toBeInTheDocument()
  })

  it('shows nothing to review when there is no request', async () => {
    await openAs(coordinator, submitted({ status: 'Under Review' }))

    expect(screen.queryByRole('heading', { name: 'Requested changes' })).not.toBeInTheDocument()
  })
})

// --- AC5: review before deciding -----------------------------------------------

describe('AC5 — the Coordinator reviews, then approves or rejects', () => {
  it('asks for the request to be answered before the event is decided', async () => {
    await openAs(coordinator, pending())

    expect(screen.getByRole('button', { name: 'Approve changes' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reject changes' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Approve event' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject event' })).not.toBeInTheDocument()
    expect(screen.getByText(/approve or reject the request before deciding/)).toBeInTheDocument()
  })

  it('approving applies the changes and makes the event decidable', async () => {
    approveEventChangeMock.mockResolvedValue(
      answered(true, ''),
    )
    const user = userEvent.setup()
    await openAs(coordinator, pending())

    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    expect(approveEventChangeMock).toHaveBeenCalledWith('101', coordinator)
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Changes approved and applied. You can now decide the event.',
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Welcome Night')
    expect(screen.queryByRole('heading', { name: 'Requested changes' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve event' })).toBeInTheDocument()
    expect(screen.getByText('Requested changes approved')).toBeInTheDocument()
  })

  it('labels the approve button while it works', async () => {
    const reply = deferred<EventRecord>()
    approveEventChangeMock.mockReturnValue(reply.promise)
    const user = userEvent.setup()
    await openAs(coordinator, pending())

    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    expect(screen.getByRole('button', { name: 'Approving…' })).toBeDisabled()
    reply.resolve(answered(true, ''))
    await screen.findByRole('status')
  })

  it.each([
    [new EventRuleError('There is no change request awaiting review on this event.'),
      'There is no change request awaiting review on this event.'],
    [new ApiError('Boom', 'unknown', 500),
      'Could not approve the requested changes. The API answered HTTP 500'],
  ])('reports a failed approval (%#)', async (error, message) => {
    approveEventChangeMock.mockRejectedValue(error)
    const user = userEvent.setup()
    await openAs(coordinator, pending())

    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('heading', { name: 'Requested changes' })).toBeInTheDocument()
  })

  it('rejecting needs a reason, sends it trimmed, and shows it to the Organiser', async () => {
    rejectEventChangeMock.mockResolvedValue(answered(false, 'Hall is booked at 19:00.'))
    const user = userEvent.setup()
    await openAs(coordinator, pending())
    const reject = screen.getByRole('button', { name: 'Reject changes' })

    await user.type(screen.getByLabelText('Reason for rejecting the changes'), '   ')
    expect(reject).toBeDisabled()
    await user.type(
      screen.getByLabelText('Reason for rejecting the changes'),
      'Hall is booked at 19:00.  ',
    )
    await user.click(reject)

    expect(rejectEventChangeMock).toHaveBeenCalledWith(
      '101',
      'Hall is booked at 19:00.',
      coordinator,
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Changes rejected. The Organiser can see your reason.',
    )
    expect(screen.getByText('Requested changes rejected')).toBeInTheDocument()
    expect(screen.getByText('Hall is booked at 19:00.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Faculty Welcome Night')
  })

  it('labels the reject button while it works', async () => {
    const reply = deferred<EventRecord>()
    rejectEventChangeMock.mockReturnValue(reply.promise)
    const user = userEvent.setup()
    await openAs(coordinator, pending())
    await user.type(screen.getByLabelText('Reason for rejecting the changes'), 'No.')

    await user.click(screen.getByRole('button', { name: 'Reject changes' }))

    expect(screen.getByRole('button', { name: 'Rejecting…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Approve changes' })).toBeDisabled()
    reply.resolve(answered(false, 'No.'))
    await screen.findByRole('status')
  })

  it.each([
    [new EventRuleError('This event changed while you were working on it.'),
      'This event changed while you were working on it.'],
    [new ApiError('Boom', 'unknown', 500),
      'Could not reject the requested changes. The API answered HTTP 500'],
  ])('reports a failed rejection and keeps the reason (%#)', async (error, message) => {
    rejectEventChangeMock.mockRejectedValue(error)
    const user = userEvent.setup()
    await openAs(coordinator, pending())
    await user.type(screen.getByLabelText('Reason for rejecting the changes'), 'Booked.')

    await user.click(screen.getByRole('button', { name: 'Reject changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByLabelText('Reason for rejecting the changes')).toHaveValue('Booked.')
  })
})

describe('AC5 — the Coordinator’s answer is shown to both sides', () => {
  it('shows the Organiser that their changes were rejected, and why', async () => {
    await openAs(organiser, answered(false, 'Hall is booked at 19:00.'))

    expect(screen.getByRole('heading', { name: 'Requested changes rejected' })).toBeInTheDocument()
    expect(screen.getByText(/kept the current details on/)).toBeInTheDocument()
    expect(screen.getByText(formatTimestamp(ANSWERED_AT))).toHaveAttribute('dateTime', ANSWERED_AT)
    expect(screen.getByText('Reason')).toBeInTheDocument()
    expect(screen.getByText('Hall is booked at 19:00.')).toBeInTheDocument()
    expect(screen.getByText('Organiser’s note')).toBeInTheDocument()
    expect(screen.getByText('Please adjust the welcome programme.')).toBeInTheDocument()
  })

  it('shows an approval without a reason block', async () => {
    await openAs(organiser, answered(true, ''))

    expect(screen.getByRole('heading', { name: 'Requested changes approved' })).toBeInTheDocument()
    expect(screen.getByText(/applied the changes on/)).toBeInTheDocument()
    expect(screen.queryByText('Reason')).not.toBeInTheDocument()
    expect(screen.getByText('Please adjust the welcome programme.')).toBeInTheDocument()
  })

  it('shows the Coordinator the same answer', async () => {
    await openAs(coordinator, answered(false, 'Hall is booked at 19:00.'))

    expect(screen.getByRole('heading', { name: 'Requested changes rejected' })).toBeInTheDocument()
  })

  it('hides the previous answer while a new request is waiting', async () => {
    await openAs(organiser, {
      ...pending(),
      changeRequestNote: 'Current request note.',
      lastChangeReview: {
        outcome: 'rejected', at: ANSWERED_AT, note: 'Earlier, no.',
        requestNote: 'Previous request note.',
      },
    })

    expect(screen.getByRole('heading', { name: 'Requested changes' })).toBeInTheDocument()
    expect(screen.queryByText('Requested changes rejected')).not.toBeInTheDocument()
    expect(screen.queryByText('Earlier, no.')).not.toBeInTheDocument()
    expect(screen.queryByText('Previous request note.')).not.toBeInTheDocument()
    expect(screen.getByText('Current request note.')).toBeInTheDocument()
  })

  it('shows nothing for an event that was never asked about', async () => {
    await openAs(organiser, submitted({ lastChangeReview: null }))

    expect(screen.queryByText(/Requested changes (approved|rejected)/)).not.toBeInTheDocument()
  })
})
