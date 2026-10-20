import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import StatusBadge from './StatusBadge'
import { EVENT_STATUSES } from '../status'

it('renders every status with its own modifier class', () => {
  const classes = EVENT_STATUSES.map((status) => {
    const { container, unmount } = render(<StatusBadge status={status} />)
    const badge = container.firstElementChild as HTMLElement
    const modifier = [...badge.classList].find(
      (name) => name.startsWith('status-badge-') && !['status-badge-sm', 'status-badge-lg'].includes(name),
    )
    unmount()
    return modifier
  })
  expect(new Set(classes).size).toBe(EVENT_STATUSES.length)
})

it('renders US4.4 Pending Safety Check as its own badge', () => {
  const { container } = render(<StatusBadge status="Pending Safety Check" size="lg" />)
  expect(screen.getByText('Pending Safety Check')).toBeInTheDocument()
  expect(container.firstElementChild).toHaveClass('status-badge-safety', 'status-badge-lg')
})
