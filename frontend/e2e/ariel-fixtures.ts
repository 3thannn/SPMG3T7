import { test as base, expect as baseExpect, type APIRequestContext, type Page } from '@playwright/test'
import type { Session } from '../src/api'
import type { EventRecord } from '../src/eventsStore'

export const api = process.env.E2E_API_URL || 'http://localhost:8000'
export const expect = baseExpect.configure({ timeout: 15_000 })
const accounts = {
  organiser: 'organiser', coordinator: 'coordinator', lead: 'coordinatorlead',
  venue: 'venuestaff', tech: 'technicalsupport', safety: 'safetyofficer',
} as const
export type Actor = keyof typeof accounts

export class World {
  readonly prefix = `Ariel-E2E-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  sessions = new Map<Actor, Session>()
  events: string[] = []
  venues: string[] = []
  equipment: string[] = []
  constructor(readonly request: APIRequestContext) {}
  async session(actor: Actor) {
    if (!this.sessions.has(actor)) {
      const response = await this.request.post(api + '/auth/login', { data: {
        email: `${accounts[actor]}@spmg3t7.edu`, password: process.env.E2E_PASSWORD || 'Sprint1!demo',
      } })
      expect(response.ok(), `Sign in ${actor}: ${await response.text()}`).toBeTruthy()
      this.sessions.set(actor, await response.json() as Session)
    }
    return this.sessions.get(actor)!
  }
  async response(actor: Actor, method: string, path: string, data?: unknown) {
    const session = await this.session(actor)
    return this.request.fetch(api + path, { method, data, headers: { Authorization: `Bearer ${session.token}` } })
  }
  async call<T = EventRecord>(actor: Actor, method: string, path: string, data?: unknown): Promise<T> {
    const response = await this.response(actor, method, path, data)
    expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBeTruthy()
    return response.status() === 204 ? undefined as T : response.json()
  }
  async open(page: Page, actor: Actor, path: string) {
    // Use the real sign-in form, as in helpers.ts. Separate role documents avoid stale session restoration.
    await page.goto('/#/signin')
    await page.evaluate(() => localStorage.removeItem('spmg3t7.session.v1'))
    await page.reload()
    await page.getByLabel('Email').fill(`${accounts[actor]}@spmg3t7.edu`)
    await page.getByLabel('Password').fill(process.env.E2E_PASSWORD || 'Sprint1!demo')
    await page.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.locator('.topnav-role')).toHaveText((await this.session(actor)).role)
    await page.goto('/#' + path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  }
  draft(suffix = 'event') {
    const day = new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10)
    return { title: `${this.prefix} ${suffix}`, purpose: 'Playwright regression', description: 'Test-owned record',
      startsAt: `${day}T10:00`, endsAt: `${day}T12:00`, expectedAttendance: 40,
      venueRequirements: 'None / Not required', preferredLayout: 'None / Not required',
      accessibilityNeeds: 'None / Not required', equipmentNeeds: 'None / Not required', registrationNeeds: 'None / Not required' }
  }
  async event(stage: 'Draft' | 'Submitted' | 'Under Review' | 'Approved' | 'Planning' = 'Planning', suffix = 'event') {
    let event = await this.call('organiser', 'POST', '/events', this.draft(suffix))
    this.events.push(event.id)
    if (stage === 'Draft') return event
    event = await this.call('organiser', 'POST', `/events/${event.id}/submit`)
    if (stage === 'Submitted') return event
    event = await this.call('lead', 'POST', `/events/${event.id}/assign`, { coordinatorId: (await this.session('coordinator')).id })
    if (stage === 'Under Review') return event
    event = await this.call('coordinator', 'POST', `/events/${event.id}/approve`)
    if (stage === 'Approved') return event
    const venue = await this.venue()
    await this.call('coordinator', 'POST', `/events/${event.id}/bookings`, { venueId: venue.id, startsAt: event.startsAt, endsAt: event.endsAt })
    return this.call('coordinator', 'GET', `/events/${event.id}`)
  }
  async venue() {
    const venue = await this.call<{ id: string }>('venue', 'POST', '/venues', {
      name: `${this.prefix} venue ${this.venues.length}`, location: 'E2E store', capacity: 40,
      facilities: '', accessibilityFeatures: '', supportedLayouts: '', operatingHours: '', setupMinutes: 0, turnaroundMinutes: 0,
    })
    this.venues.push(venue.id)
    return venue
  }
  async item() {
    const item = await this.call<{ id: string; name: string }>('tech', 'POST', '/equipment', {
      name: `${this.prefix} projector`, type: `${this.prefix} Projector`, location: 'E2E store',
      description: 'Test-owned stock', totalQuantity: 10, outOfServiceQuantity: 2, outOfServiceReason: 'Maintenance',
    })
    this.equipment.push(item.id)
    return item
  }
  async cleanup() {
    const failures: string[] = []
    for (const id of this.events) {
      try {
        const event = await this.call('organiser', 'GET', `/events/${id}`)
        // Completed events are immutable; their test-owned venue and booking stay as history.
        if (!['Completed', 'Cancelled', 'Rejected'].includes(event.status))
          await this.call('organiser', 'POST', `/events/${id}/cancel`, { reason: `${this.prefix} teardown` })
      } catch (error) { failures.push(String(error)) }
    }
    // History may retain foreign keys. Delete only exact IDs created by this test; document retained records.
    for (const [actor, path, ids] of [['venue', 'venues', this.venues], ['tech', 'equipment', this.equipment]] as const) {
      for (const id of ids) {
        const response = await this.response(actor, 'DELETE', `/${path}/${id}`)
        if (response.status() === 409) console.log(`Retained test history: ${path}/${id} (${this.prefix})`)
        else if (!response.ok()) failures.push(`${path}/${id}: ${await response.text()}`)
      }
    }
    expect(failures, 'Test-owned data cleanup failed').toEqual([])
  }
}

export const test = base.extend<{ world: World }>({
  world: async ({ request }, provide, testInfo) => {
    const world = new World(request)
    try { await provide(world) } finally {
      await testInfo.attach('test-owned-records', { body: JSON.stringify({ prefix: world.prefix,
        events: world.events, venues: world.venues, equipment: world.equipment }, null, 2), contentType: 'application/json' })
      await world.cleanup()
    }
  },
})
