/**
 * Which pages a role may open — the client half of US1.3.
 *
 * The permissions themselves are not modelled here. They arrive on the session
 * the server issued, so the browser cannot hold an opinion that drifts from the
 * server's; this module only says which permission each route needs, and how to
 * explain a refusal in words a person can act on.
 *
 * This is not the enforcement point. Hiding a link and blocking a route are
 * courtesies that keep people out of dead ends — the API refuses the request
 * regardless, and that refusal is the rule.
 */

import type { Permission, Session } from './api'

/** Does the signed-in user hold this permission, according to the server? */
export function can(session: Session | null, permission: Permission): boolean {
  return session?.permissions.includes(permission) ?? false
}

/** Does the user hold at least one of these permissions? */
export function canAny(session: Session | null, permissions: readonly Permission[]): boolean {
  return permissions.some((permission) => can(session, permission))
}

type GuardedRoute = {
  /** Holding any one of these is enough to open the route. */
  anyOf: readonly Permission[]
  /** Named as the thing being refused, to drop into a sentence. */
  what: string
  /** Who it is for, so the message says more than "not you". */
  who: string
}

/**
 * Routes that need more than a session. A route absent from this table needs
 * only that the user is signed in, which App checks before it gets here.
 */
const GUARDED: Record<string, GuardedRoute> = {
  '/events': {
    anyOf: ['events:read:own', 'events:read:submitted', 'events:read:all'],
    what: 'the events list',
    who: 'Organisers, Event Coordinators, and Coordinator Lead',
  },
  '/events/new': {
    anyOf: ['events:create'],
    what: 'creating an event',
    who: 'Organisers',
  },
  '/unassigned-queue': {
    anyOf: ['queue:view:unassigned'],
    what: 'the unassigned event queue',
    who: 'Event Coordinator Lead',
  },
  '/team-assignments': {
    anyOf: ['queue:view:unassigned'],
    what: 'team assignments and workload distribution',
    who: 'Event Coordinator Lead',
  },
  '/safety-review': {
    anyOf: ['safety:review'],
    what: 'the safety review queue',
    who: 'Safety Officer',
  },
  '/venues': {
    anyOf: ['venues:read'],
    what: 'the venue catalogue',
    who: 'Event Coordinators and Venue Staff',
  },
  '/venues/new': {
    anyOf: ['venues:create'],
    what: 'adding a venue',
    who: 'Venue Staff',
  },
  '/notifications': {
    anyOf: ['notifications:read'],
    what: 'notifications',
    who: 'Organisers, Event Coordinators, Venue Staff, and Technical Support',
  },
  '/equipment': {
    anyOf: ['equipment:read'],
    what: 'the equipment catalogue',
    who: 'Event Coordinators, Coordinator Lead, and Technical Support',
  },
  '/equipment/new': {
    anyOf: ['equipment:write'],
    what: 'adding equipment',
    who: 'Technical Support',
  },
  '/booking-requests': {
    anyOf: ['bookings:decide'],
    what: 'the venue booking requests',
    who: 'Venue Staff',
  },
  // US15.2: reviewing a clash is part of deciding what a venue can support.
  '/booking-conflicts': {
    anyOf: ['bookings:decide'],
    what: 'the flagged booking conflicts',
    who: 'Venue Staff',
  },
  '/equipment-requests': {
    anyOf: ['equipment:queue'],
    what: 'the equipment request queue',
    who: 'Technical Support',
  },
  // US20.1: the Confirmed events taking registrations, as Attendees see them.
  '/attend': {
    anyOf: ['registrations:create'],
    what: 'the events open for registration',
    who: 'Attendees',
  },
  // US20.2: an Attendee's own registrations.
  '/my-registrations': {
    anyOf: ['registrations:create'],
    what: 'your registrations',
    who: 'Attendees',
  },
}

/**
 * The rule for a route, treating every /events/:id and /venues/:id page as its
 * detail route.
 */
export function guardFor(route: string): GuardedRoute | null {
  if (GUARDED[route]) return GUARDED[route]
  if (/^\/equipment\/[^/]+\/edit$/.test(route)) {
    return { anyOf: ['equipment:write'], what: 'editing equipment', who: 'Technical Support' }
  }
  if (/^\/equipment-requests\/[^/]+$/.test(route)) {
    return { anyOf: ['equipment:queue'], what: 'the equipment request queue', who: 'Technical Support' }
  }
  if (/^\/equipment\/[^/]+$/.test(route)) {
    return { anyOf: ['equipment:read'], what: 'equipment details', who: 'Event Coordinators, Coordinator Lead, and Technical Support' }
  }
  if (/^\/events\/[^/]+$/.test(route)) {
    return {
      // US4.4: the Safety Officer opens the events waiting for their check.
      anyOf: ['events:read:own', 'events:read:submitted', 'events:read:all', 'safety:review'],
      what: 'event details',
      who: 'Organisers, Event Coordinators, Coordinator Lead, and Safety Officer',
    }
  }
  // Checked before the detail route, which would otherwise match the id and
  // let anyone who can read a venue open the form that edits one.
  if (/^\/venues\/[^/]+\/edit$/.test(route)) {
    return {
      anyOf: ['venues:edit'],
      what: 'editing a venue',
      who: 'Venue Staff',
    }
  }
  if (/^\/venues\/[^/]+$/.test(route)) {
    return {
      anyOf: ['venues:read'],
      what: 'venue details',
      who: 'Event Coordinators and Venue Staff',
    }
  }
  return null
}

export function canOpen(session: Session | null, route: string): boolean {
  const guard = guardFor(route)
  return guard === null ? session !== null : canAny(session, guard.anyOf)
}

/**
 * Why the page was refused, said plainly: what was blocked, which role is
 * blocked, and who it is for. The server sends its own version of this when a
 * request is actually refused; this one is for the page the user never reaches.
 */
export function denialMessage(session: Session, route: string): string {
  const guard = guardFor(route)
  if (!guard) return `The ${session.role} role does not have access to this page.`
  return `The ${session.role} role cannot open ${guard.what}. That is available to ${guard.who}.`
}
