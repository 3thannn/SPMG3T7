import { test as base, expect as baseExpect, type APIRequestContext, type Page } from '@playwright/test'
import { execFile } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { promisify } from 'node:util'
import type { Session } from '../src/api'
import type { EventRecord } from '../src/eventsStore'

export const api = process.env.E2E_API_URL || 'http://localhost:8000'
export const expect = baseExpect.configure({ timeout: 15_000 })
const runFile = promisify(execFile)
const root = resolve(import.meta.dirname, '../..')
const python = process.env.E2E_PYTHON || resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
async function cleanupData(prefix: string, apply = false) {
  const { stdout } = await runFile(python, [resolve(import.meta.dirname, 'cleanup-data.py'), '--prefix', prefix, '--verify-api', api, apply ? '--apply' : '--check'], { cwd: root, timeout: 120_000 })
  console.log(stdout.trim())
}
const accounts = {
  organiser: 'organiser', coordinator: 'coordinator', lead: 'coordinatorlead',
  venue: 'venuestaff', tech: 'technicalsupport', safety: 'safetyofficer',
} as const
export type Actor = keyof typeof accounts

export class World {
  readonly prefix = `Ariel-E2E-${Date.now()}-${randomBytes(3).toString('hex')}`
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
    // Admin deletion is confined to the exact run prefix, including immutable test history.
    await cleanupData(this.prefix, true)
  }

}

export const test = base.extend<{ world: World }>({
  world: async ({ request, context }, provide, testInfo) => {
    if (process.env.E2E_ALLOW_SHARED_WRITES !== '1')
      throw new Error('Live tests write shared data. Set E2E_ALLOW_SHARED_WRITES=1 to opt in; teardown fully removes test records.')
    const world = new World(request)
    // Fail before writing if cleanup access is missing or a previous run left data.
    // Run this suite with one worker so active test data is not mistaken for leftovers.
    await cleanupData('Ariel-E2E-')
    // UI writes must also go to the API whose database was verified, even if
    // VITE_API_BASE_URL differs from E2E_API_URL. Abort before sending a request.
    await context.route('**/*', async route => {
      if (['fetch', 'xhr'].includes(route.request().resourceType())
        && !route.request().url().startsWith(api.replace(/\/$/, '') + '/')) {
        testInfo.annotations.push({ type: 'blocked-api', description: 'Browser API target differs from the verified E2E_API_URL; check VITE_API_BASE_URL.' })
        await route.abort('blockedbyclient')
        return
      }
      await route.continue()
    })
    const recovery = resolve(root, 'frontend/playwright/.cache/recovery', world.prefix + '.json')
    await mkdir(resolve(root, 'frontend/playwright/.cache/recovery'), { recursive: true })
    await writeFile(recovery, JSON.stringify({ prefix: world.prefix, api, state: 'running' }))
    try { await provide(world) } finally {
      const manifest = { prefix: world.prefix, api, events: world.events, venues: world.venues, equipment: world.equipment }
      await writeFile(recovery, JSON.stringify({ ...manifest, state: 'cleanup-required' }, null, 2))
      await testInfo.attach('test-owned-records', { body: JSON.stringify(manifest, null, 2), contentType: 'application/json' })
      await world.cleanup()
      await writeFile(recovery, JSON.stringify({ ...manifest, state: 'cleaned' }, null, 2))
    }
  },
})
