import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventDetailPage from './EventDetailPage'
import { getEvent, saveEvent, submitEvent, type EventRecord } from '../eventsStore'
import { buildSession } from '../test/sessions'

vi.mock('../eventsStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../eventsStore')>()),
  getEvent: vi.fn(),
  saveEvent: vi.fn(),
  submitEvent: vi.fn(),
}))

const getEventMock = vi.mocked(getEvent)
const saveEventMock = vi.mocked(saveEvent)
const submitEventMock = vi.mocked(submitEvent)
const organiser = buildSession({ role: 'Event Organiser', id: '1', name: 'Dylan' })

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

afterEach(() => {
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
