/**
 * The preferred layout choices — Week 9 (G7/A7).
 *
 * Venue Staff add, edit and delete layouts through the catalogue, so the
 * Organiser's choices come from it. The rule is the server's
 * (backend/tests/test_event_needs.py); this checks the form offers what the
 * server lists, and keeps working when it cannot load the list.
 */

import { render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import EventNeedsFields from './EventNeedsFields'
import { NO_NEEDS } from '../eventNeeds'
import { listLayoutOptions } from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  listLayoutOptions: vi.fn(),
}))

const listLayoutsMock = vi.mocked(listLayoutOptions)
const organiser = buildSession({ role: 'Event Organiser' })

afterEach(() => {
  vi.resetAllMocks()
})

function layoutSelect() {
  return screen.getByLabelText('Preferred layout')
}

it('TC-NF01 offers a layout Venue Staff added to a venue', async () => {
  listLayoutsMock.mockResolvedValue(['Theatre', 'Ballroom'])
  render(<EventNeedsFields needs={NO_NEEDS} onChange={() => {}} session={organiser} />)

  expect(await within(layoutSelect()).findByRole('option', { name: 'Ballroom' })).toBeInTheDocument()
  expect(listLayoutsMock).toHaveBeenCalledWith(organiser)
})

it('TC-NF02 keeps the standard list when the catalogue cannot be read', async () => {
  listLayoutsMock.mockRejectedValue(new Error('offline'))
  render(<EventNeedsFields needs={NO_NEEDS} onChange={() => {}} session={organiser} />)

  expect(within(layoutSelect()).getByRole('option', { name: 'Theatre' })).toBeInTheDocument()
  expect(within(layoutSelect()).queryByRole('option', { name: 'Ballroom' })).toBeNull()
})

it('TC-NF03 still shows a saved layout the catalogue no longer lists', () => {
  render(
    <EventNeedsFields needs={{ ...NO_NEEDS, preferredLayout: 'Ballroom' }} onChange={() => {}} />,
  )
  expect(within(layoutSelect()).getByRole('option', { name: 'Ballroom' })).toBeInTheDocument()
})
