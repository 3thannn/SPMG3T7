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

/** Every role the app models. */
const ROLES: Role[] = [
  'Event Organiser',
  'Event Coordinator',
  'Event Coordinator Lead',
  'Venue Staff',
  'Safety Officer',
  'Technical Support',
]

/**
 * The roles with event permissions. Venue Staff is deliberately absent: it
 * maintains the venue catalogue and holds nothing on events, so asserting it
 * could open the events list would assert the opposite of the rule.
 */
const EVENT_ROLES: Role[] = ['Event Organiser', 'Event Coordinator']

describe('can', () => {
  it('reads the permissions the server issued', () => {
    expect(can(buildSession({ role: 'Event Organiser' }), 'events:create')).toBe(true)
    expect(can(buildSession({ role: 'Event Organiser' }), 'events:review')).toBe(false)
  })

  it('grants nothing without a session', () => {
    expect(can(null, 'events:create')).toBe(false)
  })

  it('grants nothing when the server issued an empty permission set', () => {
    expect(can(buildSession({ permissions: [] }), 'events:create')).toBe(false)
  })

  it('holding one of several is enough for canAny', () => {
    const coordinator = buildSession({ role: 'Event Coordinator' })
    expect(canAny(coordinator, ['events:read:own', 'events:read:submitted'])).toBe(true)
    expect(canAny(coordinator, ['events:create', 'events:submit'])).toBe(false)
  })
})

describe('canOpen', () => {
  it('lets Tech Support maintain equipment and see only its request queue and notices', () => {
    const support = buildSession({ role: 'Technical Support' })
    expect(canOpen(support, '/equipment')).toBe(true)
    expect(canOpen(support, '/equipment/new')).toBe(true)
    expect(canOpen(support, '/equipment/1/edit')).toBe(true)
    expect(canOpen(support, '/equipment-requests/17')).toBe(true)
    expect(canOpen(support, '/notifications')).toBe(true)
    expect(canOpen(support, '/events/101')).toBe(false)
    expect(canOpen(buildSession({ role: 'Event Coordinator' }), '/equipment/new')).toBe(false)
  })
  it('lets an Organiser into the events screens', () => {
    const organiser = buildSession({ role: 'Event Organiser' })
    expect(canOpen(organiser, '/events')).toBe(true)
    expect(canOpen(organiser, '/events/new')).toBe(true)
    expect(canOpen(organiser, '/events/evt_seed0001')).toBe(true)
  })

  it('lets a Coordinator read events but not create one', () => {
    // The boundary between the two roles: an Organiser proposes, a Coordinator
    // reviews. Reading is shared; creating is not.
    const coordinator = buildSession({ role: 'Event Coordinator' })
    expect(canOpen(coordinator, '/events')).toBe(true)
    expect(canOpen(coordinator, '/events/evt_seed0001')).toBe(true)
    expect(canOpen(coordinator, '/events/new')).toBe(false)
  })

  it.each(EVENT_ROLES)('lets %s open the events list', (role) => {
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
    const coordinator = buildSession({ role: 'Event Coordinator' })
    expect(guardFor('/events/new')?.anyOf).toEqual(['events:create'])
    expect(canOpen(coordinator, '/events/new')).toBe(false)
  })

  it('refuses an Organiser whose permissions were somehow stripped', () => {
    // The role name alone grants nothing; the permission list is what counts.
    expect(canOpen(buildSession({ role: 'Event Organiser', permissions: [] }), '/events')).toBe(false)
  })
})

describe('denialMessage', () => {
  it('names the role, what was refused, and who it is for', () => {
    expect(denialMessage(buildSession({ role: 'Event Coordinator' }), '/events/new')).toBe(
      'The Event Coordinator role cannot open creating an event. That is available to Organisers.',
    )
  })

  it('describes the list as a page rather than an action', () => {
    expect(denialMessage(buildSession({ role: 'Event Coordinator' }), '/events')).toBe(
      'The Event Coordinator role cannot open the events list. That is available to Organisers, Event Coordinators, and Coordinator Lead.',
    )
  })

  it.each(ROLES)('always names the %s role rather than saying only "denied"', (role) => {
    const message = denialMessage(buildSession({ role }), '/events/new')
    expect(message).toContain(role)
    expect(message.length).toBeGreaterThan(30)
  })

  it('still says something useful for a route with no specific rule', () => {
    expect(denialMessage(buildSession({ role: 'Event Coordinator' }), '/nowhere')).toContain(
      'Event Coordinator',
    )
  })
})

