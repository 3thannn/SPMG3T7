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
  getEvent,
  rejectEventChange,
  requestEventChange,
  type EventRecord,
  type ProposedChange,
} from '../eventsStore'
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
vi.mock('../components/EventRegistration', () => ({ default: () => null }))

const getEventMock = vi.mocked(getEvent)
const requestEventChangeMock = vi.mocked(requestEventChange)

const rejectEventChangeMock = vi.mocked(rejectEventChange)

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
})

// --- AC2: editing and submitting for review ------------------------------------

describe('AC2 — submitting the proposed changes for review', () => {

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
      undefined,
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
})

// --- AC5: review before deciding -----------------------------------------------

describe('AC5 — the Coordinator reviews, then approves or rejects', () => {

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
      undefined,
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Changes rejected. The Organiser can see your reason.',
    )
    expect(screen.getByText('Requested changes rejected')).toBeInTheDocument()
    expect(screen.getByText('Hall is booked at 19:00.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Faculty Welcome Night')
  })
})

// --- US11.3: an important change to a Confirmed event --------------------------

describe('US11.3 — an important change to a Confirmed event goes back through approval', () => {
  function confirmedPending(changes: ProposedChange[]): EventRecord {
    return { ...pending(changes), status: 'Confirmed' }
  }

  it('warns the Coordinator that approving sends the event back to Planning', async () => {
    await openAs(coordinator, confirmedPending([ATTENDANCE_CHANGE]))

    expect(screen.getByText(/Approving sends the event back to Planning/)).toBeInTheDocument()
    expect(screen.queryByText(/the event keeps its current status/)).not.toBeInTheDocument()
  })
})
