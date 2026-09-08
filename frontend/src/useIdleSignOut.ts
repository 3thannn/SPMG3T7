import { useEffect, useRef } from 'react'

/**
 * Sign the user out after a stretch with no activity — the browser half of the
 * inactivity rule in US1.1.
 *
 * The server expires the session on its own schedule and is the one that
 * counts; this exists so an unattended screen does not sit there looking signed
 * in, and so the user is told why rather than meeting a refusal on their next
 * click. Both ends use the same window, which the server sends on the session.
 */

/** What counts as being at the keyboard. Deliberately not mousemove, which a
 *  nudged desk can fire forever without anyone being there. */
const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const

export function useIdleSignOut(minutes: number | null, onIdle: () => void): void {
  const latestOnIdle = useRef(onIdle)

  useEffect(() => {
    latestOnIdle.current = onIdle
  }, [onIdle])

  useEffect(() => {
    if (minutes === null || minutes <= 0) return

    const limit = minutes * 60 * 1000
    let timer = 0

    function restart() {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => latestOnIdle.current(), limit)
    }

    function onVisibilityChange() {
      // Coming back to a backgrounded tab is activity; leaving it is not, and
      // the timer keeps running while it is hidden.
      if (document.visibilityState === 'visible') restart()
    }

    restart()
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, restart, { passive: true })
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      window.clearTimeout(timer)
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, restart)
      }
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [minutes])
}
