import { test, expect } from '@playwright/test'
import { ACCOUNT, PASSWORD, reset, signInAs, signOut, type Role } from './support'

/**
 * US1.1-US1.4 in the browser: every role signs in to its own view, a wrong
 * password is refused, signing out locks the pages again, and a page outside
 * the role is refused rather than shown.
 */

test.beforeEach(async ({ request }) => {
  await reset(request)
})

const ROLES = Object.keys(ACCOUNT) as Role[]

test('US1.1/US1.4: each of the seven roles lands on its own view', async ({ page }) => {
  for (const role of ROLES) {
    await signInAs(page, role)
    await expect(page).toHaveURL(new RegExp(`#${ACCOUNT[role].home}$`))
    await expect(page.locator('.topnav-name')).toHaveText(ACCOUNT[role].name)
    await signOut(page)
  }
})

test('US1.1: a wrong password is refused and nobody is signed in', async ({ page }) => {
  await page.goto('/#/signin')
  await page.getByLabel('Email').fill(ACCOUNT['Event Organiser'].email)
  await page.getByLabel('Password').fill(`${PASSWORD}-wrong`)
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('.topnav-role')).toHaveCount(0)
})

test('US1.2: after signing out, a protected page asks for sign-in again', async ({ page }) => {
  await signInAs(page, 'Event Organiser')
  await signOut(page)

  await page.goto('/#/events')

  await expect(page.locator('form').getByRole('button', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Events', level: 1 })).toHaveCount(0)
})

test('US1.3: an Organiser opening the venue catalogue is refused, not shown it', async ({
  page,
}) => {
  await signInAs(page, 'Event Organiser')

  await page.goto('/#/venues')

  await expect(page.getByRole('heading', { name: 'This page is not open to your role' })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveText(
    'The Event Organiser role cannot open the venue catalogue. That is available to ' +
      'Event Coordinators and Venue Staff.',
  )
  await expect(page.getByText('Great Hall', { exact: true })).toHaveCount(0)
})
