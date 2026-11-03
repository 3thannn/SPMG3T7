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
  'Event Organiser': [
    'events:create',
    'events:read:own',
    'events:submit',
    // US4.6: cancel an event they own.
    'events:cancel',
    'notifications:read',
    // US20.3: who registered for an event they own.
    'registrations:read',
    // D3: open and close registration on an event they own.
    'registration:manage',
  ],
  'Event Coordinator': [
    'events:read:submitted',
    'events:review',
    'events:complete',
    // US4.6: cancel an event assigned to them.
    'events:cancel',
    'users:read',
    'venues:read',
    // US14.1: request venues for the events assigned to them.
    'bookings:request',
    'equipment:read',
    'equipment:request',
    // US4.4: send a ready event for its safety check.
    'safety:submit',
    // US4.7: confirm it once every approval is in.
    'events:confirm',
    // US10.2: told about assignments and booking or safety problems.
    'notifications:read',
    // US20.1: registration on the events assigned to them.
    'registration:manage',
    // US20.3: who registered for the events assigned to them.
    'registrations:read',
  ],
  // US1.4 + US8.2/8.3/8.6: Coordinator Lead sees all events, manages assignments.
  'Event Coordinator Lead': [
    'events:read:all',
    'queue:view:unassigned',
    'coordinators:assign',
    'users:read',
    'venues:read',
    'equipment:read',
    // US10.3: told when a submitted event lands in the unassigned queue.
    'notifications:read',
  ],
  // US9.1a-c: Venue Staff maintain the catalogue and hold nothing else.
  'Venue Staff': [
    'venues:read',
    'venues:create',
    'venues:edit',
    'venues:delete',
    // US14.3: tentative holds for a Coordinator.
    'holds:place',
    // US16.1: approve or reject booking requests.
    'bookings:decide',
    // US4.6: told when a cancelled event's bookings are released.
    'notifications:read',
  ],
  // US1.4: Safety Officer reviews safety aspects.
  'Safety Officer': ['safety:review'],
  'Technical Support': ['equipment:read', 'equipment:write', 'equipment:queue', 'notifications:read'],
  // US20.1: registers for Confirmed events. US4.6: told when one is cancelled.
  Attendee: ['registrations:create', 'notifications:read'],
}

const HOME: Record<Role, string> = {
  'Event Organiser': '/events',
  'Event Coordinator': '/events',
  // US8.2: Lead lands on the unassigned queue.
  'Event Coordinator Lead': '/unassigned-queue',
  // The events list is no use to a role that cannot open an event.
  'Venue Staff': '/venues',
  // US1.4: Safety Officer lands on their review queue.
  'Safety Officer': '/safety-review',
  'Technical Support': '/equipment-requests',
  Attendee: '/attend',
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
