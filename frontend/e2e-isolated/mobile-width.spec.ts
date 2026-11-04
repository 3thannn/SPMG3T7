import { test, expect, type Page } from '@playwright/test'
import { ACCOUNT, as, reset, type Role } from './support'

/**
 * G14: the Week 1 brief asks for a mobile-friendly app. At a phone's width
 * (390 x 844, an iPhone 14) every role's home page, and the event and booking
 * pages the workflow lives on, must fit the screen: no sideways scrolling of
 * the whole page. The link rail and wide tables may scroll inside their own box.
 */

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

test.beforeEach(async ({ request }) => {
  await reset(request)
})

async function fitsTheScreen(page: Page) {
  await page.waitForLoadState('networkidle')
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  // On a failure, name what sticks out, so the fix is obvious.
  const culprits =
    overflow > 1
      ? await page.evaluate(() =>
          [...document.querySelectorAll('body *')]
            .filter(
              (element) =>
                element.getBoundingClientRect().right >
                document.documentElement.clientWidth + 1,
            )
            .slice(0, 6)
            .map((element) => `${element.tagName}.${element.className}`),
        )
      : []
  expect(overflow, `page is ${overflow}px too wide: ${culprits.join(', ')}`).toBeLessThanOrEqual(1)
}

const PAGES: [Role, string][] = [
  ...(Object.entries(ACCOUNT) as [Role, (typeof ACCOUNT)[Role]][]).map(
    ([role, account]) => [role, account.home] as [Role, string],
  ),
  ['Event Coordinator', '/events/1'],
  ['Event Organiser', '/events/new'],
  ['Venue Staff', '/booking-requests'],
  ['Venue Staff', '/venues/1'],
  ['Event Coordinator', '/notifications'],
]

for (const [role, route] of PAGES) {
  test(`G14: ${role} ${route} fits a phone screen`, async ({ page }) => {
    await as(page, role, route)
    await fitsTheScreen(page)
  })
}
