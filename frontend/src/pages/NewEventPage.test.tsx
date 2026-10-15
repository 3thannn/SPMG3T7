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
import { afterEach, describe, expect, it, vi } from 'vitest'
import NewEventPage, { SUBMIT_BLOCKED } from './NewEventPage'
import { createEvent, EventRuleError, submitEvent, type EventRecord } from '../eventsStore'
import { MISSING_MESSAGES, NO_NEEDS, NOT_REQUIRED } from '../eventNeeds'
import { ANSWERED_NEEDS } from '../test/eventNeeds'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  createEvent: vi.fn(),
  submitEvent: vi.fn(),
}))

const createEventMock = vi.mocked(createEvent)
const submitEventMock = vi.mocked(submitEvent)

afterEach(() => {
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

/** US2.1 (Sprint 3): answer all five needs, the way an Organiser would. */
async function answerNeeds(user: ReturnType<typeof userEvent.setup>) {
  const venue = screen.getByRole('group', { name: 'Venue requirements' })
  await user.click(within(venue).getByLabelText('Projector'))
  await user.click(within(venue).getByLabelText('Stage'))
  await user.selectOptions(screen.getByLabelText('Preferred layout'), 'Theatre')
  const access = screen.getByRole('group', { name: 'Accessibility needs' })
  await user.click(within(access).getByLabelText('Wheelchair access'))
  await user.type(screen.getByLabelText('Equipment needs'), 'Two wireless microphones')
  const registration = screen.getByRole('group', { name: 'Registration needs' })
  await user.click(within(registration).getByLabelText('None / Not required'))
}

it('offers a field for every writable column of the events table', () => {
  render(<NewEventPage session={organiser} />)

  expect(screen.getByLabelText('Title')).toBeInTheDocument()
  expect(screen.getByLabelText('Purpose')).toBeInTheDocument()
  expect(screen.getByLabelText('Starts')).toBeInTheDocument()
  expect(screen.getByLabelText('Ends')).toBeInTheDocument()
  expect(screen.getByLabelText('Expected attendance')).toBeInTheDocument()
  expect(screen.getByLabelText('Description')).toBeInTheDocument()
})

it('sends every field that was filled in', async () => {
  const user = userEvent.setup()
  createEventMock.mockResolvedValue(created)

  render(<NewEventPage session={organiser} />)
  await fillRequired(user)
  await user.type(screen.getByLabelText('Purpose'), 'Welcome the new intake.')
  await user.type(screen.getByLabelText('Expected attendance'), '120')
  await user.type(screen.getByLabelText('Description'), 'Talks.')
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  await waitFor(() => expect(createEventMock).toHaveBeenCalled())
  expect(createEventMock.mock.calls[0][0]).toEqual({
    title: 'Faculty Welcome Night',
    purpose: 'Welcome the new intake.',
    description: 'Talks.',
    startsAt: '2026-11-02T18:00',
    endsAt: null,
    expectedAttendance: 120,
    ...NO_NEEDS,
  })
})

it('sends a blank attendance as null, because the column is nullable', async () => {
  const user = userEvent.setup()
  createEventMock.mockResolvedValue(created)

  render(<NewEventPage session={organiser} />)
  await fillRequired(user)
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  await waitFor(() => expect(createEventMock).toHaveBeenCalled())
  const draft = createEventMock.mock.calls[0][0]
  expect(draft.expectedAttendance).toBeNull()
  expect(draft.purpose).toBe('')
})

it('submits the newly created event when Submit is clicked', async () => {
  const user = userEvent.setup()
  createEventMock.mockResolvedValue(created)
  submitEventMock.mockResolvedValue({ ...created, status: 'Submitted' })

  render(<NewEventPage session={organiser} />)
  await fillRequired(user)
  await user.type(screen.getByLabelText('Ends'), '2026-11-02T21:00')
  await user.type(screen.getByLabelText('Purpose'), 'Welcome the new intake.')
  await user.type(screen.getByLabelText('Expected attendance'), '120')
  await user.type(screen.getByLabelText('Description'), 'Talks.')
  await answerNeeds(user)
  await user.click(screen.getByRole('button', { name: 'Submit' }))

  await waitFor(() => expect(submitEventMock).toHaveBeenCalledWith('101', organiser))
})

it('requires purpose and attendance before submitting', async () => {
  const user = userEvent.setup()

  render(<NewEventPage session={organiser} />)
  await fillRequired(user)
  await user.type(screen.getByLabelText('Ends'), '2026-11-02T21:00')
  await user.click(screen.getByRole('button', { name: 'Submit' }))

  expect(await screen.findByText('Give the event a purpose.')).toBeInTheDocument()
  expect(screen.getByText('Give the expected attendance.')).toBeInTheDocument()
  expect(createEventMock).not.toHaveBeenCalled()
})

it('sets today as the earliest selectable start date', () => {
  render(<NewEventPage session={organiser} />)

  const today = new Date()
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(
    today.getDate(),
  ).padStart(2, '0')}`
  expect(screen.getByLabelText('Starts')).toHaveAttribute('min', `${iso}T00:00`)
})

it('keeps an attendance of zero, which is not the same as leaving it blank', async () => {
  const user = userEvent.setup()
  createEventMock.mockResolvedValue(created)

  render(<NewEventPage session={organiser} />)
  await user.type(screen.getByLabelText('Expected attendance'), '0')
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  await waitFor(() => expect(createEventMock).toHaveBeenCalled())
  expect(createEventMock.mock.calls[0][0].expectedAttendance).toBe(0)
})

it('rejects a completely empty draft', async () => {
  const user = userEvent.setup()

  render(<NewEventPage session={organiser} />)
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  expect(
    await screen.findByText('Enter at least one letter or number in any field to save a draft.'),
  ).toBeInTheDocument()
  expect(createEventMock).not.toHaveBeenCalled()
})

it('rejects a draft containing only whitespace and punctuation', async () => {
  const user = userEvent.setup()

  render(<NewEventPage session={organiser} />)
  await user.type(screen.getByLabelText('Title'), '   ')
  await user.type(screen.getByLabelText('Purpose'), '---')
  await user.type(screen.getByLabelText('Description'), '!@#')
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/at least one letter or number/i)
  expect(createEventMock).not.toHaveBeenCalled()
})

it('allows a description-only draft and preserves its whitespace exactly', async () => {
  const user = userEvent.setup()
  createEventMock.mockResolvedValue({ ...created, title: '', startsAt: '' })

  render(<NewEventPage session={organiser} />)
  const description = '  First line\n    indented line\n  '
  await user.type(screen.getByLabelText('Description'), description)
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  await waitFor(() => expect(createEventMock).toHaveBeenCalled())
  expect(createEventMock.mock.calls[0][0]).toEqual({
    title: '',
    purpose: '',
    description,
    startsAt: '',
    endsAt: null,
    expectedAttendance: null,
    ...NO_NEEDS,
  })
})

it('still requires a title and date when submitting', async () => {
  const user = userEvent.setup()

  render(<NewEventPage session={organiser} />)
  await user.type(screen.getByLabelText('Description'), 'Planning notes')
  await user.click(screen.getByRole('button', { name: 'Submit' }))

  expect(await screen.findByText('Give the event a title.')).toBeInTheDocument()
  expect(screen.getByText('Give the event a date.')).toBeInTheDocument()
  expect(createEventMock).not.toHaveBeenCalled()
})

it('refuses an attendance that is not a whole number', async () => {
  const user = userEvent.setup()

  render(<NewEventPage session={organiser} />)
  await fillRequired(user)
  await user.type(screen.getByLabelText('Expected attendance'), '-4')
  await user.click(screen.getByRole('button', { name: 'Save as draft' }))

  expect(
    await screen.findByText('Enter a whole number of people, or leave it blank.'),
  ).toBeInTheDocument()
  expect(createEventMock).not.toHaveBeenCalled()
})

it('lets only an Organiser create an event', () => {
  render(<NewEventPage session={buildSession({ role: 'Event Coordinator' })} />)

  expect(screen.getByText('Only Organisers create events')).toBeInTheDocument()
  expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
})

// --- US2.1 reopened in Sprint 3: the customer's mandatory fields -----------------

/** Every field filled in and valid, the needs included. */
async function fillAll(user: ReturnType<typeof userEvent.setup>) {
  await fillRequired(user)
  await user.type(screen.getByLabelText('Ends'), '2026-11-02T21:00')
  await user.type(screen.getByLabelText('Purpose'), 'Welcome the new intake.')
  await user.type(screen.getByLabelText('Expected attendance'), '120')
  await user.type(screen.getByLabelText('Description'), 'Talks and a campus tour.')
  await answerNeeds(user)
}

// Typing every field is slow under coverage instrumentation, so allow longer.
describe('US2.1 (Sprint 3) — mandatory fields on Submit', { timeout: 15_000 }, () => {
  it('offers every field the customer listed', () => {
    render(<NewEventPage session={organiser} />)

    for (const label of [
      'Title',
      'Description',
      'Purpose',
      'Starts',
      'Ends',
      'Expected attendance',
      'Preferred layout',
      'Equipment needs',
      'Registration needs',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    expect(screen.getByRole('group', { name: 'Venue requirements' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Accessibility needs' })).toBeInTheDocument()
  })

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

  it('blocks Submit when only a need is unanswered', async () => {
    const user = userEvent.setup()

    render(<NewEventPage session={organiser} />)
    await fillAll(user)
    const registration = screen.getByRole('group', { name: 'Registration needs' })
    await user.click(within(registration).getByLabelText(NOT_REQUIRED))
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(SUBMIT_BLOCKED)
    expect(screen.getByText(MISSING_MESSAGES.registrationNeeds)).toBeInTheDocument()
    expect(screen.queryByText(MISSING_MESSAGES.venueRequirements)).not.toBeInTheDocument()
    expect(createEventMock).not.toHaveBeenCalled()
  })

  it('clears a field’s error as soon as it is answered', async () => {
    const user = userEvent.setup()

    render(<NewEventPage session={organiser} />)
    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText(MISSING_MESSAGES.venueRequirements)

    const venue = screen.getByRole('group', { name: 'Venue requirements' })
    await user.click(within(venue).getByLabelText('Lectern'))
    await user.type(screen.getByLabelText('Description'), 'Talks.')

    expect(screen.queryByText(MISSING_MESSAGES.venueRequirements)).not.toBeInTheDocument()
    expect(screen.queryByText('Give the event a description.')).not.toBeInTheDocument()
    expect(screen.getByText(MISSING_MESSAGES.preferredLayout)).toBeInTheDocument()
  })

  it('submits a complete request — every field written, described needs trimmed', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)
    submitEventMock.mockResolvedValue({ ...created, status: 'Submitted' })

    render(<NewEventPage session={organiser} />)
    await fillAll(user)
    await user.type(screen.getByLabelText('Equipment needs'), '  ')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => expect(submitEventMock).toHaveBeenCalledWith('101', organiser))
    expect(createEventMock.mock.calls[0][0]).toEqual({
      title: 'Faculty Welcome Night',
      purpose: 'Welcome the new intake.',
      description: 'Talks and a campus tour.',
      startsAt: '2026-11-02T18:00',
      endsAt: '2026-11-02T21:00',
      expectedAttendance: 120,
      ...ANSWERED_NEEDS,
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
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

  it('shows the server’s refusal if it still finds something missing', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)
    submitEventMock.mockRejectedValue(new EventRuleError(MISSING_MESSAGES.preferredLayout))

    render(<NewEventPage session={organiser} />)
    await fillAll(user)
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(MISSING_MESSAGES.preferredLayout)
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

  it('saves a draft holding only some needs, exactly as typed', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)

    render(<NewEventPage session={organiser} />)
    await user.selectOptions(screen.getByLabelText('Preferred layout'), 'Cabaret')
    await user.type(screen.getByLabelText('Equipment needs'), ' 2 mics ')
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(createEventMock).toHaveBeenCalled())
    expect(createEventMock.mock.calls[0][0]).toEqual({
      title: '',
      purpose: '',
      description: '',
      startsAt: '',
      endsAt: null,
      expectedAttendance: null,
      ...NO_NEEDS,
      preferredLayout: 'Cabaret',
      equipmentNeeds: ' 2 mics ',
    })
  })
})

describe('US2.1 — expected attendance upper bound', () => {
  it('refuses more people than the database column holds, even on a draft', async () => {
    const user = userEvent.setup()

    render(<NewEventPage session={organiser} />)
    await user.type(screen.getByLabelText('Expected attendance'), '2147483648')
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    expect(
      await screen.findByText('Expected attendance must be 2,147,483,647 or fewer.'),
    ).toBeInTheDocument()
    expect(createEventMock).not.toHaveBeenCalled()
  })

  it('accepts the largest number the column holds', async () => {
    const user = userEvent.setup()
    createEventMock.mockResolvedValue(created)

    render(<NewEventPage session={organiser} />)
    await user.type(screen.getByLabelText('Expected attendance'), '2147483647')
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(createEventMock).toHaveBeenCalled())
    expect(createEventMock.mock.calls[0][0].expectedAttendance).toBe(2147483647)
  })
})
