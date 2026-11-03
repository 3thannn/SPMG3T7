import { test, expect } from '@playwright/test'
import { signIn, signOut } from './helpers'

/**
 * E2E tests for Authentication flows (US1.1, US1.2, US1.3)
 *
 * These tests cover:
 * - US1.1: Sign in and session management
 * - US1.2: Sign out
 * - US1.3: Role-based access control
 */

test.describe('Authentication', () => {

  test('US1.3: Each role is routed to their correct home page', async ({ page }) => {
    // Test Organiser
    await signIn(page, 'Event Organiser')
    await expect(page).toHaveURL(/#\/events/)
    await signOut(page)

    // Test Coordinator
    await signIn(page, 'Event Coordinator')
    await expect(page).toHaveURL(/#\/events/)
    await signOut(page)

    // Test Coordinator Lead
    await signIn(page, 'Event Coordinator Lead')
    await expect(page).toHaveURL(/#\/unassigned-queue/)
    await signOut(page)

    // Test Safety Officer
    await signIn(page, 'Safety Officer')
    await expect(page).toHaveURL(/#\/safety-review/)
    await signOut(page)

    // Test Venue Staff
    await signIn(page, 'Venue Staff')
    await expect(page).toHaveURL(/#\/venues/)
  })
})
