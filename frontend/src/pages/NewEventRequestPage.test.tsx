/**
 * The event request form — Event Request Creation.
 *
 * `eventRequests.test.ts` pins the rules down one at a time. This file is about
 * the page: that the form asks for what the story says it asks for, that a
 * refusal lands beside the field it is about, that nothing is sent until the
 * form is complete, and that a successful submit lands the Organiser on the
 * event it just made.
 *
 * `createEventRequest` is mocked rather than the network: what this page owes
 * the module is a complete set of fields, and asserting that against the
 * function is more direct than reconstructing it from a request body.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NewEventRequestPage from './NewEventRequestPage'
import { EventRequestError } from '../eventRequests'
import { buildSession } from '../test/sessions'
import type { EventRecord } from '../eventsStore'

const createEventRequest = vi.hoisted(() => vi.fn())
const navigate = vi.hoisted(() => vi.fn())

vi.mock('../eventRequests', async (importOriginal) => {
  // The real validation is kept: this page's job is to run it and place what it
  // says, so mocking it out would leave the assertions testing the mock.
  const actual = await importOriginal<typeof import('../eventRequests')>()
  return { ...actual, createEventRequest }
})

vi.mock('../router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../router')>()
  return { ...actual, navigate }
})

/** A date comfortably ahead of whenever the suite runs. */
const FUTURE = `${new Date().getFullYear() + 1}-11-02`

const SUBMITTED: EventRecord = {
  id: '77',
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: '',
  startsAt: `${FUTURE}T18:00`,
  endsAt: `${FUTURE}T21:30`,
  expectedAttendance: 120,
  status: 'Submitted',
  organiserId: 'user_1',
  organiserName: 'Dylan',
  createdAt: `${FUTURE}T09:00`,
  updatedAt: `${FUTURE}T09:00`,
  history: [],
}

function renderPage(role: 'Event Organiser' | 'Event Coordinator' = 'Event Organiser') {
  render(<NewEventRequestPage session={buildSession({ role })} />)
  return userEvent.setup()
}

/** Fill the whole form, leaving out whatever the test wants missing. */
async function fillIn(
  user: ReturnType<typeof userEvent.setup>,
  skip: string[] = [],
  overrides: Record<string, string> = {},
) {
  const entries: Record<string, string> = {
    'Event name': 'Faculty Welcome Night',
    Purpose: 'Welcome the new intake.',
    'Proposed date': FUTURE,
    'Start time': '18:00',
    'End time': '21:30',
    'Expected attendance': '120',
    ...overrides,
  }
  for (const [label, value] of Object.entries(entries)) {
    if (skip.includes(label) || !value) continue
    await user.clear(screen.getByLabelText(label))
    await user.type(screen.getByLabelText(label), value)
  }
}

async function submitForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Submit request' }))
}

