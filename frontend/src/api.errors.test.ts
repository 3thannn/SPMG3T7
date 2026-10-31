/** How an API failure becomes an error the page can act on, for the shapes api.test.ts skips. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, AuthError, authorizedFetch } from './api'
import { failure, stubFetch } from './test/fetch'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('reading an error answer', () => {
  it('takes a plain-string detail as the message', async () => {
    stubFetch({ ok: false, status: 400, json: async () => ({ detail: 'Bad request body.' }) })

    await expect(authorizedFetch('/events', 'token')).rejects.toMatchObject({
      message: 'Bad request body.',
      status: 400,
    })
  })

  it('reads a 401 with no code as not signed in', async () => {
    stubFetch({ ok: false, status: 401, json: async () => ({}) })

    await expect(authorizedFetch('/events', 'token')).rejects.toMatchObject({
      code: 'not_authenticated',
      message: 'Request failed with status 401.',
    })
  })

  it('turns a refused sign-in into an AuthError', async () => {
    stubFetch(failure(401, 'Wrong email or password.', 'invalid_credentials'))

    const refused = authorizedFetch('/auth/me', 'token')

    await expect(refused).rejects.toBeInstanceOf(AuthError)
    await expect(refused).rejects.toBeInstanceOf(ApiError)
  })
})
