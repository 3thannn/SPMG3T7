import { defineConfig, devices } from '@playwright/test'

/**
 * The browser journeys (one or more per role), run against an API with no
 * database behind it, so they can never change the team's real records.
 *
 * The specs in `e2e-isolated/` start their own pair: `backend/e2e_server.py`
 * (the real API over in-memory stores, reset before each test) on 8001, and a
 * dev server on 5174 pointed at it. Neither reuses a running server.
 *
 *   npm run test:e2e
 */
const API_PORT = 8001
const WEB_PORT = 5174
const python = process.platform === 'win32' ? '.venv\\Scripts\\python' : '.venv/bin/python'

export default defineConfig({
  testDir: './e2e-isolated',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1280, height: 720 },
    // Optional: a Chromium already on the machine (e.g. a cloud container)
    // when it does not match the Playwright version installed here.
    launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH || undefined },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${python} -m uvicorn e2e_server:app --port ${API_PORT}`,
      cwd: '../backend',
      env: { CORS_ORIGINS: `http://localhost:${WEB_PORT}` },
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60 * 1000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60 * 1000,
    },
  ],
})
