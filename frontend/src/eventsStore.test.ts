import { beforeEach, describe, expect, it } from 'vitest'
import {
  EventRuleError,
  __resetStore,
  createEvent,
  getEvent,
  listEvents,
  saveEvent,
  submitEvent,
} from './eventsStore'

const organiser = { id: 'user_1', name: 'Dylan' }
const otherOrganiser = { id: 'user_2', name: 'Ariel' }
const coordinator = { id: 'user_9', name: 'Ethan' }

const draft = {
  title: 'Orientation Briefing',
  description: 'Welcome session.',
  startsAt: '2026-10-01T09:00',
  location: 'Lecture Theatre 2',
}

beforeEach(() => {
  __resetStore([])
})

describe('createEvent', () => {
  it('starts every new event as a Draft', async () => {
    const created = await createEvent(draft, organiser)

    expect(created.status).toBe('Draft')
  })

  it('records creation in the audit trail with who and when', async () => {
    const created = await createEvent(draft, organiser)

    expect(created.history).toHaveLength(1)
    expect(created.history[0]).toMatchObject({
      from: null,
      to: 'Draft',
      byId: 'user_1',
      byName: 'Dylan',
    })
    expect(Date.parse(created.history[0].at)).not.toBeNaN()
  })
})

describe('US4.2 — Draft stays Draft on save', () => {
  it('leaves the status untouched when content is edited', async () => {
    const created = await createEvent(draft, organiser)

    const saved = await saveEvent(created.id, { ...draft, title: 'Renamed' }, organiser)

    expect(saved.title).toBe('Renamed')
    expect(saved.status).toBe('Draft')
  })

  it('writes no history entry, because a save is not a status change', async () => {
    const created = await createEvent(draft, organiser)

    const saved = await saveEvent(created.id, { ...draft, title: 'Renamed' }, organiser)

    expect(saved.history).toHaveLength(created.history.length)
  })

  it('refuses an edit from someone who does not own the event', async () => {
    const created = await createEvent(draft, organiser)

    await expect(saveEvent(created.id, draft, otherOrganiser)).rejects.toBeInstanceOf(
      EventRuleError,
    )
  })
})

describe('US4.2 — submit moves Draft to Submitted exactly once', () => {
  it('moves a Draft to Submitted', async () => {
    const created = await createEvent(draft, organiser)

    const submitted = await submitEvent(created.id, organiser)

    expect(submitted.status).toBe('Submitted')
  })

  it('appends a timestamped, attributable history entry', async () => {
    const created = await createEvent(draft, organiser)

    const submitted = await submitEvent(created.id, organiser)
    const latest = submitted.history[submitted.history.length - 1]

    expect(latest).toMatchObject({
      from: 'Draft',
      to: 'Submitted',
      byId: 'user_1',
      byName: 'Dylan',
    })
    expect(Date.parse(latest.at)).not.toBeNaN()
  })

  it('rejects a second submit and leaves the event unchanged', async () => {
    const created = await createEvent(draft, organiser)
    await submitEvent(created.id, organiser)

    await expect(submitEvent(created.id, organiser)).rejects.toBeInstanceOf(EventRuleError)

    const after = await getEvent(created.id)
    expect(after?.status).toBe('Submitted')
    expect(after?.history).toHaveLength(2)
  })

  it('refuses a submit from someone who does not own the event', async () => {
    const created = await createEvent(draft, organiser)

    await expect(submitEvent(created.id, otherOrganiser)).rejects.toBeInstanceOf(EventRuleError)
  })
})

describe('US4.1 — what the list returns per role', () => {
  it('gives an Organiser only the events they own', async () => {
    await createEvent(draft, organiser)
    await createEvent({ ...draft, title: 'Someone else’s' }, otherOrganiser)

    const mine = await listEvents(organiser, false)

    expect(mine).toHaveLength(1)
    expect(mine[0].organiserId).toBe('user_1')
  })

  it('gives a Coordinator every event', async () => {
    await createEvent(draft, organiser)
    await createEvent({ ...draft, title: 'Someone else’s' }, otherOrganiser)

    const all = await listEvents(coordinator, true)

    expect(all).toHaveLength(2)
  })
})
