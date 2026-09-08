/**
 * US1.3 — which pages each role may open.
 *
 * These assert the client's half: the guard that decides whether a page is even
 * built. The API refuses the matching request on its own, and those refusals are
 * covered by the backend suite.
 */

import { describe, expect, it } from 'vitest'
import { can, canAny, canOpen, denialMessage, guardFor } from './permissions'
import { buildSession } from './test/sessions'
import type { Role } from './status'

const ROLES: Role[] = ['Organiser', 'Coordinator']

describe('can', () => {
  it('reads the permissions the server issued', () => {
    expect(can(buildSession({ role: 'Organiser' }), 'events:create')).toBe(true)
    expect(can(buildSession({ role: 'Organiser' }), 'events:review')).toBe(false)
  })

  it('grants nothing without a session', () => {
    expect(can(null, 'events:create')).toBe(false)
  })

  it('grants nothing when the server issued an empty permission set', () => {
    expect(can(buildSession({ permissions: [] }), 'events:create')).toBe(false)
  })

  it('holding one of several is enough for canAny', () => {
    const coordinator = buildSession({ role: 'Coordinator' })
    expect(canAny(coordinator, ['events:read:own', 'events:read:all'])).toBe(true)
    expect(canAny(coordinator, ['events:create', 'events:submit'])).toBe(false)
  })
})

describe('canOpen', () => {
  it('lets an Organiser into the events screens', () => {
    const organiser = buildSession({ role: 'Organiser' })
    expect(canOpen(organiser, '/events')).toBe(true)
    expect(canOpen(organiser, '/events/new')).toBe(true)
    expect(canOpen(organiser, '/events/evt_seed0001')).toBe(true)
  })

  it('lets a Coordinator read events but not create one', () => {
    // The boundary between the two roles: an Organiser proposes, a Coordinator
    // reviews. Reading is shared; creating is not.
    const coordinator = buildSession({ role: 'Coordinator' })
    expect(canOpen(coordinator, '/events')).toBe(true)
    expect(canOpen(coordinator, '/events/evt_seed0001')).toBe(true)
    expect(canOpen(coordinator, '/events/new')).toBe(false)
  })

  it.each(ROLES)('lets %s open the events list', (role) => {
    expect(canOpen(buildSession({ role }), '/events')).toBe(true)
  })

  it('blocks every route without a session', () => {
    expect(canOpen(null, '/events')).toBe(false)
    expect(canOpen(null, '/events/new')).toBe(false)
  })

  it('guards an unknown route on having a session alone', () => {
    // An unlisted route is a 404, and a signed-in user should see the 404
    // rather than a denial for a page that does not exist.
    expect(canOpen(buildSession(), '/nowhere')).toBe(true)
    expect(canOpen(null, '/nowhere')).toBe(false)
  })

  it('treats /events/new as creating, not as an event with the id "new"', () => {
    const coordinator = buildSession({ role: 'Coordinator' })
    expect(guardFor('/events/new')?.anyOf).toEqual(['events:create'])
    expect(canOpen(coordinator, '/events/new')).toBe(false)
  })

  it('refuses an Organiser whose permissions were somehow stripped', () => {
    // The role name alone grants nothing; the permission list is what counts.
    expect(canOpen(buildSession({ role: 'Organiser', permissions: [] }), '/events')).toBe(false)
  })
})

describe('denialMessage', () => {
  it('names the role, what was refused, and who it is for', () => {
    expect(denialMessage(buildSession({ role: 'Coordinator' }), '/events/new')).toBe(
      'The Coordinator role cannot open creating an event. That is available to Organisers.',
    )
  })

  it('describes the list as a page rather than an action', () => {
    expect(denialMessage(buildSession({ role: 'Coordinator' }), '/events')).toBe(
      'The Coordinator role cannot open the events list. That is available to Organisers and Event Coordinators.',
    )
  })

  it.each(ROLES)('always names the %s role rather than saying only "denied"', (role) => {
    const message = denialMessage(buildSession({ role }), '/events/new')
    expect(message).toContain(role)
    expect(message.length).toBeGreaterThan(30)
  })

  it('still says something useful for a route with no specific rule', () => {
    expect(denialMessage(buildSession({ role: 'Coordinator' }), '/nowhere')).toContain(
      'Coordinator',
    )
  })
})
