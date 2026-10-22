import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SafetyCheckPanel, { SAFETY_NOTE_MAX } from './SafetyCheckPanel'
import {
  EventRuleError,
  approveSafetyCheck,
  getSafetyReadiness,
  returnSafetyCheck,
  sendForSafetyCheck,
  type EventRecord,
  type SafetyReadiness,
} from '../eventsStore'
import { ApiError, type Session } from '../api'
import type { EventStatus } from '../status'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getSafetyReadiness: vi.fn(),
  sendForSafetyCheck: vi.fn(),
  approveSafetyCheck: vi.fn(),
  returnSafetyCheck: vi.fn(),
}))

const readinessMock = vi.mocked(getSafetyReadiness)
const sendMock = vi.mocked(sendForSafetyCheck)
const approveMock = vi.mocked(approveSafetyCheck)
const returnMock = vi.mocked(returnSafetyCheck)

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

describe('the Safety Officer decides a Pending Safety Check event', () => {
  it('approves it', async () => {
    const user = userEvent.setup()
    const confirmed = eventAt('Confirmed')
    approveMock.mockResolvedValue(confirmed)
    const { onUpdated } = renderPanel(eventAt('Pending Safety Check'), officer)

    expect(screen.getByRole('heading', { name: 'Safety check decision' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))

    expect(approveMock).toHaveBeenCalledWith('101', officer)
    expect(onUpdated).toHaveBeenCalledWith(confirmed, 'Approved. The event is now Confirmed.')
    expect(readinessMock).not.toHaveBeenCalled()
  })

  it('shows progress on the button being used and locks the rest', async () => {
    const user = userEvent.setup()
    const pending = deferred<EventRecord>()
    approveMock.mockReturnValue(pending.promise)
    renderPanel(eventAt('Pending Safety Check'), officer)

    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))
    expect(screen.getByRole('button', { name: 'Approving…' })).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toBeDisabled()

    pending.resolve(eventAt('Confirmed'))
    expect(await screen.findByRole('button', { name: 'Approve safety check' })).toBeEnabled()
  })

  it('passes on a refused approval', async () => {
    const user = userEvent.setup()
    approveMock.mockRejectedValue(
      new EventRuleError('This safety check was already decided. Refresh it and try again.'),
    )
    const { onError, onUpdated } = renderPanel(eventAt('Pending Safety Check'), officer)

    await user.click(screen.getByRole('button', { name: 'Approve safety check' }))

    expect(onError).toHaveBeenCalledWith(
      'This safety check was already decided. Refresh it and try again.',
    )
    expect(onUpdated).not.toHaveBeenCalled()
  })

  it('needs a note before sending the event back', async () => {
    const user = userEvent.setup()
    renderPanel(eventAt('Pending Safety Check'), officer)

    const sendBack = screen.getByRole('button', { name: 'Send back to Planning' })
    expect(sendBack).toBeDisabled()
    await user.type(screen.getByLabelText('What needs to change'), '   ')
    expect(sendBack).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toHaveAttribute(
      'maxLength',
      String(SAFETY_NOTE_MAX),
    )
  })

  it('sends the event back with the trimmed note, then clears it', async () => {
    const user = userEvent.setup()
    const planning = eventAt('Planning')
    returnMock.mockResolvedValue(planning)
    const { onUpdated } = renderPanel(eventAt('Pending Safety Check'), officer)

    await user.type(screen.getByLabelText('What needs to change'), '  Add a fire marshal.  ')
    await user.click(screen.getByRole('button', { name: 'Send back to Planning' }))

    expect(returnMock).toHaveBeenCalledWith('101', 'Add a fire marshal.', officer)
    expect(onUpdated).toHaveBeenCalledWith(
      planning,
      'Sent back to Planning. The Coordinator can see your note.',
    )
    expect(screen.getByLabelText('What needs to change')).toHaveValue('')
  })

  it('shows "Sending back…" while that request is in flight', async () => {
    const user = userEvent.setup()
    const pending = deferred<EventRecord>()
    returnMock.mockReturnValue(pending.promise)
    renderPanel(eventAt('Pending Safety Check'), officer)

    await user.type(screen.getByLabelText('What needs to change'), 'Fix exits')
    await user.click(screen.getByRole('button', { name: 'Send back to Planning' }))
    expect(screen.getByRole('button', { name: 'Sending back…' })).toBeDisabled()

    pending.resolve(eventAt('Planning'))
    expect(await screen.findByRole('button', { name: 'Send back to Planning' })).toBeDisabled()
  })

  it('keeps the note when sending back fails', async () => {
    const user = userEvent.setup()
    returnMock.mockRejectedValue(new ApiError('Boom', 'unknown', 500))
    const { onError } = renderPanel(eventAt('Pending Safety Check'), officer)

    await user.type(screen.getByLabelText('What needs to change'), 'Fix exits')
    await user.click(screen.getByRole('button', { name: 'Send back to Planning' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/^Could not send the event back\./)
    expect(screen.getByLabelText('What needs to change')).toHaveValue('Fix exits')
  })

  it('locks every control while another write on the page is in flight', () => {
    renderPanel(eventAt('Pending Safety Check'), officer, true)
    expect(screen.getByRole('button', { name: 'Approve safety check' })).toBeDisabled()
    expect(screen.getByLabelText('What needs to change')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send back to Planning' })).toBeDisabled()
  })
})
