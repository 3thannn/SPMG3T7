/**
 * US2.1 (Sprint 3): the five need fields shared by the new-event form and the
 * draft / change-request edit form. Controlled, so these tests drive it through
 * a small stateful harness the way a page does.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import EventNeedsFields from './EventNeedsFields'
import {
  ACCESSIBILITY_OPTIONS,
  FACILITY_OPTIONS,
  LAYOUT_OPTIONS,
  MISSING_MESSAGES,
  NO_NEEDS,
  NOT_REQUIRED,
  type EventNeeds,
} from '../eventNeeds'
import { ANSWERED_NEEDS } from '../test/eventNeeds'

/** Renders the fields over real state, reporting every change to `spy`. */
function Harness({
  initial = NO_NEEDS,
  spy = () => {},
  errors,
  disabled,
}: {
  initial?: EventNeeds
  spy?: (needs: EventNeeds) => void
  errors?: Partial<Record<keyof EventNeeds, string>>
  disabled?: boolean
}) {
  const [needs, setNeeds] = useState(initial)
  return (
    <EventNeedsFields
      needs={needs}
      errors={errors}
      disabled={disabled}
      onChange={(key, value) => {
        const next = { ...needs, [key]: value }
        setNeeds(next)
        spy(next)
      }}
    />
  )
}

const group = (name: string) => screen.getByRole('group', { name })

describe('what is offered', () => {
  it('lists every facility and accessibility option, plus None / Not required', () => {
    render(<Harness />)

    const venue = within(group('Venue requirements')).getAllByRole('checkbox')
    expect(venue.map((box) => box.closest('label')?.textContent)).toEqual([
      ...FACILITY_OPTIONS,
      NOT_REQUIRED,
    ])
    const access = within(group('Accessibility needs')).getAllByRole('checkbox')
    expect(access.map((box) => box.closest('label')?.textContent)).toEqual([
      ...ACCESSIBILITY_OPTIONS,
      NOT_REQUIRED,
    ])
  })

  it('offers each layout, None / Not required, and starts with nothing chosen', () => {
    render(<Harness />)

    const layout = screen.getByLabelText('Preferred layout') as HTMLSelectElement
    expect([...layout.options].map((option) => option.value)).toEqual([
      '',
      ...LAYOUT_OPTIONS,
      NOT_REQUIRED,
    ])
    expect(layout.value).toBe('')
  })

  it('offers a text box and None / Not required for equipment and registration', () => {
    render(<Harness />)

    for (const name of ['Equipment needs', 'Registration needs']) {
      expect(within(group(name)).getByRole('textbox', { name })).toBeEnabled()
      expect(within(group(name)).getByLabelText(NOT_REQUIRED)).not.toBeChecked()
    }
  })

  it('shows what an event already has', () => {
    render(<Harness initial={ANSWERED_NEEDS} />)

    const venue = group('Venue requirements')
    expect(within(venue).getByLabelText('Stage')).toBeChecked()
    expect(within(venue).getByLabelText('Projector')).toBeChecked()
    expect(within(venue).getByLabelText('Lectern')).not.toBeChecked()
    expect(screen.getByLabelText('Preferred layout')).toHaveValue('Theatre')
    expect(within(group('Accessibility needs')).getByLabelText('Wheelchair access')).toBeChecked()
    expect(screen.getByLabelText('Equipment needs')).toHaveValue('Two wireless microphones')
    const registration = group('Registration needs')
    expect(within(registration).getByLabelText(NOT_REQUIRED)).toBeChecked()
    expect(within(registration).getByRole('textbox')).toHaveValue('')
    expect(within(registration).getByRole('textbox')).toBeDisabled()
  })

  it('shows a hint under each field until there is an error', () => {
    render(<Harness />)

    expect(screen.getAllByText(/^Required when submitting\./)).toHaveLength(5)
    expect(group('Venue requirements')).toHaveAttribute(
      'aria-describedby',
      'venueRequirements-hint',
    )
    expect(screen.getByLabelText('Preferred layout')).toHaveAttribute(
      'aria-describedby',
      'preferredLayout-hint',
    )
  })
})

