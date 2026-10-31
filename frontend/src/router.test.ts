/** The hash router: which routes match, and how links move between them. */

import { act, renderHook } from '@testing-library/react'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import {
  matchEventDetail,
  matchVenueDetail,
  matchVenueEdit,
  navigate,
  useNavigateTo,
  useRoute,
} from './router'

afterEach(() => {
  window.location.hash = ''
})

describe('matching a route', () => {
  it.each([
    ['/events/7', '7'],
    ['/events/new', null],
    ['/events', null],
    ['/events/7/edit', null],
  ])('event detail: %s', (route, id) => {
    expect(matchEventDetail(route)).toBe(id)
  })

  it.each([
    ['/venues/3', '3'],
    ['/venues/new', null],
    ['/venues', null],
  ])('venue detail: %s', (route, id) => {
    expect(matchVenueDetail(route)).toBe(id)
  })

  it.each([
    ['/venues/3/edit', '3'],
    ['/venues/3', null],
  ])('venue edit: %s', (route, id) => {
    expect(matchVenueEdit(route)).toBe(id)
  })
})

describe('moving between routes', () => {
  it('reads the route from the hash, with no hash meaning the landing page', () => {
    const { result } = renderHook(() => useRoute())
    expect(result.current).toBe('/')

    act(() => {
      navigate('/venues')
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })

    expect(result.current).toBe('/venues')
  })

  it('does not touch the hash when already on the route', () => {
    navigate('/venues')
    const before = window.location.href

    navigate('/venues')

    expect(window.location.href).toBe(before)
  })

  it('a link routes in place of loading the page', () => {
    const { result } = renderHook(() => useNavigateTo('/events'))
    let prevented = false

    result.current({ preventDefault: () => (prevented = true) })

    expect(prevented).toBe(true)
    expect(window.location.hash).toBe('#/events')
  })

  it('rendered on a server, with no location to read, it is the landing page', () => {
    function Route() {
      return createElement('span', null, useRoute())
    }

    expect(renderToString(createElement(Route))).toBe('<span>/</span>')
  })
})
