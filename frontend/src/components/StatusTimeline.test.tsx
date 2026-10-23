import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import StatusTimeline from './StatusTimeline'
import type { StatusChange } from '../status'

const status: StatusChange[] = [
  { from: null, to: 'Draft', at: '2026-10-13T09:00:00', byId: '1', byName: 'Dylan' },
  { from: 'Draft', to: 'Submitted', at: '2026-10-13T10:00:00', byId: '1', byName: 'Dylan' },
  { from: 'Approved', to: 'Planning', at: '2026-10-13T11:00:00', byId: '2', byName: 'Priya' },
]

it('shows event status transitions in order', () => {
  const { container } = render(<StatusTimeline history={status} />)
  const entries = [...container.querySelectorAll('ol.timeline > li')]
  expect(entries).toHaveLength(3)
  expect(entries[0]).toHaveTextContent('Created as')
  expect(entries[1]).toHaveTextContent('Submitted')
  expect(entries[2]).toHaveTextContent('Planning')
  expect(screen.queryByText(/equipment request/i)).not.toBeInTheDocument()
})

it('shows when each change was made, in Singapore time', () => {
  render(<StatusTimeline history={status} />)
  // changed_at is naive UTC, so 09:00 there is 17:00 in Singapore.
  expect(screen.getByText('13 Oct 2026, 17:00')).toBeInTheDocument()
  expect(screen.getByText('13 Oct 2026, 19:00')).toBeInTheDocument()
})
