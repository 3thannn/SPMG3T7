/**
 * The event store is a client for `/events` now, not a store.
 *
 * So these tests assert what it sends and how it reads what comes back — the
 * rules themselves (who may see what, submitting once) are the server's, and
 * are tested against real requests in backend/tests/test_events.py. Asserting
 * them here as well would be asserting a mock.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  EventRuleError,
  createEvent,
  getEvent,
  listEvents,
  saveEvent,
  submitEvent,
} from './eventsStore'
import { ApiError } from './api'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const session = buildSession({ token: 'session-token', id: '1', name: 'Dylan' })

const EVENT = {
  id: '101',
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks.',
  startsAt: '2026-11-02T18:00',
  expectedAttendance: 120,
  status: 'Draft',
  organiserId: '1',
  organiserName: 'Dylan',
  createdAt: '2026-09-08T10:00:00',
  updatedAt: '2026-09-08T10:00:00',
  history: [
    { from: null, to: 'Draft', at: '2026-09-08T10:00:00', byId: '1', byName: 'Dylan' },
  ],
}

const DRAFT = {
  title: 'Faculty Welcome Night',
  purpose: 'Welcome the new intake.',
  description: 'Talks.',
  startsAt: '2026-11-02T18:00',
  expectedAttendance: 120,
}

function ok(body: unknown, status = 200) {
  return { ok: true, status, json: async () => body }
}

function failure(status: number, code: string, message: string) {
  return { ok: false, status, json: async () => ({ detail: { code, message } }) }
}

/** Stub fetch and hand back the spy, so a test can read what was requested. */
function stubFetch(response: unknown) {
  const spy = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', spy)
  return spy
}

describe('listEvents', () => {
  it('asks the API and returns what it sends', async () => {
    const spy = stubFetch(ok([EVENT]))

    const events = await listEvents(session)

    expect(events).toHaveLength(1)
    expect(events[0].title).toBe('Faculty Welcome Night')
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8000/events',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer session-token' }),
      }),
    )
  })

  it('does not tell the server which role is asking', async () => {
    // The server reads the role from the session. A client that could ask for
    // "submitted events" could simply ask, which is the bug this guards against.
    const spy = stubFetch(ok([]))

    await listEvents(session)

    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/events')
    expect(JSON.stringify(init)).not.toContain('Organiser')
  })
})

describe('getEvent', () => {
  it('returns the event', async () => {
    stubFetch(ok(EVENT))

    expect((await getEvent('101', session))?.id).toBe('101')
  })

  it('reads a 404 as "no such event" rather than throwing', async () => {
    // The server answers 404 both for an event that is gone and for one that is
    // not yours to see, so the page shows the same thing for both.
    stubFetch(failure(404, 'event_not_found', 'That event no longer exists.'))

    expect(await getEvent('999', session)).toBeNull()
  })

  it('still throws for a failure that is not a missing event', async () => {
    stubFetch(failure(401, 'session_expired', 'Your session expired.'))

    await expect(getEvent('101', session)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('createEvent', () => {
  it('posts the draft and returns the created event', async () => {
    const spy = stubFetch(ok(EVENT, 201))

    const created = await createEvent(DRAFT, session)

    expect(created.status).toBe('Draft')
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/events')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(DRAFT)
  })

  it('never sends an organiser — the server takes it from the session', async () => {
    const spy = stubFetch(ok(EVENT, 201))

    await createEvent(DRAFT, session)

    expect(JSON.parse(spy.mock.calls[0][1].body)).not.toHaveProperty('organiserId')
  })

  it('turns a refused draft into a rule error the page can show', async () => {
    stubFetch(failure(400, 'invalid_event', 'Give the event a date.'))

    await expect(createEvent(DRAFT, session)).rejects.toThrow(EventRuleError)
    await expect(createEvent(DRAFT, session)).rejects.toThrow('Give the event a date.')
  })
})

describe('saveEvent', () => {
  it('puts the draft to the event', async () => {
    const spy = stubFetch(ok(EVENT))

    await saveEvent('101', DRAFT, session)

    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('http://localhost:8000/events/101')
    expect(init.method).toBe('PUT')
  })

  it('reports a refusal to edit someone else’s event as a rule error', async () => {
    stubFetch(
      failure(403, 'forbidden', 'Only the Organiser who owns this event can edit it.'),
    )

    await expect(saveEvent('101', DRAFT, session)).rejects.toThrow(EventRuleError)
  })
})

describe('submitEvent', () => {
  it('posts to the submit route', async () => {
    const spy = stubFetch(ok({ ...EVENT, status: 'Submitted' }))

    const submitted = await submitEvent('101', session)

    expect(submitted.status).toBe('Submitted')
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/events/101/submit')
    expect(spy.mock.calls[0][1].method).toBe('POST')
  })

  it('turns a second submit into a rule error carrying the reason', async () => {
    stubFetch(
      failure(
        409,
        'rule_refused',
        'This event has already been submitted. An event can only be submitted once.',
      ),
    )

    await expect(submitEvent('101', session)).rejects.toThrow(
      'This event has already been submitted. An event can only be submitted once.',
    )
  })

  it('lets a lapsed session through as an ApiError, not a rule error', async () => {
    // A rule error is shown in the page; a lapsed session has to end it.
    stubFetch(failure(401, 'session_expired', 'Your session expired.'))

    await expect(submitEvent('101', session)).rejects.not.toBeInstanceOf(EventRuleError)
  })
})
