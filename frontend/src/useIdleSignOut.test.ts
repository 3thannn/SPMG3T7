/** US1.1: the browser signs out after the server's idle window, counting only activity. */

import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useIdleSignOut } from './useIdleSignOut'

const MINUTE = 60_000

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})

describe('useIdleSignOut', () => {
  it('signs out once the window passes with nothing done', () => {
    const onIdle = vi.fn()
    renderHook(() => useIdleSignOut(1, onIdle))

    vi.advanceTimersByTime(MINUTE)

    expect(onIdle).toHaveBeenCalledTimes(1)
  })

  it('coming back to the tab counts as activity and restarts the window', () => {
    const onIdle = vi.fn()
    renderHook(() => useIdleSignOut(1, onIdle))

    vi.advanceTimersByTime(MINUTE - 1000)
    setVisibility('visible')
    vi.advanceTimersByTime(MINUTE - 1000)

    expect(onIdle).not.toHaveBeenCalled()
  })

  it('leaving the tab does not, so the window keeps running while it is hidden', () => {
    const onIdle = vi.fn()
    renderHook(() => useIdleSignOut(1, onIdle))

    vi.advanceTimersByTime(MINUTE - 1000)
    setVisibility('hidden')
    vi.advanceTimersByTime(1000)

    expect(onIdle).toHaveBeenCalledTimes(1)
  })

  it('does nothing without a window from the server', () => {
    const onIdle = vi.fn()
    renderHook(() => useIdleSignOut(null, onIdle))

    vi.advanceTimersByTime(60 * MINUTE)

    expect(onIdle).not.toHaveBeenCalled()
  })
})
