/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**', '**/e2e-isolated/**'],
    // The page tests type into forms key by key, which on a slow runner can
    // pass the 5s default without anything being wrong.
    testTimeout: 15000,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      // main.tsx only mounts <App /> into the page; src/test holds test helpers.
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/main.tsx'],
      // `npm test -- --coverage` fails below these. Branches are the one gap
      // left (README, "Test coverage"); raise the number as they are covered.
      // The suite is the tests traced to acceptance criteria, so the floor is
      // what it reaches; loading and error states are mostly left to the E2E
      // journeys. See docs/testing (workbook Summary). Raise when tests are added.
      thresholds: { lines: 52, statements: 51, functions: 49, branches: 48 },
    },
  },
})
