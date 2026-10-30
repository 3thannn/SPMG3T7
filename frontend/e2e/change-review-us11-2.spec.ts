import { test, expect, type Page } from '@playwright/test'

// Browser-level workflow with an isolated API fixture. Real API rules and
// database transactions are covered by backend tests, without live user data.
test('clarification, amended proposal, acceptance and arrangement review', async ({ page, context }) => {
  let role = 'Event Coordinator'
  const ownerPermissions = ['events:read:own', 'events:submit', 'notifications:read']
  const coordPermissions = ['events:read:submitted', 'events:edit', 'events:review', 'notifications:read']
  const identity = () => ({ id: role === 'Event Organiser' ? '1' : '2', name: role,
    role, email: 'test@example.edu', permissions: role === 'Event Organiser' ? ownerPermissions : coordPermissions })
  let event = {
    id: '101', title: 'Review test', purpose: 'Welcome', description: 'An event',
    startsAt: '2027-11-02T18:00', endsAt: '2027-11-02T21:00', expectedAttendance: 40,
    status: 'Planning', organiserId: '1', organiserName: 'Organiser', coordinatorId: '2',
    coordinatorName: 'Coordinator', createdAt: '2026-10-01T00:00', updatedAt: '2026-10-30T00:00',
    venueRequirements: 'None / Not required', preferredLayout: 'None / Not required',
    accessibilityNeeds: 'None / Not required', equipmentNeeds: 'None / Not required',
    registrationNeeds: 'None / Not required', history: [], reviewRevision: 1,
    awaitingReply: false, changeRequested: true,
    pendingChanges: [{ field: 'expected_attendance', label: 'Expected attendance', oldValue: '40', newValue: '50', important: true }],
    arrangementReview: [] as { kind: string; id: string; label: string; reason: string; error: boolean }[],
  }
  const notices: { id: string; message: string }[] = []
  await context.route('http://localhost:8000/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: {
      'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' } })
    let body: unknown = []
    if (path === '/auth/me') body = identity()
    else if (path === '/notifications') body = notices
    else if (path === '/events/101/clarification') {
      event = { ...event, awaitingReply: true, reviewRevision: event.reviewRevision + 1 }
      notices.push({ id: '1', message: 'Please reduce attendance' })
      body = event
    } else if (path === '/events/101/change-request') {
      const proposal = request.postDataJSON()
      expect(proposal.reviewRevision).toBe(2)
      event = { ...event, awaitingReply: false, reviewRevision: 3,
        pendingChanges: [{ ...event.pendingChanges[0], newValue: String(proposal.expectedAttendance) }] }
      body = event
    } else if (path === '/events/101/change-request/approve') {
      expect(new URL(request.url()).searchParams.get('review_revision')).toBe('3')
      event = { ...event, expectedAttendance: 41, changeRequested: false, pendingChanges: [],
        reviewRevision: 4, arrangementReview: [{ kind: 'venue', id: '1', label: 'Hall booking',
          reason: 'Capacity is 40; expected attendance is 41.', error: false }] }
      notices.push({ id: '2', message: 'Change request accepted' })
      body = event
    } else if (path === '/events/101') body = event
    else if (path === '/events') body = [event]
    else if (path.endsWith('/registration')) body = { enabled: false, capacity: 40, registeredCount: 0 }
    return route.fulfill({ json: body, headers: { 'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' } })
  })

  async function openAs(previous: Page, nextRole: string): Promise<Page> {
    // Start each role in a fresh document before React restores a session.
    // This avoids a previous document's async restoration overwriting storage.
    await previous.close()
    role = nextRole
    const next = await context.newPage()
    await next.addInitScript(session => localStorage.setItem('spmg3t7.session.v1', JSON.stringify(session)),
      { ...identity(), token: 'fixture-token' })
    await next.goto('/')
    await expect(next.locator('.topnav-role')).toHaveText(nextRole)
    await next.evaluate(() => { window.location.hash = '#/events/101' })
    await expect(next.getByRole('heading', { name: 'Review test', exact: true, level: 1 })).toBeVisible()
    return next
  }
  page = await openAs(page, 'Event Coordinator')
  await page.getByLabel('What do you need from them?').fill('Please reduce attendance')
  await page.getByRole('button', { name: 'Send request', exact: true }).click()
  page = await openAs(page, 'Event Organiser')
  await page.getByRole('button', { name: 'Request changes', exact: true }).click()
  await expect(page.getByLabel('Expected attendance', { exact: true })).toHaveValue('50')
  await page.getByLabel('Expected attendance', { exact: true }).fill('41')
  await page.getByRole('button', { name: 'Submit change request', exact: true }).click()
  await expect(page.getByText(/Change request sent/)).toBeVisible()
  page = await openAs(page, 'Event Coordinator')
  await page.getByRole('button', { name: 'Approve changes', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Arrangement review' })).toContainText('Conflict')
  expect(event.status).toBe('Planning')
  expect(notices.map(n => n.message)).toEqual(['Please reduce attendance', 'Change request accepted'])
})
