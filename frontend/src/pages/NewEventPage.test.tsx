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

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import NewEventPage from './NewEventPage'
import { createEvent, submitEvent, type EventRecord } from '../eventsStore'
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
