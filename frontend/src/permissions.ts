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
    anyOf: ['events:read:own', 'events:read:submitted'],
    what: 'the events list',
    who: 'Organisers and Event Coordinators',
  },
  '/events/new': {
    anyOf: ['events:create'],
    what: 'creating an event',
    who: 'Organisers',
  },
}

/** The rule for a route, treating every /events/:id page as the detail route. */
export function guardFor(route: string): GuardedRoute | null {
  if (GUARDED[route]) return GUARDED[route]
  if (/^\/events\/[^/]+$/.test(route)) {
    return {
      anyOf: ['events:read:own', 'events:read:submitted'],
      what: 'event details',
      who: 'Organisers and Event Coordinators',
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
