/**
 * Session builders for tests.
 *
 * These mirror what the API issues for each development account, so a test that
 * renders a signed-in page gets the same permission set the real server would
 * send. Keeping them in one place means a change to the catalogue shows up as a
 * failing test rather than as five stale copies that quietly disagree.
 */

import type { Permission, Session } from '../api'
import type { Role } from '../status'

const PERMISSIONS: Record<Role, Permission[]> = {
  'Event Organiser': ['events:create', 'events:read:own', 'events:submit'],
  'Event Coordinator': [
    'events:read:submitted',
    'events:review',
    'users:read',
    'venues:read',
    // US14.1: request venues for the events assigned to them.
    'bookings:request',
  ],
  // US9.1a-c: Venue Staff maintain the catalogue and hold nothing else.
  'Venue Staff': ['venues:read', 'venues:create', 'venues:edit', 'venues:delete'],
}

const HOME: Record<Role, string> = {
  'Event Organiser': '/events',
  'Event Coordinator': '/events',
  // The events list is no use to a role that cannot open an event.
  'Venue Staff': '/venues',
}

export function buildSession(overrides: Partial<Session> = {}): Session {
  const role = overrides.role ?? 'Event Organiser'
  return {
    token: 'test-token',
    id: 'user_1',
    email: 'dylan@example.edu',
    name: 'Dylan',
    role,
    permissions: PERMISSIONS[role],
    home: HOME[role],
    idleMinutes: 30,
    ...overrides,
  }
}