beforeEach(() => {
  createEventRequest.mockReset()
  navigate.mockReset()
  createEventRequest.mockResolvedValue(SUBMITTED)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('the form', () => {
  it('asks for every field the story names', () => {
    renderPage()

    expect(screen.getByLabelText('Event name')).toBeInTheDocument()
    expect(screen.getByLabelText('Purpose')).toBeInTheDocument()
    expect(screen.getByLabelText('Proposed date')).toBeInTheDocument()
    expect(screen.getByLabelText('Start time')).toBeInTheDocument()
    expect(screen.getByLabelText('End time')).toBeInTheDocument()
    expect(screen.getByLabelText('Expected attendance')).toBeInTheDocument()
  })

  it('marks the description as the one optional field', () => {
    renderPage()

    expect(screen.getByLabelText('Description (optional)')).toBeInTheDocument()
  })

  it('says the request will be submitted rather than saved as a draft', () => {
    renderPage()

    expect(screen.getByText('Submitted')).toBeInTheDocument()
    expect(screen.getByText(/no draft to come back to/i)).toBeInTheDocument()
  })

  it('uses plain date, time and number inputs — no catalogue lookups yet', () => {
    // Venue and Equipment arrive in Sprint 2 and 3; until then every field is
    // something the Organiser types.
    renderPage()

    expect(screen.getByLabelText('Proposed date')).toHaveAttribute('type', 'date')
    expect(screen.getByLabelText('Start time')).toHaveAttribute('type', 'time')
    expect(screen.getByLabelText('End time')).toHaveAttribute('type', 'time')
    expect(screen.getByLabelText('Expected attendance')).toHaveAttribute('type', 'number')
  })

  it('stops the date picker offering a day in the past', () => {
    renderPage()
    const today = new Date()
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(
      today.getDate(),
    ).padStart(2, '0')}`

    expect(screen.getByLabelText('Proposed date')).toHaveAttribute('min', iso)
  })
})

describe('submitting a complete request', () => {
  it('sends it', async () => {
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await waitFor(() => expect(createEventRequest).toHaveBeenCalledTimes(1))
  })

  it('sends exactly what was typed', async () => {
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await waitFor(() =>
      expect(createEventRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Faculty Welcome Night',
          purpose: 'Welcome the new intake.',
          proposedDate: FUTURE,
          startTime: '18:00',
          endTime: '21:30',
          expectedAttendance: '120',
        }),
        expect.anything(),
      ),
    )
  })

  it('sends the description when one is given', async () => {
    const user = renderPage()
    await fillIn(user)
    await user.type(screen.getByLabelText('Description (optional)'), 'Talks, then supper.')

    await submitForm(user)

    await waitFor(() => expect(createEventRequest).toHaveBeenCalled())
    expect(createEventRequest.mock.calls[0][0].description).toBe('Talks, then supper.')
  })

  it('sends without a description, which is optional', async () => {
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await waitFor(() => expect(createEventRequest).toHaveBeenCalled())
    expect(createEventRequest.mock.calls[0][0].description).toBe('')
  })

  it('goes to the event it just created', async () => {
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/events/77'))
  })

  it('says it is working while the request is in flight', async () => {
    let release: (event: EventRecord) => void = () => {}
    createEventRequest.mockReturnValue(
      new Promise<EventRecord>((resolve) => {
        release = resolve
      }),
    )
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    expect(await screen.findByRole('button', { name: 'Submitting…' })).toBeDisabled()
    release(SUBMITTED)
  })
})

describe('an incomplete request', () => {
  it('is not sent at all', async () => {
    const user = renderPage()

    await submitForm(user)

    expect(createEventRequest).not.toHaveBeenCalled()
  })

  it('complains about every empty field in one pass', async () => {
    const user = renderPage()

    await submitForm(user)

    expect(await screen.findByText('Give the event a name.')).toBeInTheDocument()
    expect(screen.getByText('Say what the event is for.')).toBeInTheDocument()
    expect(screen.getByText('Give the event a proposed date.')).toBeInTheDocument()
    expect(screen.getByText('Give the event a start time.')).toBeInTheDocument()
    expect(screen.getByText('Give the event an end time.')).toBeInTheDocument()
    expect(screen.getByText('Give the expected attendance.')).toBeInTheDocument()
  })

  it('does not complain about the description', async () => {
    const user = renderPage()

    await submitForm(user)

    await screen.findByText('Give the event a name.')
    expect(screen.getByLabelText('Description (optional)')).toHaveAttribute(
      'aria-invalid',
      'false',
    )
  })

  it('marks the field itself as invalid, not only the message', async () => {
    const user = renderPage()

    await submitForm(user)

    await waitFor(() =>
      expect(screen.getByLabelText('Event name')).toHaveAttribute('aria-invalid', 'true'),
    )
  })

  it('points the field at its own message for a screen reader', async () => {
    const user = renderPage()

    await submitForm(user)

    await waitFor(() =>
      expect(screen.getByLabelText('Event name')).toHaveAttribute(
        'aria-describedby',
        'name-error',
      ),
    )
  })

  it('clears a complaint as soon as that field is being fixed', async () => {
    const user = renderPage()
    await submitForm(user)
    await screen.findByText('Give the event a name.')

    await user.type(screen.getByLabelText('Event name'), 'A')

    expect(screen.queryByText('Give the event a name.')).not.toBeInTheDocument()
    // The others stay until the next submit re-checks them.
    expect(screen.getByText('Say what the event is for.')).toBeInTheDocument()
  })
})

describe('the validation rules, through the form', () => {
  it('refuses a date in the past', async () => {
    const user = renderPage()
    await fillIn(user, [], { 'Proposed date': '2020-01-01' })

    await submitForm(user)

    expect(await screen.findByText('The proposed date cannot be in the past.')).toBeInTheDocument()
    expect(createEventRequest).not.toHaveBeenCalled()
  })

  it('refuses an end time before the start', async () => {
    const user = renderPage()
    await fillIn(user, [], { 'End time': '17:00' })

    await submitForm(user)

    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeInTheDocument()
    expect(createEventRequest).not.toHaveBeenCalled()
  })

  it('refuses an end time equal to the start', async () => {
    const user = renderPage()
    await fillIn(user, [], { 'End time': '18:00' })

    await submitForm(user)

    expect(
      await screen.findByText('The end time must be after the start time.'),
    ).toBeInTheDocument()
  })

  it('refuses an attendance of zero', async () => {
    const user = renderPage()
    await fillIn(user, [], { 'Expected attendance': '0' })

    await submitForm(user)

    expect(await screen.findByText('Expected attendance must be at least 1.')).toBeInTheDocument()
    expect(createEventRequest).not.toHaveBeenCalled()
  })

  it('refuses a negative attendance', async () => {
    const user = renderPage()
    await fillIn(user, [], { 'Expected attendance': '-4' })

    await submitForm(user)

    expect(await screen.findByText('Expected attendance must be at least 1.')).toBeInTheDocument()
  })

  it('caps the name and purpose at their column widths in the field itself', () => {
    // The first line of defence, so an over-long entry cannot be typed at all.
    // `validate` re-checks it for the paths a keyboard does not go through, and
    // the server checks it again after that.
    renderPage()

    expect(screen.getByLabelText('Event name')).toHaveAttribute('maxlength', '255')
    expect(screen.getByLabelText('Purpose')).toHaveAttribute('maxlength', '500')
  })

  it('accepts an event today', async () => {
    const today = new Date()
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(
      today.getDate(),
    ).padStart(2, '0')}`
    const user = renderPage()
    await fillIn(user, [], { 'Proposed date': iso })

    await submitForm(user)

    await waitFor(() => expect(createEventRequest).toHaveBeenCalled())
  })
})

describe('when the server refuses', () => {
  it('shows the reason it gave', async () => {
    createEventRequest.mockRejectedValue(
      new EventRequestError('The proposed date cannot be in the past.'),
    )
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The proposed date cannot be in the past.',
    )
  })

  it('falls back to a plain message when the failure carries none', async () => {
    createEventRequest.mockRejectedValue(new TypeError('Failed to fetch'))
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not submit the request. Try again.',
    )
  })

  it('leaves what was typed in place so it can be corrected and sent again', async () => {
    createEventRequest.mockRejectedValue(new EventRequestError('Refused.'))
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await screen.findByRole('alert')
    expect(screen.getByLabelText('Event name')).toHaveValue('Faculty Welcome Night')
  })

  it('re-enables the button so the request can be sent again', async () => {
    createEventRequest.mockRejectedValue(new EventRequestError('Refused.'))
    const user = renderPage()
    await fillIn(user)

    await submitForm(user)

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Submit request' })).toBeEnabled()
  })

  it('clears the last refusal when the form is sent again', async () => {
    createEventRequest.mockRejectedValueOnce(new EventRequestError('Refused.'))
    const user = renderPage()
    await fillIn(user)
    await submitForm(user)
    await screen.findByRole('alert')

    await submitForm(user)

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})

describe('who the page is for', () => {
  it('turns a Coordinator away', async () => {
    renderPage('Event Coordinator')

    expect(screen.getByText('Only Organisers raise event requests')).toBeInTheDocument()
    expect(screen.queryByLabelText('Event name')).not.toBeInTheDocument()
  })

  it('tells the Coordinator which role they are signed in as', () => {
    renderPage('Event Coordinator')

    expect(screen.getByText(/Event Coordinator/)).toBeInTheDocument()
  })

  it('offers the Coordinator a way back to the events list', async () => {
    const user = renderPage('Event Coordinator')

    await user.click(screen.getByRole('button', { name: 'Back to events' }))

    expect(navigate).toHaveBeenCalledWith('/events')
  })
})

describe('leaving the form', () => {
  it('cancels back to the events list', async () => {
    const user = renderPage()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(navigate).toHaveBeenCalledWith('/events')
    expect(createEventRequest).not.toHaveBeenCalled()
  })

  it('goes back through the breadcrumb without a page load', async () => {
    const user = renderPage()

    await user.click(screen.getByRole('link', { name: '← Events' }))

    expect(navigate).toHaveBeenCalledWith('/events')
  })
})
