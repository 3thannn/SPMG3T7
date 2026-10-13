import { Page, expect } from '@playwright/test'

/**
 * Helper functions for E2E tests
 */

export type Role =
  | 'Event Organiser'
  | 'Event Coordinator'
  | 'Event Coordinator Lead'
  | 'Safety Officer'
  | 'Venue Staff'

/**
 * Test user credentials for different roles
 * These match the actual users in your Supabase public.users table
 */
export const TEST_USERS = {
  'Event Organiser': {
    email: 'organiser@spmg3t7.edu',
    password: 'Sprint1!demo',
    name: 'Lincoln',
  },
  'Event Coordinator': {
    email: 'coordinator@spmg3t7.edu',
    password: 'Sprint1!demo',
    name: 'Ethan',
  },
  'Event Coordinator Lead': {
    email: 'coordinatorlead@spmg3t7.edu',
    password: 'Sprint1!demo',
    name: 'Jordan',
  },
  'Safety Officer': {
    email: 'safetyofficer@spmg3t7.edu',
    password: 'Sprint1!demo',
    name: 'Alex',
  },
  'Venue Staff': {
    email: 'venuestaff@spmg3t7.edu',
    password: 'Sprint1!demo',
    name: 'Sam',
  },
} as const

/**
 * Sign in as a specific role
 */
export async function signIn(page: Page, role: Role) {
  const user = TEST_USERS[role]

  await page.goto('/#/signin')

  // Wait for the sign-in page to load
  await page.waitForLoadState('networkidle')

  // Fill in credentials
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)

  // Click sign in button (the one in the form, not the header)
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()

  // Wait for navigation to complete and verify signed in
  // The name appears in the TopNav component with class "topnav-name"
  await expect(page.locator('.topnav-name')).toHaveText(user.name, { timeout: 10000 })
}

/**
 * Sign out the current user
 * Note: Manual sign-out redirects to landing page (/), not sign-in page
 */
export async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()

  // Wait for navigation to complete and verify we're signed out
  // The "Sign in" button in the header should appear when signed out
  await expect(page.getByRole('banner').getByRole('button', { name: 'Sign in' })).toBeVisible({ timeout: 10000 })

  // Should not see user identity anymore
  await expect(page.locator('.topnav-identity')).not.toBeVisible()
}

/**
 * Wait for the backend to be ready
 * This is no longer needed - tests will navigate directly to pages
 */
export async function waitForBackend(_page: Page) {
  // No-op: tests navigate directly to the pages they need
}
