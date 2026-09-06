import { useCallback, useEffect, useSyncExternalStore } from 'react'

/**
 * A hash router in about forty lines.
 *
 * Sprint 1 needs five routes and no data loaders, so this avoids adding a
 * routing dependency. Hash routing also means the Vite preview and any static
 * host serve deep links without rewrite rules. Swap in react-router if nested
 * layouts or route-level data loading arrive later.
 */

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

function currentPath(): string {
  const hash = window.location.hash.replace(/^#/, '')
  return hash === '' ? '/' : hash
}

export function navigate(path: string): void {
  if (currentPath() === path) return
  window.location.hash = path
}

export function useRoute(): string {
  return useSyncExternalStore(subscribe, currentPath, () => '/')
}

/** Scrolls to the top whenever the route changes, as a page navigation would. */
export function useScrollToTopOnRouteChange(route: string): void {
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [route])
}

/**
 * Matches `/events/:id` and returns the id, or null. Kept deliberately narrow —
 * it is the only parameterised route in Sprint 1.
 */
export function matchEventDetail(route: string): string | null {
  const match = /^\/events\/([^/]+)$/.exec(route)
  if (!match) return null
  const id = match[1]
  return id === 'new' ? null : id
}

/** An anchor that routes without a full page load. */
export function useNavigateTo(path: string): (event: { preventDefault(): void }) => void {
  return useCallback(
    (event: { preventDefault(): void }) => {
      event.preventDefault()
      navigate(path)
    },
    [path],
  )
}