describe('the venue catalogue (US9.2)', () => {
  const coordinator = buildSession({ role: 'Event Coordinator' })
  const organiser = buildSession({ role: 'Event Organiser' })

  it('lets a Coordinator into the catalogue and any record in it', () => {
    expect(canOpen(coordinator, '/venues')).toBe(true)
    expect(canOpen(coordinator, '/venues/1')).toBe(true)
  })

  it('keeps an Organiser out of both', () => {
    // US9.2 is a Coordinator's story, and the server agrees — an Organiser's
    // session carries no venues:read for this to read.
    expect(canOpen(organiser, '/venues')).toBe(false)
    expect(canOpen(organiser, '/venues/1')).toBe(false)
  })

  it('guards a venue record on venues:read', () => {
    expect(guardFor('/venues/1')?.anyOf).toEqual(['venues:read'])
  })

  it('explains the refusal rather than only denying it', () => {
    expect(denialMessage(organiser, '/venues')).toBe(
      'The Event Organiser role cannot open the venue catalogue. That is available to Event Coordinators and Venue Staff.',
    )
    expect(denialMessage(organiser, '/venues/1')).toContain('venue details')
  })

  it('needs a session like every other guarded route', () => {
    expect(canOpen(null, '/venues')).toBe(false)
    expect(canOpen(null, '/venues/1')).toBe(false)
  })
})

describe('maintaining the catalogue (US9.1a-c)', () => {
  const venueStaff = buildSession({ role: 'Venue Staff' })
  const coordinator = buildSession({ role: 'Event Coordinator' })
  const organiser = buildSession({ role: 'Event Organiser' })

  it('lets Venue Staff add and edit a venue', () => {
    expect(canOpen(venueStaff, '/venues/new')).toBe(true)
    expect(canOpen(venueStaff, '/venues/1/edit')).toBe(true)
  })

  it('lets Venue Staff read the catalogue they maintain', () => {
    expect(canOpen(venueStaff, '/venues')).toBe(true)
    expect(canOpen(venueStaff, '/venues/1')).toBe(true)
  })

  it('keeps a Coordinator out of the write screens', () => {
    // A Coordinator reads the catalogue; maintaining it is a different job.
    expect(canOpen(coordinator, '/venues/new')).toBe(false)
    expect(canOpen(coordinator, '/venues/1/edit')).toBe(false)
  })

  it('keeps an Organiser out of all of it', () => {
    expect(canOpen(organiser, '/venues')).toBe(false)
    expect(canOpen(organiser, '/venues/new')).toBe(false)
    expect(canOpen(organiser, '/venues/1/edit')).toBe(false)
  })

  it('keeps Venue Staff out of the events screens', () => {
    // The permission goes one way: the catalogue is not a door into events.
    expect(canOpen(venueStaff, '/events')).toBe(false)
    expect(canOpen(venueStaff, '/events/new')).toBe(false)
    expect(canOpen(venueStaff, '/events/1')).toBe(false)
  })

  it('reads the edit route as editing rather than as a venue id', () => {
    // Checked before the detail route, which would otherwise match "1" and let
    // anyone who can read a venue open the form that changes one.
    expect(guardFor('/venues/1/edit')?.anyOf).toEqual(['venues:edit'])
  })

  it('explains each refusal rather than only denying it', () => {
    expect(denialMessage(coordinator, '/venues/new')).toBe(
      'The Event Coordinator role cannot open adding a venue. That is available to Venue Staff.',
    )
    expect(denialMessage(coordinator, '/venues/1/edit')).toContain('editing a venue')
  })
})

