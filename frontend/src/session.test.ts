import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearStoredSession, loadStoredSession, storeSession } from './session'
import { buildSession } from './test/sessions'

const STORAGE_KEY = 'spmg3t7.session.v1'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('storeSession', () => {
  it('round-trips a session', () => {
    const session = buildSession({ role: 'Coordinator' })

    storeSession(session)

    expect(loadStoredSession()).toEqual(session)
  })

  it('replaces the previous session rather than adding to it', () => {
    storeSession(buildSession({ id: 'user_1' }))
    storeSession(buildSession({ id: 'user_2' }))

    expect(loadStoredSession()?.id).toBe('user_2')
  })

  it('does not throw when storage refuses the write', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError')
    })

    expect(() => storeSession(buildSession())).not.toThrow()
  })
})

describe('loadStoredSession', () => {
  it('returns null when nothing is stored', () => {
    expect(loadStoredSession()).toBeNull()
  })

  it('returns null for a record that is not valid JSON', () => {
    localStorage.setItem(STORAGE_KEY, '{ not json')

    expect(loadStoredSession()).toBeNull()
  })

  it('returns null for a record with no token', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'user_1', role: 'Organiser' }))

    expect(loadStoredSession()).toBeNull()
  })

  it('returns null for a record with no role or permissions', () => {
    // A half-written record must not become a session with unknown rights.
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: 't', id: 'user_1' }))

    expect(loadStoredSession()).toBeNull()
  })

  it('reads as signed out when storage itself is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('SecurityError')
    })

    expect(loadStoredSession()).toBeNull()
  })
})

describe('clearStoredSession', () => {
  it('removes the stored session', () => {
    storeSession(buildSession())

    clearStoredSession()

    expect(loadStoredSession()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('does not throw when there is nothing to clear', () => {
    expect(() => clearStoredSession()).not.toThrow()
  })
})
