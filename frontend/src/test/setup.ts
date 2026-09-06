import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no layout, so scrollTo is unimplemented and logs a noisy "Not
// implemented" error on every route change. The app only uses it to reset
// scroll position, which has no bearing on any assertion.
//
// Defined rather than stubbed: tests that call vi.unstubAllGlobals() would
// otherwise restore jsdom's throwing version halfway through the run.
Object.defineProperty(window, 'scrollTo', {
  value: vi.fn(),
  writable: true,
  configurable: true,
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})
