/** US8.2, US8.3, US8.4: the Lead's queue client, and how each call fails. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  assignCoordinator,
  listCoordinators,
  listUnassignedEvents,
  reassignCoordinator,
} from './unassignedQueueStore'
import { ApiError } from './api'
import { EventRuleError } from './eventsStore'
import { failure, ok, sent, stubFetch } from './test/fetch'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const lead = buildSession({ role: 'Event Coordinator Lead', token: 'session-token' })

describe('the queue calls', () => {
  it('lists the unassigned events', async () => {
    const spy = stubFetch(ok([{ id: '7', title: 'Open Day' }]))

    const events = await listUnassignedEvents(lead)

    expect(events[0].id).toBe('7')
    expect(sent(spy).path).toBe('/events/unassigned')
  })

  it('assigns a coordinator by id', async () => {
    const spy = stubFetch(ok({}))

    await assignCoordinator(lead, '7', '2')

    expect(sent(spy)).toEqual({
      path: '/events/7/assign',
      method: 'POST',
      body: { coordinatorId: '2' },
    })
  })

  it('reassigns to a different coordinator', async () => {
    const spy = stubFetch(ok({}))

    await reassignCoordinator(lead, '7', '9')

    expect(sent(spy)).toEqual({
      path: '/events/7/reassign',
      method: 'POST',
      body: { coordinatorId: '9' },
    })
  })

  it('offers only Event Coordinators to assign', async () => {
    stubFetch(
      ok([
        { id: '2', name: 'Priya', email: 'priya@spmg3t7.edu', role: 'Event Coordinator' },
        { id: '3', name: 'Jordan', email: 'jordan@spmg3t7.edu', role: 'Event Coordinator Lead' },
        { id: '1', name: 'Dylan', email: 'dylan@spmg3t7.edu', role: 'Event Organiser' },
      ]),
    )

    const coordinators = await listCoordinators(lead)

    expect(coordinators).toEqual([{ id: '2', name: 'Priya', email: 'priya@spmg3t7.edu' }])
  })
})

describe('when a call fails, the error says what could not be done', () => {
  it.each([
    ['load unassigned events', () => listUnassignedEvents(lead)],
    ['assign coordinator', () => assignCoordinator(lead, '7', '2')],
    ['load coordinators', () => listCoordinators(lead)],
  ])('could not %s', async (doing, call) => {
    stubFetch(failure(500))

    await expect(call()).rejects.toThrow(`Could not ${doing}. The API answered HTTP 500`)
  })
})

describe('US8.4: a reassignment that fails', () => {
  it.each([400, 409])('passes on the server’s reason for a %s refusal', async (status) => {
    stubFetch(failure(status, 'This event is Cancelled, so it can no longer be reassigned.'))

    const refused = reassignCoordinator(lead, '7', '9')

    await expect(refused).rejects.toBeInstanceOf(EventRuleError)
    await expect(refused).rejects.toThrow(
      'This event is Cancelled, so it can no longer be reassigned.',
    )
  })

  it('leaves any other failure for the page to describe', async () => {
    stubFetch(failure(500))

    await expect(reassignCoordinator(lead, '7', '9')).rejects.toBeInstanceOf(ApiError)
  })
})
