import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SafetyCheckPanel, { SAFETY_NOTE_MAX } from './SafetyCheckPanel'
import {
  EventRuleError,
  approveSafetyCheck,
  confirmEvent,
  getConfirmReadiness,
  getSafetyReadiness,
  getSafetyReview,
  listSafetyDecisions,
  rejectSafetyCheck,
  requestSafetyChanges,
  resolveSafetyFlag,
  sendForSafetyCheck,
  type EventRecord,
  type SafetyDecision,
  type SafetyFlag,
  type SafetyReadiness,
  type SafetyReview,
} from '../eventsStore'
import { ApiError, type Session } from '../api'
import type { EventStatus } from '../status'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getSafetyReadiness: vi.fn(),
  sendForSafetyCheck: vi.fn(),
  approveSafetyCheck: vi.fn(),
  requestSafetyChanges: vi.fn(),
  rejectSafetyCheck: vi.fn(),
  getSafetyReview: vi.fn(),
  listSafetyDecisions: vi.fn(),
  resolveSafetyFlag: vi.fn(),
  getConfirmReadiness: vi.fn(),
  confirmEvent: vi.fn(),
}))

const readinessMock = vi.mocked(getSafetyReadiness)
const sendMock = vi.mocked(sendForSafetyCheck)
const approveMock = vi.mocked(approveSafetyCheck)
const changesMock = vi.mocked(requestSafetyChanges)
const rejectMock = vi.mocked(rejectSafetyCheck)
const reviewMock = vi.mocked(getSafetyReview)
const decisionsMock = vi.mocked(listSafetyDecisions)
const resolveMock = vi.mocked(resolveSafetyFlag)
const confirmReadinessMock = vi.mocked(getConfirmReadiness)
const confirmMock = vi.mocked(confirmEvent)

const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })
const officer = buildSession({ role: 'Safety Officer', id: '5', name: 'Alex' })
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

const READY: SafetyReadiness = { ready: true, reason: '', message: '' }
const WAITING: SafetyReadiness = {
  ready: false,
  reason: 'venue-not-confirmed',
  message: 'Every active venue booking must be Confirmed by Venue Staff before the safety check.',
}

function eventAt(status: EventStatus, overrides: Partial<EventRecord> = {}): EventRecord {
  return {
    id: '101',
    title: 'Open House',
    purpose: 'Welcome visitors',
    description: 'Tours.',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    expectedAttendance: 30,
    status,
    organiserId: '1',
    organiserName: 'Dylan',
    createdAt: '2099-01-01T09:00:00',
    updatedAt: '2099-01-01T09:00:00',
    coordinatorId: '2',
    history: [],
    ...overrides,
  }
}

function renderPanel(event: EventRecord, session: Session, disabled = false) {
  const onUpdated = vi.fn()
  const onError = vi.fn()
  const view = render(
    <SafetyCheckPanel
      event={event}
      session={session}
      disabled={disabled}
      onUpdated={onUpdated}
      onError={onError}
    />,
  )
  return { ...view, onUpdated, onError }
}

/** A promise the test settles by hand, to unmount while a request is in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** When the event entered Pending Safety Check: the review's `waitingSince`. */
const STARTED = '2099-01-02T10:00:00'

const REVIEW: SafetyReview = {
  eventId: '101',
  title: 'Open House',
  status: 'Pending Safety Check',
  startsAt: '2099-11-02T09:00',
  endsAt: '2099-11-02T17:00',
  expectedAttendance: 30,
  accessibilityNeeds: 'Wheelchair access',
  preferredLayout: 'Theatre',
  venueRequirements: 'Stage',
  waitingSince: STARTED,
  venues: [
    {
      bookingId: '11',
      venueId: '1',
      venueName: 'Great Hall',
      location: 'Building A',
      status: 'Confirmed',
      startsAt: '2099-11-02T09:00',
      endsAt: '2099-11-02T17:00',
      capacity: 500,
      headcount: 30,
      overCapacity: false,
      requiredLayout: 'Theatre',
      supportedLayouts: 'Theatre',
      facilities: 'Stage',
      accessibilityFeatures: 'Step-free access',
      accessibilityNeeds: [],
      operatingHours: '08:00-22:00',
      setupMinutes: 30,
      turnaroundMinutes: 45,
      closures: [],
    },
  ],
  equipment: [
    {
      id: '21',
      type: 'Projector',
      quantity: 2,
      technicalRequirements: '',
      supportNotes: '',
      startsAt: '2099-11-02T08:30',
      endsAt: '2099-11-02T17:30',
    },
  ],
}

