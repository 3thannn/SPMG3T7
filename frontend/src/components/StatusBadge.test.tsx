import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatusBadge from './StatusBadge'
import { EVENT_STATUSES, SAFETY_APPROVED_STAGE } from '../status'

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

describe('US17.2 (reopened): an approved safety check', () => {
  it('stays Pending Safety Check and names what it is waiting for', () => {
    const { container } = render(<StatusBadge status="Pending Safety Check" safetyApproved />)
    const badge = container.firstElementChild as HTMLElement

    expect(screen.getByText('Pending Safety Check')).toBeInTheDocument()
    expect(screen.getByText(SAFETY_APPROVED_STAGE)).toHaveClass('status-badge-stage')
    expect(badge).toHaveClass('status-badge-safety', 'status-badge-staged')
    // Read out as one status with its stage, not two run-together phrases.
    expect(badge).toHaveTextContent(
      'Status: Pending Safety Check·, Safety approved, awaiting Coordinator confirmation',
    )
  })

  it('names no stage before the approval', () => {
    const { container } = render(<StatusBadge status="Pending Safety Check" safetyApproved={false} />)

    expect(screen.queryByText(SAFETY_APPROVED_STAGE)).not.toBeInTheDocument()
    expect(container.firstElementChild).not.toHaveClass('status-badge-staged')
  })

  it('ignores the flag in any other status', () => {
    for (const status of EVENT_STATUSES.filter((item) => item !== 'Pending Safety Check')) {
      const { container, unmount } = render(<StatusBadge status={status} safetyApproved />)
      expect(container.firstElementChild).toHaveTextContent(`Status: ${status}`)
      expect(container.firstElementChild).not.toHaveClass('status-badge-staged')
      unmount()
    }
  })
})