describe('notifications (US10.1)', () => {
  it('TC-F17 lets an Organiser and a Coordinator open notifications and keeps other roles out', () => {
    expect(canOpen(buildSession({ role: 'Event Organiser' }), '/notifications')).toBe(true)
    // US10.2
    expect(canOpen(buildSession({ role: 'Event Coordinator' }), '/notifications')).toBe(true)
    expect(canOpen(buildSession({ role: 'Event Coordinator Lead' }), '/notifications')).toBe(false)
    expect(canOpen(buildSession({ role: 'Safety Officer' }), '/notifications')).toBe(false)
  })

  it('lets Venue Staff open notifications, to hear about released bookings (US4.6)', () => {
    expect(canOpen(buildSession({ role: 'Venue Staff' }), '/notifications')).toBe(true)
  })
})

describe('booking requests (US16.1)', () => {
  it('TC-DF18 lets only Venue Staff open the booking requests', () => {
    expect(canOpen(buildSession({ role: 'Venue Staff' }), '/booking-requests')).toBe(true)
    for (const role of [
      'Event Organiser',
      'Event Coordinator',
      'Event Coordinator Lead',
      'Safety Officer',
      'Technical Support',
    ] as const) {
      expect(canOpen(buildSession({ role }), '/booking-requests')).toBe(false)
    }
  })
})

describe('booking conflicts (US15.2)', () => {
  it('TC-FF23 lets only Venue Staff open the flagged booking conflicts', () => {
    expect(canOpen(buildSession({ role: 'Venue Staff' }), '/booking-conflicts')).toBe(true)
    for (const role of [
      'Event Organiser',
      'Event Coordinator',
      'Event Coordinator Lead',
      'Safety Officer',
      'Technical Support',
    ] as const) {
      expect(canOpen(buildSession({ role }), '/booking-conflicts')).toBe(false)
    }
    expect(denialMessage(buildSession({ role: 'Event Coordinator' }), '/booking-conflicts')).toBe(
      'The Event Coordinator role cannot open the flagged booking conflicts. That is available to Venue Staff.',
    )
  })
})

describe('registering for events (US20.1)', () => {
  it('lets only Attendees open the events open for registration', () => {
    expect(canOpen(buildSession({ role: 'Attendee' }), '/attend')).toBe(true)
    for (const role of [
      'Event Organiser',
      'Event Coordinator',
      'Event Coordinator Lead',
      'Venue Staff',
      'Safety Officer',
      'Technical Support',
    ] as const) {
      expect(canOpen(buildSession({ role }), '/attend')).toBe(false)
    }
    expect(denialMessage(buildSession({ role: 'Event Organiser' }), '/attend')).toBe(
      'The Event Organiser role cannot open the events open for registration. That is available to Attendees.',
    )
  })

  it('lets only Attendees open their registrations (US20.2)', () => {
    expect(canOpen(buildSession({ role: 'Attendee' }), '/my-registrations')).toBe(true)
    for (const role of ['Event Organiser', 'Event Coordinator', 'Venue Staff'] as const) {
      expect(canOpen(buildSession({ role }), '/my-registrations')).toBe(false)
    }
    expect(denialMessage(buildSession({ role: 'Event Coordinator' }), '/my-registrations')).toBe(
      'The Event Coordinator role cannot open your registrations. That is available to Attendees.',
    )
  })

  it('keeps Attendees out of every internal page', () => {
    const attendee = buildSession({ role: 'Attendee' })
    for (const route of ['/events', '/events/950', '/events/new', '/venues', '/equipment']) {
      expect(canOpen(attendee, route)).toBe(false)
    }
  })

  it('lets Attendees read their notifications, to hear about a cancelled event (US4.6)', () => {
    expect(canOpen(buildSession({ role: 'Attendee' }), '/notifications')).toBe(true)
  })
})

it('opens equipment details to everyone who can read the catalogue', () => {
  expect(guardFor('/equipment/5')?.anyOf).toEqual(['equipment:read'])
})
