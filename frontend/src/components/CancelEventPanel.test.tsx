import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CancelEventPanel, { CancelledNotice } from './CancelEventPanel'
import {
  EVENT_CANCELLATION_REASON_MAX,
  EventRuleError,
  cancelEvent,
  type EventRecord,
} from '../eventsStore'
import { ApiError, type Session } from '../api'
import type { EventStatus } from '../status'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  cancelEvent: vi.fn(),
}))

const cancelMock = vi.mocked(cancelEvent)

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })
const coordinator = buildSession({ role: 'Event Coordinator', id: '2', name: 'Priya' })

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
    <CancelEventPanel
      event={event}
      session={session}
      disabled={disabled}
      onUpdated={onUpdated}
      onError={onError}
    />,
  )
  return { ...view, onUpdated, onError }
}

async function openAndType(reason: string) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Cancel this event…' }))
  if (reason) {
    await user.type(screen.getByLabelText('Why is this event being cancelled?'), reason)
  }
  return user
}

afterEach(() => {
  vi.resetAllMocks()
})

describe('who sees it', () => {
  it('offers it to the Organiser who owns the event', () => {
    renderPanel(eventAt('Planning'), organiser)
    expect(screen.getByRole('heading', { name: 'Cancel event' })).toBeInTheDocument()
  })

  it('offers it to the assigned Coordinator', () => {
    renderPanel(eventAt('Confirmed'), coordinator)
    expect(screen.getByRole('button', { name: 'Cancel this event…' })).toBeInTheDocument()
  })

  it('offers it to the Organiser on their own Draft', () => {
    renderPanel(eventAt('Draft', { coordinatorId: null }), organiser)
    expect(screen.getByRole('button', { name: 'Cancel this event…' })).toBeInTheDocument()
  })

  it('shows nothing to an Organiser who does not own the event', () => {
    const { container } = renderPanel(eventAt('Planning', { organiserId: '7' }), organiser)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows nothing to a Coordinator the event is not assigned to', () => {
    const { container } = renderPanel(eventAt('Planning', { coordinatorId: '9' }), coordinator)
    expect(container).toBeEmptyDOMElement()
  })

  it.each(['Event Coordinator Lead', 'Venue Staff', 'Safety Officer', 'Technical Support'] as const)(
    'shows nothing to %s',
    (role) => {
      const session = buildSession({ role, id: '2' })
      const { container } = renderPanel(eventAt('Pending Safety Check'), session)
      expect(container).toBeEmptyDOMElement()
    },
  )

  it.each<EventStatus>(['Completed', 'Cancelled', 'Rejected'])(
    'shows nothing once the event is %s',
    (status) => {
      const { container } = renderPanel(eventAt(status), organiser)
      expect(container).toBeEmptyDOMElement()
    },
  )
})

describe('cancelling', () => {
  it('asks first, says what will happen, and needs a reason', async () => {
    renderPanel(eventAt('Planning'), coordinator)
    expect(screen.queryByLabelText('Why is this event being cancelled?')).not.toBeInTheDocument()

    await openAndType('')

    expect(screen.getByRole('note')).toHaveTextContent(/cannot be undone/)
    expect(screen.getByRole('note')).toHaveTextContent(/every equipment request is released/)
    expect(screen.getByRole('button', { name: 'Confirm cancellation' })).toBeDisabled()
    expect(screen.getByLabelText('Why is this event being cancelled?')).toHaveAttribute(
      'maxLength',
      String(EVENT_CANCELLATION_REASON_MAX),
    )
  })

  it('a blank reason does not enable it', async () => {
    renderPanel(eventAt('Planning'), coordinator)
    await openAndType('   ')
    expect(screen.getByRole('button', { name: 'Confirm cancellation' })).toBeDisabled()
  })

  it('sends the trimmed reason and hands back the cancelled event', async () => {
    const cancelled = eventAt('Cancelled')
    cancelMock.mockResolvedValue(cancelled)
    const { onUpdated, onError } = renderPanel(eventAt('Planning'), coordinator)

    const user = await openAndType('  Funding was withdrawn.  ')
    await user.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(cancelMock).toHaveBeenCalledWith('101', 'Funding was withdrawn.', coordinator)
    expect(onUpdated).toHaveBeenCalledWith(cancelled, expect.stringMatching(/^Cancelled\. /))
    expect(onError).not.toHaveBeenCalled()
  })

  it('passes a refusal on in the server’s words and keeps what was typed', async () => {
    cancelMock.mockRejectedValue(new EventRuleError('This event has already been cancelled.'))
    const { onUpdated, onError } = renderPanel(eventAt('Planning'), organiser)

    const user = await openAndType('No longer needed.')
    await user.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(onError).toHaveBeenCalledWith('This event has already been cancelled.')
    expect(onUpdated).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Why is this event being cancelled?')).toHaveValue(
      'No longer needed.',
    )
  })

  it('explains an unexpected failure without blaming the user', async () => {
    cancelMock.mockRejectedValue(new ApiError('Server error', 'unknown', 500))
    const { onError } = renderPanel(eventAt('Planning'), organiser)

    const user = await openAndType('No longer needed.')
    await user.click(screen.getByRole('button', { name: 'Confirm cancellation' }))

    expect(onError).toHaveBeenCalledWith(expect.stringMatching(/cancel the event/))
  })

  it('"Keep event" closes the box and forgets the reason', async () => {
    renderPanel(eventAt('Planning'), organiser)
    const user = await openAndType('Maybe not.')
    await user.click(screen.getByRole('button', { name: 'Keep event' }))

    expect(screen.queryByLabelText('Why is this event being cancelled?')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    expect(screen.getByLabelText('Why is this event being cancelled?')).toHaveValue('')
    expect(cancelMock).not.toHaveBeenCalled()
  })

  it('waits while another write on the page is in flight', () => {
    renderPanel(eventAt('Planning'), organiser, true)
    expect(screen.getByRole('button', { name: 'Cancel this event…' })).toBeDisabled()
  })
})

describe('the notice on a cancelled event', () => {
  const cancelledAt = '2026-10-21T09:00:00'

  it('says who cancelled it, when and why, and that it is read-only', () => {
    render(
      <CancelledNotice
        event={eventAt('Cancelled', {
          history: [
            { from: 'Planning', to: 'Cancelled', at: cancelledAt, byId: '2', byName: 'Priya',
              notes: 'Funding was withdrawn.', kind: 'cancellation' },
          ],
        })}
      />,
    )
    const notice = screen.getByRole('note')
    expect(notice).toHaveTextContent(/^Cancelled by Priya on /)
    expect(notice).toHaveTextContent('Reason: Funding was withdrawn.')
    expect(notice).toHaveTextContent('This event is read-only.')
  })

  it('still says it is cancelled when the entry is missing', () => {
    render(<CancelledNotice event={eventAt('Cancelled')} />)
    expect(screen.getByRole('note')).toHaveTextContent(/^Cancelled/)
    expect(screen.queryByText(/^Reason:/)).not.toBeInTheDocument()
  })

  it('shows nothing on an event that is not cancelled', () => {
    const { container } = render(<CancelledNotice event={eventAt('Planning')} />)
    expect(container).toBeEmptyDOMElement()
  })
})
