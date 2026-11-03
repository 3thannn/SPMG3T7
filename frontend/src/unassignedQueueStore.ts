/**
 * US8.2, US8.3, US8.4: Unassigned queue, coordinator assignment, and reassignment for Lead.
 */

import { ApiError, authorizedFetch, type Session, unexpectedFailureMessage } from './api'
import { EventRuleError } from './eventsStore'
import type { EventStatus } from './status'

export type UnassignedEvent = {
  id: string
  title: string
  purpose: string | null
  description: string | null
  startsAt: string | null
  expectedAttendance: number | null
  status: EventStatus
  organiserId: string
  organiserName: string
  submittedAt: string
  coordinatorId: string | null
}

export type Coordinator = {
  id: string
  name: string
  email: string
}

/**
 * US8.2: Fetch unassigned events (Submitted with no coordinator).
 * Only accessible to Coordinator Lead.
 */
export async function listUnassignedEvents(session: Session): Promise<UnassignedEvent[]> {
  try {
    const response = await authorizedFetch('/events/unassigned', session.token)
    return (await response.json()) as UnassignedEvent[]
  } catch (error) {
    throw new Error(unexpectedFailureMessage(error, 'load unassigned events'))
  }
}

/**
 * US8.3: Assign a coordinator to an event.
 * Only accessible to Coordinator Lead.
 */
export async function assignCoordinator(
  session: Session,
  eventId: string,
  coordinatorId: string,
): Promise<void> {
  try {
    await authorizedFetch(`/events/${eventId}/assign`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ coordinatorId }),
    })
  } catch (error) {
    throw new Error(unexpectedFailureMessage(error, 'assign coordinator'))
  }
}

/**
 * US8.4: Reassign an already-assigned event to a different coordinator.
 * Only accessible to Coordinator Lead.
 */
export async function reassignCoordinator(
  session: Session,
  eventId: string,
  coordinatorId: string,
): Promise<void> {
  try {
    await authorizedFetch(`/events/${eventId}/reassign`, session.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ coordinatorId }),
    })
  } catch (error) {
    // US8.4: a refusal says why (a finished event, or one changed meanwhile).
    if (error instanceof ApiError && (error.status === 400 || error.status === 409)) {
      throw new EventRuleError(error.message)
    }
    throw error
  }
}

/**
 * Fetch list of coordinators (for assignment dropdown).
 */
export async function listCoordinators(session: Session): Promise<Coordinator[]> {
  try {
    const response = await authorizedFetch('/auth/users', session.token)
    const allUsers = (await response.json()) as Array<{
      id: string
      name: string
      email: string
      role: string
    }>

    // Filter to only Event Coordinators
    return allUsers
      .filter((user) => user.role === 'Event Coordinator')
      .map((user) => ({ id: user.id, name: user.name, email: user.email }))
  } catch (error) {
    throw new Error(unexpectedFailureMessage(error, 'load coordinators'))
  }
}