describe('choosing', () => {
  it('ticks facilities in list order and unticks them again', async () => {
    const user = userEvent.setup()
    const spy = vi.fn()
    render(<Harness spy={spy} />)
    const venue = group('Venue requirements')

    await user.click(within(venue).getByLabelText('Projector'))
    await user.click(within(venue).getByLabelText('Stage'))
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ venueRequirements: 'Stage, Projector' }),
    )

    await user.click(within(venue).getByLabelText('Stage'))
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ venueRequirements: 'Projector' }),
    )
  })

  it('makes None / Not required and the options exclude each other', async () => {
    const user = userEvent.setup()
    const spy = vi.fn()
    render(<Harness spy={spy} />)
    const access = group('Accessibility needs')

    await user.click(within(access).getByLabelText('Hearing loop'))
    await user.click(within(access).getByLabelText(NOT_REQUIRED))
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ accessibilityNeeds: NOT_REQUIRED }),
    )
    expect(within(access).getByLabelText('Hearing loop')).not.toBeChecked()

    await user.click(within(access).getByLabelText('Lift'))
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ accessibilityNeeds: 'Lift' }))
    expect(within(access).getByLabelText(NOT_REQUIRED)).not.toBeChecked()
  })

  it('picks a layout, or None / Not required', async () => {
    const user = userEvent.setup()
    const spy = vi.fn()
    render(<Harness spy={spy} />)

    await user.selectOptions(screen.getByLabelText('Preferred layout'), 'Banquet')
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ preferredLayout: 'Banquet' }))

    await user.selectOptions(screen.getByLabelText('Preferred layout'), NOT_REQUIRED)
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ preferredLayout: NOT_REQUIRED }),
    )
  })

  it('takes equipment needs in words, exactly as typed', async () => {
    const user = userEvent.setup()
    const spy = vi.fn()
    render(<Harness spy={spy} />)

    await user.type(screen.getByLabelText('Equipment needs'), ' 2 mics ')
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ equipmentNeeds: ' 2 mics ' }))
  })

  it('answers registration with None / Not required, and can take it back', async () => {
    const user = userEvent.setup()
    const spy = vi.fn()
    render(<Harness spy={spy} />)
    const registration = group('Registration needs')
    await user.type(within(registration).getByRole('textbox'), 'Walk-in')

    await user.click(within(registration).getByLabelText(NOT_REQUIRED))
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ registrationNeeds: NOT_REQUIRED }),
    )
    expect(within(registration).getByRole('textbox')).toBeDisabled()
    expect(within(registration).getByRole('textbox')).toHaveValue('')
    expect(within(registration).getByRole('textbox')).toHaveAttribute('placeholder', '')

    await user.click(within(registration).getByLabelText(NOT_REQUIRED))
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ registrationNeeds: '' }))
    expect(within(registration).getByRole('textbox')).toBeEnabled()
  })
})

describe('errors and disabling', () => {
  it('shows each field’s error in place of its hint and links it', () => {
    render(<Harness errors={MISSING_MESSAGES} />)

    for (const message of Object.values(MISSING_MESSAGES)) {
      expect(screen.getByText(message)).toHaveClass('field-error')
    }
    expect(screen.queryByText(/^Required when submitting\./)).not.toBeInTheDocument()
    expect(group('Venue requirements')).toHaveClass('needs-group-invalid')
    expect(group('Venue requirements')).toHaveAttribute(
      'aria-describedby',
      'venueRequirements-error',
    )
    expect(screen.getByLabelText('Preferred layout')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Preferred layout')).toHaveAccessibleDescription(
      MISSING_MESSAGES.preferredLayout,
    )
    expect(screen.getByLabelText('Equipment needs')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Equipment needs')).toHaveAccessibleDescription(
      MISSING_MESSAGES.equipmentNeeds,
    )
  })

  it('marks nothing invalid without errors', () => {
    render(<Harness />)

    expect(group('Venue requirements')).not.toHaveClass('needs-group-invalid')
    expect(screen.getByLabelText('Preferred layout')).toHaveAttribute('aria-invalid', 'false')
  })

  it('disables every control while the page is busy', () => {
    render(<Harness disabled />)

    for (const box of screen.getAllByRole('checkbox')) expect(box).toBeDisabled()
    expect(screen.getByLabelText('Preferred layout')).toBeDisabled()
    expect(screen.getByLabelText('Equipment needs')).toBeDisabled()
  })
})
