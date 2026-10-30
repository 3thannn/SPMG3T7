import { test as base, expect } from '@playwright/test'
import type { Session } from '../src/api'

export const api = 'http://127.0.0.1:8000'
type World = { eventId: string; bookingId: string; startsAt: string; endsAt: string; session: Session }

export const test = base.extend<{ world: World; role: string }>({
  role: ['Event Coordinator', { option: true }],
  world: async ({ page, request, role }, provide) => {
    const reset = await request.post(api + '/__test__/reset')
    expect(reset.ok()).toBeTruthy()
    const seeded = await reset.json()
    const email = role === 'Event Organiser' ? 'organiser@spmg3t7.edu' : 'coordinator@spmg3t7.edu'
    const login = await request.post(api + '/auth/login', {
      data: { email, password: 'Sprint1!demo' },
    })
    expect(login.ok()).toBeTruthy()
    const session = await login.json()
    await page.goto('/#/signin')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill('Sprint1!demo')
    await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
    await expect(page.locator('.topnav-name')).toHaveText(session.name)
    await page.goto('/#/events/' + seeded.eventId)
    await expect(page.getByRole('heading', { name: 'Venue bookings', exact: true })).toBeVisible()
    await expect(page.locator('.booking-row')).toHaveCount(2)
    await provide({ ...seeded, session })
  },
})

export { expect }
