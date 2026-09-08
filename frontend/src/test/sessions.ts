/**
 * Session builders for tests.
 *
 * These mirror what the API issues for each seeded account, so a test that
 * renders a signed-in page gets the same permission set the real server would
 * send. Keeping them in one place means a change to the catalogue shows up as a
 * failing test rather than as five stale copies that quietly disagree.
 */

import type { Permission, Session } from '../api'
import type { Role } from '../status'

const PERMISSIONS: Record<Role, Permission[]> = {
  Organiser: ['events:create', 'events:read:own', 'events:submit'],
  Coordinator: ['events:read:all', 'events:review', 'users:read'],
}

const HOME: Record<Role, string> = {
  Organiser: '/events',
  Coordinator: '/events',
}

export function buildSession(overrides: Partial<Session> = {}): Session {
  const role = overrides.role ?? 'Organiser'
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
