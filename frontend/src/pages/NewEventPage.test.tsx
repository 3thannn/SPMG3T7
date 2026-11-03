/**
 * What the creation form sends, given what was typed.
 *
 * The fields are the writable columns of the `events` table, so these tests are
 * mostly about the two nullable ones: a blank purpose and a blank attendance
 * have to reach the API as "unset" rather than as an invented value, and an
 * attendance of zero has to survive as zero. The rules the server owns are
 * tested in backend/tests/test_events.py; what is this page's job is asking for
 * the right things and refusing what the columns cannot hold.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NewEventPage, { SUBMIT_BLOCKED } from './NewEventPage'
import { createEvent, submitEvent, type EventRecord } from '../eventsStore'
import { MISSING_MESSAGES, NO_NEEDS, NOT_REQUIRED } from '../eventNeeds'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  createEvent: vi.fn(),
  submitEvent: vi.fn(),
}))

const createEventMock = vi.mocked(createEvent)
const submitEventMock = vi.mocked(submitEvent)

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

const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

const created: EventRecord = {
  id: '101',
  title: 'Faculty Welcome Night',
  purpose: '',
  description: '',
  startsAt: '2026-11-02T18:00',
  expectedAttendance: null,
  status: 'Draft',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:00:00',
  history: [],
}

/** Fill in the fields required when submitting, leaving optional details alone. */
async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Title'), 'Faculty Welcome Night')
  await user.type(screen.getByLabelText('Starts'), '2026-11-02T18:00')
}

// Typing every field is slow under coverage instrumentation, so allow longer.
describe('US2.1 (Sprint 3) — mandatory fields on Submit', { timeout: 15_000 }, () => {

  it('blocks Submit on an empty form and names every missing field', async () => {
    const user = userEvent.setup()

    render(<NewEventPage session={organiser} />)
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(SUBMIT_BLOCKED)
    for (const message of [
      'Give the event a title.',
      'Give the event a date.',
      'Give the event an end date.',
      'Give the event a purpose.',
      'Give the expected attendance.',
      'Give the event a description.',
      ...Object.values(MISSING_MESSAGES),
    ]) {
      expect(screen.getByText(message)).toHaveClass('field-error')
    }
    expect(screen.getByLabelText('Description')).toHaveAccessibleDescription(
      'Give the event a description.',
    )
    expect(createEventMock).not.toHaveBeenCalled()
    expect(submitEventMock).not.toHaveBeenCalled()
  })

  it('accepts None / Not required for every need', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)
    submitEventMock.mockResolvedValue({ ...created, status: 'Submitted' })

    render(<NewEventPage session={organiser} />)
    await fillRequired(user)
    await user.type(screen.getByLabelText('Ends'), '2026-11-02T21:00')
    await user.type(screen.getByLabelText('Purpose'), 'Welcome the new intake.')
    await user.type(screen.getByLabelText('Expected attendance'), '120')
    await user.type(screen.getByLabelText('Description'), 'Talks.')
    for (const name of [
      'Venue requirements',
      'Accessibility needs',
      'Equipment needs',
      'Registration needs',
    ]) {
      await user.click(within(screen.getByRole('group', { name })).getByLabelText(NOT_REQUIRED))
    }
    await user.selectOptions(screen.getByLabelText('Preferred layout'), NOT_REQUIRED)
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => expect(submitEventMock).toHaveBeenCalled())
    expect(createEventMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        venueRequirements: NOT_REQUIRED,
        preferredLayout: NOT_REQUIRED,
        accessibilityNeeds: NOT_REQUIRED,
        equipmentNeeds: NOT_REQUIRED,
        registrationNeeds: NOT_REQUIRED,
      }),
    )
  })
})

describe('US2.1 (Sprint 3) — drafts still save without these checks (US2.2)', () => {
  it('saves a draft with every need unanswered and shows no errors', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)

    render(<NewEventPage session={organiser} />)
    await user.type(screen.getByLabelText('Title'), 'Faculty Welcome Night')
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(createEventMock).toHaveBeenCalled())
    expect(createEventMock.mock.calls[0][0]).toEqual(expect.objectContaining(NO_NEEDS))
    expect(submitEventMock).not.toHaveBeenCalled()
    expect(screen.queryByText(MISSING_MESSAGES.venueRequirements)).not.toBeInTheDocument()
  })
})
