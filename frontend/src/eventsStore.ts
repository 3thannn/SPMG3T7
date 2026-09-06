/**
 * Event data access for Sprint 1.
 *
 * The backend has no /events endpoints yet, so this module stands in for them.
 * Every function is async and shaped like the HTTP call that will replace it,
 * so swapping in `fetch` later is a change to this file alone — no page or
 * component needs to move.
 *
 * IMPORTANT: the US4.2 rules enforced here (submit exactly once, audit trail)
 * are mirrored on the client for a responsive UI. They are NOT the enforcement
 * point. A browser store is trivially editable, so the server must re-check
 * both rules and own the timestamps when the real endpoints land.
 */

import {
  checkSubmit,
  submitRefusalMessage,
  type EventStatus,
  type StatusChange,
} from './status'

export type EventRecord = {
  id: string
  title: string
  description: string
  startsAt: string // ISO-8601, or '' while still a rough draft
  location: string
  status: EventStatus
  organiserId: string
  organiserName: string
  createdAt: string
  updatedAt: string
  history: StatusChange[]
}

export type EventDraft = {
  title: string
  description: string
  startsAt: string
  location: string
}

export type Actor = { id: string; name: string }

/** Raised when a write is refused by a business rule, e.g. a second submit. */
export class EventRuleError extends Error {}

const STORAGE_KEY = 'spmg3t7.events.v1'

function nowIso(): string {
  return new Date().toISOString()
}

function newId(): string {
  return `evt_${Math.random().toString(36).slice(2, 10)}`
}

function readAll(): EventRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return seed()
    const parsed = JSON.parse(raw) as EventRecord[]
    return Array.isArray(parsed) ? parsed : seed()
  } catch {
    // A private window or blocked storage should not break the page.
    return seed()
  }
}

function writeAll(events: EventRecord[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(events))
  } catch {
    // Non-fatal: the session keeps working, it just will not persist.
  }
}

/** A couple of events so the list and detail pages are demonstrable on a cold start. */
function seed(): EventRecord[] {
  const created = new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString()
  const events: EventRecord[] = [
    {
      id: 'evt_seed0001',
      title: 'Faculty Welcome Night',
      description: 'Opening social for incoming students, with a short programme of talks.',
      startsAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 21).toISOString().slice(0, 16),
      location: 'Great Hall',
      status: 'Draft',
      organiserId: 'user_organiser',
      organiserName: 'Dylan',
      createdAt: created,
      updatedAt: created,
      history: [
        { from: null, to: 'Draft', at: created, byId: 'user_organiser', byName: 'Dylan' },
      ],
    },
    {
      id: 'evt_seed0002',
      title: 'Inter-Faculty Hackathon',
      description: 'Twenty-four hour build event across four tracks.',
      startsAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 45).toISOString().slice(0, 16),
      location: 'Engineering Block, Level 3',
      status: 'Submitted',
      organiserId: 'user_organiser',
      organiserName: 'Dylan',
      createdAt: created,
      updatedAt: nowIso(),
      history: [
        { from: null, to: 'Draft', at: created, byId: 'user_organiser', byName: 'Dylan' },
        {
          from: 'Draft',
          to: 'Submitted',
          at: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
          byId: 'user_organiser',
          byName: 'Dylan',
        },
      ],
    },
  ]
  writeAll(events)
  return events
}

/**
 * US4.1: an Organiser sees the events they own; a Coordinator sees all events.
 * The role check lives with the caller's session, so both arms are passed in.
 */
export async function listEvents(actor: Actor, seesAll: boolean): Promise<EventRecord[]> {
  const all = readAll()
  const visible = seesAll ? all : all.filter((event) => event.organiserId === actor.id)
  return [...visible].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export async function getEvent(id: string): Promise<EventRecord | null> {
  return readAll().find((event) => event.id === id) ?? null
}

/** A new event always begins as a Draft (US4.2). */
export async function createEvent(draft: EventDraft, actor: Actor): Promise<EventRecord> {
  const at = nowIso()
  const event: EventRecord = {
    id: newId(),
    ...draft,
    status: 'Draft',
    organiserId: actor.id,
    organiserName: actor.name,
    createdAt: at,
    updatedAt: at,
    history: [{ from: null, to: 'Draft', at, byId: actor.id, byName: actor.name }],
  }
  writeAll([event, ...readAll()])
  return event
}

/**
 * US4.2: "Draft stays Draft on save." Saving edits content and never moves the
 * status, so no history entry is written — a save is not a status change.
 */
export async function saveEvent(
  id: string,
  draft: EventDraft,
  actor: Actor,
): Promise<EventRecord> {
  const all = readAll()
  const index = all.findIndex((event) => event.id === id)
  if (index === -1) throw new EventRuleError('That event no longer exists.')

  const existing = all[index]
  if (existing.organiserId !== actor.id) {
    throw new EventRuleError('Only the Organiser who owns this event can edit it.')
  }

  const updated: EventRecord = { ...existing, ...draft, updatedAt: nowIso() }
  all[index] = updated
  writeAll(all)
  return updated
}

/**
 * US4.2: Draft -> Submitted, exactly once, timestamped and attributable. A
 * second submit is refused rather than silently ignored.
 */
export async function submitEvent(id: string, actor: Actor): Promise<EventRecord> {
  const all = readAll()
  const index = all.findIndex((event) => event.id === id)
  if (index === -1) throw new EventRuleError('That event no longer exists.')

  const existing = all[index]
  const check = checkSubmit(existing, actor.id)
  if (!check.allowed) {
    throw new EventRuleError(submitRefusalMessage(check.reason))
  }

  const at = nowIso()
  const updated: EventRecord = {
    ...existing,
    status: 'Submitted',
    updatedAt: at,
    history: [
      ...existing.history,
      { from: existing.status, to: 'Submitted', at, byId: actor.id, byName: actor.name },
    ],
  }
  all[index] = updated
  writeAll(all)
  return updated
}

/** Test helper — drops everything so each test starts from a known state. */
export function __resetStore(events: EventRecord[] = []): void {
  writeAll(events)
}