function flagOf(overrides: Partial<SafetyFlag> = {}): SafetyFlag {
  return {
    id: '4',
    target: 'booking',
    targetId: '11',
    label: 'Great Hall',
    status: 'Confirmed',
    startsAt: '2099-11-02T09:00',
    endsAt: '2099-11-02T17:00',
    resolvedAt: '',
    resolvedByName: '',
    ...overrides,
  }
}

function decisionOf(overrides: Partial<SafetyDecision> = {}): SafetyDecision {
  return {
    id: '3',
    outcome: 'changes-requested',
    note: 'Add a second fire exit.',
    decidedByName: 'Alex',
    decidedAt: '2099-01-02T11:00:00',
    checkStartedAt: STARTED,
    flags: [],
    ...overrides,
  }
}

beforeEach(() => {
  // Most tests are not about earlier decisions or the review loading.
  decisionsMock.mockResolvedValue([])
  reviewMock.mockResolvedValue(REVIEW)
})

afterEach(() => {
  vi.resetAllMocks()
})

describe('who sees what', () => {
  it('shows nothing to an Organiser, whatever the status', () => {
    const { container } = renderPanel(eventAt('Planning'), organiser)
    expect(container).toBeEmptyDOMElement()
    expect(readinessMock).not.toHaveBeenCalled()
  })

  it('shows nothing to a Coordinator the event is not assigned to', () => {
    const { container } = renderPanel(eventAt('Planning', { coordinatorId: '9' }), coordinator)
    expect(container).toBeEmptyDOMElement()
  })

  it.each<EventStatus>(['Approved', 'Confirmed', 'Completed'])(
    'shows the assigned Coordinator nothing while the event is %s',
    (status) => {
      const { container } = renderPanel(eventAt(status), coordinator)
      expect(container).toBeEmptyDOMElement()
    },
  )

  it.each<EventStatus>(['Planning', 'Confirmed'])(
    'shows the Safety Officer nothing while the event is %s',
    (status) => {
      const { container } = renderPanel(eventAt(status), officer)
      expect(container).toBeEmptyDOMElement()
    },
  )

  it('tells the assigned Coordinator the event is waiting for the Safety Officer', () => {
    renderPanel(eventAt('Pending Safety Check'), coordinator)
    expect(screen.getByRole('heading', { name: 'Safety check' })).toBeInTheDocument()
    expect(screen.getByText(/Waiting for the Safety Officer/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('the assigned Coordinator sends a Planning event', () => {
  it('says it is checking, then offers the send once the server says ready', async () => {
    readinessMock.mockResolvedValue(READY)
    renderPanel(eventAt('Planning'), coordinator)

    expect(screen.getByRole('status')).toHaveTextContent('Checking whether this event is ready…')
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeDisabled()
    expect(await screen.findByText(/Every venue booking is Confirmed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Check again' })).not.toBeInTheDocument()
    expect(readinessMock).toHaveBeenCalledWith('101', coordinator)
  })

  it('explains what is outstanding and keeps the send disabled', async () => {
    readinessMock.mockResolvedValue(WAITING)
    renderPanel(eventAt('Planning'), coordinator)

    expect(await screen.findByText(WAITING.message)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeDisabled()
  })

  it('checks again on request', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValueOnce(WAITING).mockResolvedValueOnce(READY)
    renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Check again' }))

    expect(await screen.findByRole('button', { name: 'Send for safety check' })).toBeEnabled()
    expect(readinessMock).toHaveBeenCalledTimes(2)
  })

  it('says so when readiness cannot be read, and lets them retry', async () => {
    readinessMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    renderPanel(eventAt('Planning'), coordinator)

    expect(await screen.findByText('Could not check whether this event is ready.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
  })

  it('re-checks when the page reloads the event', async () => {
    readinessMock.mockResolvedValue(WAITING)
    const { rerender, onUpdated, onError } = renderPanel(eventAt('Planning'), coordinator)
    await screen.findByText(WAITING.message)

    readinessMock.mockResolvedValue(READY)
    rerender(
      <SafetyCheckPanel
        event={eventAt('Planning', { updatedAt: '2099-01-02T09:00:00' })}
        session={coordinator}
        disabled={false}
        onUpdated={onUpdated}
        onError={onError}
      />,
    )

    expect(await screen.findByRole('button', { name: 'Send for safety check' })).toBeEnabled()
    expect(readinessMock).toHaveBeenCalledTimes(2)
  })

  it('sends the event and hands the page the result', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(READY)
    const sent = eventAt('Pending Safety Check')
    sendMock.mockResolvedValue(sent)
    const { onUpdated, onError } = renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Send for safety check' }))

    expect(sendMock).toHaveBeenCalledWith('101', coordinator)
    expect(onUpdated).toHaveBeenCalledWith(
      sent,
      'Sent for the safety check. The event is now Pending Safety Check.',
    )
    expect(onError).not.toHaveBeenCalled()
  })

  it('shows "Sending…" while the request is in flight', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(READY)
    const pending = deferred<EventRecord>()
    sendMock.mockReturnValue(pending.promise)
    renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Send for safety check' }))
    expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled()

    pending.resolve(eventAt('Pending Safety Check'))
    expect(await screen.findByRole('button', { name: 'Send for safety check' })).toBeEnabled()
  })

  it('passes on a refusal and re-checks what made the event unready', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValueOnce(READY).mockResolvedValueOnce(WAITING)
    sendMock.mockRejectedValue(new EventRuleError(WAITING.message))
    const { onError, onUpdated } = renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Send for safety check' }))

    expect(onError).toHaveBeenCalledWith(WAITING.message)
    expect(onUpdated).not.toHaveBeenCalled()
    expect(await screen.findByText(WAITING.message)).toBeInTheDocument()
    expect(readinessMock).toHaveBeenCalledTimes(2)
  })

  it('describes an unexpected failure without blaming a rule', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(READY)
    sendMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const { onError } = renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Send for safety check' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/^Could not send the event for its safety check\./)
  })

  it('stays disabled while another write on the page is in flight', async () => {
    readinessMock.mockResolvedValue(READY)
    renderPanel(eventAt('Planning'), coordinator, true)

    await screen.findByText(/Every venue booking is Confirmed/)
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeDisabled()
  })

  it('ignores an answer that arrives after it has gone', async () => {
    const answer = deferred<SafetyReadiness>()
    readinessMock.mockReturnValue(answer.promise)
    const { unmount } = renderPanel(eventAt('Planning'), coordinator)
    unmount()
    answer.resolve(READY)
    await answer.promise

    const failure = deferred<SafetyReadiness>()
    readinessMock.mockReturnValue(failure.promise)
    const second = renderPanel(eventAt('Planning'), coordinator)
    second.unmount()
    failure.reject(new Error('gone'))
    await expect(failure.promise).rejects.toThrow('gone')
  })
})

/* ---------- US17.2: the Coordinator meets the Safety Officer's decision ---------- */

const FLAGS_OPEN: SafetyReadiness = {
  ready: false,
  reason: 'safety-flags-open',
  message: 'The Safety Officer flagged arrangements for re-review.',
}

describe('US17.2: the assigned Coordinator sees what was sent back', () => {
  it('shows the request for changes, its note, and the flags to re-review', async () => {
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([
      decisionOf({
        flags: [
          flagOf(),
          flagOf({
            id: '5',
            target: 'equipment',
            targetId: '21',
            label: 'Projector × 2',
            status: 'Reserved',
            resolvedAt: '2099-01-03T09:00:00',
            resolvedByName: '',
          }),
        ],
      }),
    ])
    renderPanel(eventAt('Planning'), coordinator)

    expect(await screen.findByText('Changes requested')).toBeInTheDocument()
    expect(screen.getByText(/by Alex/)).toBeInTheDocument()
    expect(screen.getByText('Add a second fire exit.')).toBeInTheDocument()
    const flags = screen.getByRole('list', { name: 'Flagged for re-review' })
    expect(within(flags).getByText(/Great Hall/)).toBeInTheDocument()
    expect(within(flags).getByText('(Confirmed)')).toBeInTheDocument()
    expect(within(flags).getByText(/Re-reviewed by the Coordinator/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark Great Hall re-reviewed' })).toBeEnabled()
    expect(
      screen.queryByRole('button', { name: 'Mark Projector × 2 re-reviewed' }),
    ).not.toBeInTheDocument()
    expect(await screen.findByText(FLAGS_OPEN.message)).toBeInTheDocument()
    expect(decisionsMock).toHaveBeenCalledWith('101', coordinator)
  })

  it('shows a rejection and its reason, with nothing to re-review', async () => {
    readinessMock.mockResolvedValue(READY)
    decisionsMock.mockResolvedValue([
      decisionOf({ outcome: 'rejected', note: 'Venue unsafe.', decidedByName: '' }),
    ])
    renderPanel(eventAt('Planning'), coordinator)

    expect(await screen.findByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText(/by the Safety Officer/)).toBeInTheDocument()
    expect(screen.getByText('Venue unsafe.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Flagged for re-review' })).not.toBeInTheDocument()
  })

  it('describes a flagged arrangement that has gone without its times', async () => {
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([
      decisionOf({
        flags: [
          flagOf({
            label: 'A venue booking that no longer exists',
            status: '',
            startsAt: '',
            endsAt: '',
          }),
        ],
      }),
    ])
    renderPanel(eventAt('Planning'), coordinator)

    const flags = await screen.findByRole('list', { name: 'Flagged for re-review' })
    expect(within(flags).getByText('A venue booking that no longer exists')).toBeInTheDocument()
  })

  it('shows nothing about a decision when none was made', async () => {
    readinessMock.mockResolvedValue(READY)
    renderPanel(eventAt('Planning'), coordinator)

    await screen.findByText(/Every venue booking is Confirmed/)
    await waitFor(() => expect(decisionsMock).toHaveBeenCalled())
    expect(screen.queryByText('Changes requested')).not.toBeInTheDocument()
  })

  it('does not present an approval as something sent back', async () => {
    readinessMock.mockResolvedValue(READY)
    decisionsMock.mockResolvedValue([decisionOf({ outcome: 'approved', note: '' })])
    renderPanel(eventAt('Planning'), coordinator)

    await screen.findByText(/Every venue booking is Confirmed/)
    await waitFor(() => expect(decisionsMock).toHaveBeenCalled())
    expect(screen.queryByText('Approved')).not.toBeInTheDocument()
  })

  it('says so when the last decision cannot be loaded', async () => {
    readinessMock.mockResolvedValue(READY)
    decisionsMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    renderPanel(eventAt('Planning'), coordinator)

    expect(
      await screen.findByText("Could not load the Safety Officer's last decision."),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send for safety check' })).toBeEnabled()
  })

  it('marks a flag re-reviewed, then re-checks whether the event is ready', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValueOnce(FLAGS_OPEN).mockResolvedValueOnce(READY)
    decisionsMock.mockResolvedValue([decisionOf({ flags: [flagOf(), flagOf({ id: '5' })] })])
    resolveMock.mockResolvedValue(
      flagOf({ resolvedAt: '2099-01-03T09:00:00', resolvedByName: 'Priya' }),
    )
    renderPanel(eventAt('Planning'), coordinator)

    const [first] = await screen.findAllByRole('button', { name: 'Mark Great Hall re-reviewed' })
    await user.click(first)

    expect(resolveMock).toHaveBeenCalledWith('101', '4', coordinator)
    expect(await screen.findByText(/Re-reviewed by Priya/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Mark Great Hall re-reviewed' })).toHaveLength(1)
    expect(await screen.findByRole('button', { name: 'Send for safety check' })).toBeEnabled()
    expect(readinessMock).toHaveBeenCalledTimes(2)
  })

  it('shows "Saving…" and locks the other flags while one is saved', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([decisionOf({ flags: [flagOf(), flagOf({ id: '5' })] })])
    const pending = deferred<SafetyFlag>()
    resolveMock.mockReturnValue(pending.promise)
    renderPanel(eventAt('Planning'), coordinator)

    const [first] = await screen.findAllByRole('button', { name: 'Mark Great Hall re-reviewed' })
    await user.click(first)
    const buttons = screen.getAllByRole('button', { name: 'Mark Great Hall re-reviewed' })
    expect(buttons[0]).toHaveTextContent('Saving…')
    expect(buttons[0]).toBeDisabled()
    expect(buttons[1]).toHaveTextContent('Mark re-reviewed')
    expect(buttons[1]).toBeDisabled()

    pending.resolve(flagOf({ resolvedAt: '2099-01-03T09:00:00', resolvedByName: 'Priya' }))
    expect(
      await screen.findByRole('button', { name: 'Mark Great Hall re-reviewed' }),
    ).toBeEnabled()
  })

  it('passes on a refused re-review and keeps the flag open', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([decisionOf({ flags: [flagOf()] })])
    resolveMock.mockRejectedValue(
      new EventRuleError('This arrangement was already marked re-reviewed.'),
    )
    const { onError } = renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Mark Great Hall re-reviewed' }))

    expect(onError).toHaveBeenCalledWith('This arrangement was already marked re-reviewed.')
    expect(screen.getByRole('button', { name: 'Mark Great Hall re-reviewed' })).toBeEnabled()
  })

  it('describes an unexpected re-review failure without blaming a rule', async () => {
    const user = userEvent.setup()
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([decisionOf({ flags: [flagOf()] })])
    resolveMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const { onError } = renderPanel(eventAt('Planning'), coordinator)

    await user.click(await screen.findByRole('button', { name: 'Mark Great Hall re-reviewed' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/^Could not mark the arrangement re-reviewed\./)
  })

  it('locks the flags while another write on the page is in flight', async () => {
    readinessMock.mockResolvedValue(FLAGS_OPEN)
    decisionsMock.mockResolvedValue([decisionOf({ flags: [flagOf()] })])
    renderPanel(eventAt('Planning'), coordinator, true)

    expect(
      await screen.findByRole('button', { name: 'Mark Great Hall re-reviewed' }),
    ).toBeDisabled()
  })

  it('ignores decisions that arrive after it has gone', async () => {
    readinessMock.mockResolvedValue(READY)
    const answer = deferred<SafetyDecision[]>()
    decisionsMock.mockReturnValue(answer.promise)
    const { unmount } = renderPanel(eventAt('Planning'), coordinator)
    unmount()
    answer.resolve([decisionOf()])
    await answer.promise

    const failure = deferred<SafetyDecision[]>()
    decisionsMock.mockReturnValue(failure.promise)
    const second = renderPanel(eventAt('Planning'), coordinator)
    second.unmount()
    failure.reject(new Error('gone'))
    await expect(failure.promise).rejects.toThrow('gone')
  })
})

/* ---------- US17.2: the Safety Officer records a decision ---------- */

/** Render for the Safety Officer and wait until the review has loaded. */
async function renderForOfficer(disabled = false) {
  const view = renderPanel(eventAt('Pending Safety Check'), officer, disabled)
  await waitFor(() => expect(reviewMock).toHaveBeenCalled())
  if (!disabled) {
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeEnabled(),
    )
  }
  return view
}

describe('US17.2: the Safety Officer decides a Pending Safety Check event', () => {
  it('locks the decision until the review it is made on has loaded', async () => {
    const review = deferred<SafetyReview>()
    reviewMock.mockReturnValue(review.promise)
    renderPanel(eventAt('Pending Safety Check'), officer)

    expect(screen.getByRole('heading', { name: 'Safety check decision' })).toBeInTheDocument()
    expect(screen.getByText('Loading what you are deciding on…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeDisabled()

    review.resolve(REVIEW)
    expect(await screen.findByRole('button', { name: 'Approve safety check' })).toBeEnabled()
    expect(reviewMock).toHaveBeenCalledWith('101', officer)
    expect(readinessMock).not.toHaveBeenCalled()
  })

  it('approves the submission it was shown', async () => {
    const user = userEvent.setup()
    // US4.7: still Pending Safety Check, now approved, for the Coordinator to confirm.
    const approved = { ...eventAt('Pending Safety Check'), safetyApproved: true }
    approveMock.mockResolvedValue(approved)
    const { onUpdated } = await renderForOfficer()

    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))

    expect(approveMock).toHaveBeenCalledWith('101', STARTED, officer)
    expect(onUpdated).toHaveBeenCalledWith(
      approved,
      'Approved. The Coordinator confirms the event once everything else is in place.',
    )
  })

  it('shows progress on the button being used and locks the rest', async () => {
    const user = userEvent.setup()
    const pending = deferred<EventRecord>()
    approveMock.mockReturnValue(pending.promise)
    await renderForOfficer()

    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))
    expect(screen.getByRole('button', { name: 'Approving…' })).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toBeDisabled()
    expect(screen.getByLabelText('Reject')).toBeDisabled()

    pending.resolve(eventAt('Confirmed'))
    expect(await screen.findByRole('button', { name: 'Approve safety check' })).toBeEnabled()
  })

  it('passes on a refused approval', async () => {
    const user = userEvent.setup()
    approveMock.mockRejectedValue(
      new EventRuleError('This event was sent back and submitted again since you opened it.'),
    )
    const { onError, onUpdated } = await renderForOfficer()

    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))

    expect(onError).toHaveBeenCalledWith(
      'This event was sent back and submitted again since you opened it.',
    )
    expect(onUpdated).not.toHaveBeenCalled()
  })

  it('defaults the send-back to a request for changes, which needs a note', async () => {
    const user = userEvent.setup()
    await renderForOfficer()

    expect(screen.getByLabelText('Request changes')).toBeChecked()
    const send = screen.getByRole('button', { name: 'Request changes' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('What needs to change'), '   ')
    expect(send).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toHaveAttribute(
      'maxLength',
      String(SAFETY_NOTE_MAX),
    )
  })

  it('offers each booked venue and reserved line to flag for re-review', async () => {
    await renderForOfficer()

    const picker = screen.getByRole('group', { name: 'Flag for re-review (optional)' })
    expect(within(picker).getByLabelText(/^Great Hall · /)).not.toBeChecked()
    expect(within(picker).getByLabelText('Projector × 2')).not.toBeChecked()
  })

  it('requests changes with the trimmed note and the arrangements flagged', async () => {
    const user = userEvent.setup()
    const planning = eventAt('Planning')
    changesMock.mockResolvedValue(planning)
    const { onUpdated } = await renderForOfficer()

    await user.type(screen.getByLabelText('What needs to change'), '  Add a fire marshal.  ')
    await user.click(screen.getByLabelText(/^Great Hall · /))
    await user.click(screen.getByLabelText('Projector × 2'))
    // Changing their mind: unflag the venue again.
    await user.click(screen.getByLabelText(/^Great Hall · /))
    await user.click(screen.getByRole('button', { name: 'Request changes' }))

    expect(changesMock).toHaveBeenCalledWith(
      '101',
      {
        checkStartedAt: STARTED,
        note: 'Add a fire marshal.',
        flaggedBookingIds: [],
        flaggedEquipmentIds: ['21'],
      },
      officer,
    )
    expect(onUpdated).toHaveBeenCalledWith(
      planning,
      'Changes requested. The event is back in Planning and the Coordinator has been told.',
    )
  })

  it('shows "Sending back…" while a request for changes is in flight', async () => {
    const user = userEvent.setup()
    const pending = deferred<EventRecord>()
    changesMock.mockReturnValue(pending.promise)
    await renderForOfficer()

    await user.type(screen.getByLabelText('What needs to change'), 'Fix exits')
    await user.click(screen.getByLabelText(/^Great Hall · /))
    await user.click(screen.getByRole('button', { name: 'Request changes' }))
    expect(screen.getByRole('button', { name: 'Sending back…' })).toBeDisabled()
    expect(screen.getByLabelText(/^Great Hall · /)).toBeDisabled()

    pending.resolve(eventAt('Planning'))
    expect(await screen.findByRole('button', { name: 'Request changes' })).toBeEnabled()
  })

  it('keeps the note when a request for changes fails', async () => {
    const user = userEvent.setup()
    changesMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const { onError } = await renderForOfficer()

    await user.type(screen.getByLabelText('What needs to change'), 'Fix exits')
    await user.click(screen.getByRole('button', { name: 'Request changes' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/^Could not request changes\./)
    expect(screen.getByLabelText('What needs to change')).toHaveValue('Fix exits')
  })

  it('rejects with a reason, and flags nothing', async () => {
    const user = userEvent.setup()
    const planning = eventAt('Planning')
    rejectMock.mockResolvedValue(planning)
    const { onUpdated } = await renderForOfficer()

    await user.click(screen.getByLabelText('Reject'))
    expect(screen.queryByRole('group', { name: /Flag for re-review/ })).not.toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Reject safety check' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('Reason for rejecting'), ' Venue unsafe. ')
    await user.click(send)

    expect(rejectMock).toHaveBeenCalledWith('101', 'Venue unsafe.', STARTED, officer)
    expect(changesMock).not.toHaveBeenCalled()
    expect(onUpdated).toHaveBeenCalledWith(
      planning,
      'Rejected. The event is back in Planning with your reason, and the Coordinator has been told.',
    )
  })

  it('shows "Rejecting…" while a rejection is in flight', async () => {
    const user = userEvent.setup()
    const pending = deferred<EventRecord>()
    rejectMock.mockReturnValue(pending.promise)
    await renderForOfficer()

    await user.click(screen.getByLabelText('Reject'))
    await user.type(screen.getByLabelText('Reason for rejecting'), 'Unsafe')
    await user.click(screen.getByRole('button', { name: 'Reject safety check' }))
    expect(screen.getByRole('button', { name: 'Rejecting…' })).toBeDisabled()

    pending.resolve(eventAt('Planning'))
    expect(await screen.findByRole('button', { name: 'Reject safety check' })).toBeEnabled()
  })

  it('describes an unexpected rejection failure without blaming a rule', async () => {
    const user = userEvent.setup()
    rejectMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const { onError } = await renderForOfficer()

    await user.click(screen.getByLabelText('Reject'))
    await user.type(screen.getByLabelText('Reason for rejecting'), 'Unsafe')
    await user.click(screen.getByRole('button', { name: 'Reject safety check' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/^Could not reject the safety check\./)
  })

  it('can switch back from rejecting to requesting changes', async () => {
    const user = userEvent.setup()
    await renderForOfficer()

    await user.click(screen.getByLabelText('Reject'))
    await user.click(screen.getByLabelText('Request changes'))

    expect(screen.getByLabelText('What needs to change')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: /Flag for re-review/ })).toBeInTheDocument()
  })

  it('says when there is nothing booked or reserved to flag', async () => {
    reviewMock.mockResolvedValue({ ...REVIEW, venues: [], equipment: [] })
    await renderForOfficer()

    expect(screen.getByText('Nothing is booked or reserved to flag.')).toBeInTheDocument()
  })

  it('says when the review cannot be loaded, and tries again on request', async () => {
    const user = userEvent.setup()
    reviewMock.mockRejectedValueOnce(new ApiError('Boom', 'unknown', 500))
    renderPanel(eventAt('Pending Safety Check'), officer)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the safety review, so no decision can be recorded yet.',
    )
    expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('button', { name: 'Approve safety check' })).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(reviewMock).toHaveBeenCalledTimes(2)
  })

  it('shows earlier decisions on the event, and what became of their flags', async () => {
    decisionsMock.mockResolvedValue([
      decisionOf({
        flags: [
          flagOf({ resolvedAt: '2099-01-03T09:00:00', resolvedByName: 'Priya' }),
          flagOf({ id: '5', target: 'equipment', label: 'Projector × 2', status: 'Reserved' }),
        ],
      }),
      decisionOf({ id: '2', outcome: 'rejected', note: 'Too crowded.' }),
    ])
    await renderForOfficer()

    const earlier = await screen.findByRole('region', { name: 'Earlier safety decisions' })
    expect(within(earlier).getByText('Changes requested')).toBeInTheDocument()
    expect(within(earlier).getByText('Rejected')).toBeInTheDocument()
    expect(within(earlier).getByText('Too crowded.')).toBeInTheDocument()
    expect(within(earlier).getByText(/Re-reviewed by Priya/)).toBeInTheDocument()
    expect(within(earlier).getByText('Not re-reviewed yet')).toBeInTheDocument()
    // The Safety Officer reads flags; only the Coordinator resolves them.
    expect(within(earlier).queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows recorded safety decisions and flag resolutions in SGT across midnight', async () => {
    decisionsMock.mockResolvedValue([decisionOf({
      decidedAt: '2026-12-31T16:30:00',
      flags: [flagOf({ resolvedAt: '2026-12-31T16:45:00', resolvedByName: 'Priya' })],
    })])
    await renderForOfficer()
    const earlier = await screen.findByRole('region', { name: 'Earlier safety decisions' })
    expect(earlier).toHaveTextContent('01 Jan 2027, 00:30')
    expect(earlier).toHaveTextContent('01 Jan 2027, 00:45')
  })

  it('still decides when earlier decisions cannot be loaded', async () => {
    decisionsMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    await renderForOfficer()

    expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeEnabled()
    expect(
      screen.queryByRole('region', { name: 'Earlier safety decisions' }),
    ).not.toBeInTheDocument()
  })

  it('locks every control while another write on the page is in flight', async () => {
    await renderForOfficer(true)

    await screen.findByLabelText(/^Great Hall · /)
    expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toBeDisabled()
    expect(screen.getByLabelText('Request changes')).toBeDisabled()
    expect(screen.getByLabelText(/^Great Hall · /)).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeDisabled()
  })

  it('ignores answers that arrive after it has gone', async () => {
    const review = deferred<SafetyReview>()
    const decisions = deferred<SafetyDecision[]>()
    reviewMock.mockReturnValue(review.promise)
    decisionsMock.mockReturnValue(decisions.promise)
    const { unmount } = renderPanel(eventAt('Pending Safety Check'), officer)
    unmount()
    review.resolve(REVIEW)
    decisions.resolve([decisionOf()])
    await Promise.all([review.promise, decisions.promise])

    const failure = deferred<SafetyReview>()
    reviewMock.mockReturnValue(failure.promise)
    const second = renderPanel(eventAt('Pending Safety Check'), officer)
    second.unmount()
    failure.reject(new Error('gone'))
    await expect(failure.promise).rejects.toThrow('gone')
  })
})

// --- US4.7: the Coordinator confirms the event ----------------------------------

describe('US4.7: the Coordinator confirms the event once every approval is in', () => {
  const approved = () => eventAt('Pending Safety Check', { safetyApproved: true })
  const MISSING: SafetyReadiness = {
    ready: false,
    reason: 'venue-not-confirmed',
    message: 'Breakout Room B is still awaiting Venue Staff approval.',
  }

  it('waits for the Safety Officer before there is anything to confirm', () => {
    renderPanel(eventAt('Pending Safety Check'), coordinator)

    expect(screen.getByText(/Once they approve it, you confirm the event here/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm event' })).not.toBeInTheDocument()
  })

  it('offers Confirm event once approved and ready, and confirms it', async () => {
    const user = userEvent.setup()
    const confirmed = eventAt('Confirmed')
    confirmReadinessMock.mockResolvedValue(READY)
    confirmMock.mockResolvedValue(confirmed)
    const { onUpdated } = renderPanel(approved(), coordinator)

    const button = await screen.findByRole('button', { name: 'Confirm event' })
    await waitFor(() => expect(button).toBeEnabled())
    expect(screen.getByRole('status')).toHaveTextContent(/Confirm it to tell the Organiser/)
    await user.click(button)

    expect(confirmMock).toHaveBeenCalledWith('101', coordinator)
    expect(onUpdated).toHaveBeenCalledWith(
      confirmed,
      'Confirmed. The Organiser has been told the event is going ahead.',
    )
  })

  it('names what is missing and keeps the button off', async () => {
    const user = userEvent.setup()
    confirmReadinessMock.mockResolvedValue(MISSING)
    renderPanel(approved(), coordinator)

    expect(await screen.findByText(MISSING.message)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm event' })).toBeDisabled()

    confirmReadinessMock.mockResolvedValue(READY)
    await user.click(screen.getByRole('button', { name: 'Check again' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm event' })).toBeEnabled())
  })

  it('says when it could not check', async () => {
    confirmReadinessMock.mockRejectedValue(new Error('offline'))
    renderPanel(approved(), coordinator)

    expect(
      await screen.findByText('Could not check whether this event can be confirmed.'),
    ).toBeInTheDocument()
  })

  it('shows a refusal and checks again', async () => {
    const user = userEvent.setup()
    confirmReadinessMock.mockResolvedValue(READY)
    confirmMock.mockRejectedValue(new EventRuleError(MISSING.message))
    const { onError } = renderPanel(approved(), coordinator)

    const button = await screen.findByRole('button', { name: 'Confirm event' })
    await waitFor(() => expect(button).toBeEnabled())
    confirmReadinessMock.mockResolvedValue(MISSING)
    await user.click(button)

    expect(onError).toHaveBeenCalledWith(MISSING.message)
    expect(await screen.findByText(MISSING.message)).toBeInTheDocument()
  })

  it('labels the button while it confirms', async () => {
    const user = userEvent.setup()
    const reply = deferred<EventRecord>()
    confirmReadinessMock.mockResolvedValue(READY)
    confirmMock.mockReturnValue(reply.promise)
    renderPanel(approved(), coordinator)

    const button = await screen.findByRole('button', { name: 'Confirm event' })
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)

    expect(screen.getByRole('button', { name: 'Confirming…' })).toBeDisabled()
    reply.resolve(eventAt('Confirmed'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm event' })).toBeInTheDocument())
  })

  it('a Coordinator without the permission only sees the wait', () => {
    const limited = {
      ...coordinator,
      permissions: coordinator.permissions.filter((each) => each !== 'events:confirm'),
    }
    renderPanel(approved(), limited)

    expect(screen.getByText(/Waiting for the Safety Officer/)).toBeInTheDocument()
  })

  it('tells the Safety Officer the approval is in and the Coordinator confirms', () => {
    renderPanel(approved(), officer)

    expect(screen.getByText(/You approved this safety check/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve safety check' })).not.toBeInTheDocument()
  })

  it('stops loading readiness once the panel has gone', async () => {
    const reply = deferred<SafetyReadiness>()
    confirmReadinessMock.mockReturnValue(reply.promise)
    const { unmount } = renderPanel(approved(), coordinator)
    unmount()
    reply.resolve(READY)

    const failure = deferred<SafetyReadiness>()
    confirmReadinessMock.mockReturnValue(failure.promise)
    const second = renderPanel(approved(), coordinator)
    second.unmount()
    failure.reject(new Error('gone'))
    await expect(failure.promise).rejects.toThrow('gone')
  })
})
