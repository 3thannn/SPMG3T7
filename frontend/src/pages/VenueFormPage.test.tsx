/**
 * The create and edit form — US9.1a and US9.1b.
 *
 * One page serves both, so most of these assert that it behaves as the right
 * one of the two: which fields it starts with, which call it makes on submit,
 * and where it goes afterwards. The validation is checked here as messages on
 * screen; the same rules are enforced again by the server, and that is where
 * they are the rule.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import VenueFormPage from './VenueFormPage'
import {
  VenueRuleError,
  createVenue,
  getVenue,
  saveVenue,
  type VenueRecheck,
  type VenueRecord,
} from '../venuesStore'
import { buildSession } from '../test/sessions'

vi.mock('../venuesStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../venuesStore')>()),
  getVenue: vi.fn(),
  createVenue: vi.fn(),
  saveVenue: vi.fn(),
}))

const getVenueMock = vi.mocked(getVenue)
const createVenueMock = vi.mocked(createVenue)
const saveVenueMock = vi.mocked(saveVenue)

afterEach(() => {
  vi.resetAllMocks()
})

const venueStaff = buildSession({
  role: 'Venue Staff',
  id: '3',
  name: 'Sam',
  email: 'sam@example.edu',
})

function buildVenue(overrides: Partial<VenueRecord> = {}): VenueRecord {
  return {
    id: '1',
    name: 'Great Hall',
    location: 'Main Campus, Building A',
    capacity: 500,
    facilities: 'Stage, PA system',
    accessibilityFeatures: 'Step-free access',
    operatingHours: '08:00-22:00',
    supportedLayouts: 'Theatre, standing',
    createdAt: '2026-01-05T09:00:00',
    updatedAt: '2026-01-05T09:00:00',
    ...overrides,
  }
}

/** Fill the three required fields, which every valid submit needs. */
async function fillRequired(
  values: { name?: string; location?: string; capacity?: string } = {},
) {
  await userEvent.type(screen.getByLabelText('Name'), values.name ?? 'Atrium')
  await userEvent.type(screen.getByLabelText('Location'), values.location ?? 'Science Quarter')
  await userEvent.type(screen.getByLabelText('Capacity'), values.capacity ?? '90')
}

// --- US9.1a: creating -------------------------------------------------------

it('starts empty when creating', () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)

  expect(screen.getByRole('heading', { name: 'Add a venue' })).toBeInTheDocument()
  expect(screen.getByLabelText('Name')).toHaveValue('')
  expect(screen.getByLabelText('Capacity')).toHaveValue('')
  expect(getVenueMock).not.toHaveBeenCalled()
})

it('offers the required and the optional fields', () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)

  for (const label of [
    'Name',
    'Location',
    'Capacity',
    'Facilities',
    'Accessibility features',
    'Supported layouts',
    'Operating hours',
  ]) {
    expect(screen.getByLabelText(label)).toBeInTheDocument()
  }
})

it('has no input for a system-generated field', () => {
  // US9.1b: `id` and `createdAt` are not editable, and the surest way to
  // honour that is to give them nowhere to be typed.
  render(<VenueFormPage venueId={null} session={venueStaff} />)

  expect(screen.queryByLabelText(/^id$/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/created/i)).not.toBeInTheDocument()
})

it('creates a venue from the three required fields alone', async () => {
  createVenueMock.mockResolvedValue(buildVenue({ id: '42' }))

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired()
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(createVenueMock).toHaveBeenCalledWith(
      {
        name: 'Atrium',
        location: 'Science Quarter',
        capacity: 90,
        facilities: '',
        accessibilityFeatures: '',
        operatingHours: '',
        supportedLayouts: '',
        // US9.4: untouched, both go as the default of 0.
        setupMinutes: 0,
        turnaroundMinutes: 0,
      },
      venueStaff,
    )
  })
})

it('sends the optional fields when they are filled in', async () => {
  createVenueMock.mockResolvedValue(buildVenue())

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired()
  await userEvent.type(screen.getByLabelText('Facilities'), 'Cafe')
  await userEvent.type(screen.getByLabelText('Accessibility features'), 'Ramp')
  await userEvent.type(screen.getByLabelText('Supported layouts'), 'Standing')
  await userEvent.type(screen.getByLabelText('Operating hours'), '09:00-17:00')
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(createVenueMock.mock.calls[0][0]).toMatchObject({
      facilities: 'Cafe',
      accessibilityFeatures: 'Ramp',
      supportedLayouts: 'Standing',
      operatingHours: '09:00-17:00',
    })
  })
})

it('trims what was typed rather than storing the spaces', async () => {
  createVenueMock.mockResolvedValue(buildVenue())

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired({ name: '  Atrium  ' })
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(createVenueMock.mock.calls[0][0].name).toBe('Atrium')
  })
})

it('refuses to submit without a name', async () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await userEvent.type(screen.getByLabelText('Location'), 'Science Quarter')
  await userEvent.type(screen.getByLabelText('Capacity'), '90')
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the venue a name.')
  expect(createVenueMock).not.toHaveBeenCalled()
})

it('refuses to submit without a location', async () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await userEvent.type(screen.getByLabelText('Name'), 'Atrium')
  await userEvent.type(screen.getByLabelText('Capacity'), '90')
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the venue a location.')
  expect(createVenueMock).not.toHaveBeenCalled()
})

it('refuses to submit without a capacity', async () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await userEvent.type(screen.getByLabelText('Name'), 'Atrium')
  await userEvent.type(screen.getByLabelText('Location'), 'Science Quarter')
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the venue a capacity.')
  expect(createVenueMock).not.toHaveBeenCalled()
})

it('refuses a capacity that is not a positive whole number', async () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)

  for (const capacity of ['0', 'many', '-5', '1.5']) {
    await userEvent.clear(screen.getByLabelText('Capacity'))
    await userEvent.type(screen.getByLabelText('Capacity'), capacity)
    await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/positive whole number/)
  }
  expect(createVenueMock).not.toHaveBeenCalled()
})

it('shows the reason when the server refuses the name', async () => {
  createVenueMock.mockRejectedValue(
    new VenueRuleError("A venue called 'Atrium' is already in the catalogue."),
  )

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired()
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/already in the catalogue/)
})

it('says something useful when the save fails for another reason', async () => {
  createVenueMock.mockRejectedValue(new Error('network down'))

  render(<VenueFormPage venueId={null} session={venueStaff} />)
  await fillRequired()
  await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not save this venue/)
})

// --- US9.1b: editing --------------------------------------------------------

it('loads the venue into the form when editing', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueFormPage venueId="1" session={venueStaff} />)

  expect(await screen.findByRole('heading', { name: 'Edit venue' })).toBeInTheDocument()
  expect(screen.getByLabelText('Name')).toHaveValue('Great Hall')
  expect(screen.getByLabelText('Location')).toHaveValue('Main Campus, Building A')
  expect(screen.getByLabelText('Capacity')).toHaveValue('500')
  expect(screen.getByLabelText('Supported layouts')).toHaveValue('Theatre, standing')
})

it('saves the change against that venue', async () => {
  getVenueMock.mockResolvedValue(buildVenue({ id: '7' }))
  saveVenueMock.mockResolvedValue(buildVenue({ id: '7', capacity: 450 }))

  render(<VenueFormPage venueId="7" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Edit venue' })

  await userEvent.clear(screen.getByLabelText('Capacity'))
  await userEvent.type(screen.getByLabelText('Capacity'), '450')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => {
    expect(saveVenueMock).toHaveBeenCalledWith(
      '7',
      expect.objectContaining({ capacity: 450 }),
      venueStaff,
    )
  })
  expect(createVenueMock).not.toHaveBeenCalled()
})

it('can clear an optional field, because editing is a replacement', async () => {
  getVenueMock.mockResolvedValue(buildVenue())
  saveVenueMock.mockResolvedValue(buildVenue({ facilities: '' }))

  render(<VenueFormPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Edit venue' })

  await userEvent.clear(screen.getByLabelText('Facilities'))
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => {
    expect(saveVenueMock.mock.calls[0][1].facilities).toBe('')
  })
})

it('never sends a system-generated field in the payload', async () => {
  getVenueMock.mockResolvedValue(buildVenue())
  saveVenueMock.mockResolvedValue(buildVenue())

  render(<VenueFormPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Edit venue' })
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => expect(saveVenueMock).toHaveBeenCalled())
  const payload = saveVenueMock.mock.calls[0][1] as Record<string, unknown>
  expect(payload).not.toHaveProperty('id')
  expect(payload).not.toHaveProperty('createdAt')
  expect(payload).not.toHaveProperty('updatedAt')
})

it('applies the same validation when editing', async () => {
  getVenueMock.mockResolvedValue(buildVenue())

  render(<VenueFormPage venueId="1" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Edit venue' })

  await userEvent.clear(screen.getByLabelText('Name'))
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Give the venue a name.')
  expect(saveVenueMock).not.toHaveBeenCalled()
})

it('says when the venue being edited is not there', async () => {
  getVenueMock.mockResolvedValue(null)

  render(<VenueFormPage venueId="404" session={venueStaff} />)

  expect(await screen.findByText('Venue not found')).toBeInTheDocument()
  expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
})

it('distinguishes an unreachable API from a missing venue', async () => {
  getVenueMock.mockRejectedValue(new Error('network down'))

  render(<VenueFormPage venueId="1" session={venueStaff} />)

  expect(await screen.findByRole('alert')).toHaveTextContent(/Could not load this venue/)
  expect(screen.queryByText('Venue not found')).not.toBeInTheDocument()
})

it('cancels back to the venue it was editing', async () => {
  getVenueMock.mockResolvedValue(buildVenue({ id: '7' }))

  render(<VenueFormPage venueId="7" session={venueStaff} />)
  await screen.findByRole('heading', { name: 'Edit venue' })

  expect(screen.getByRole('link', { name: /Back to venue/ })).toHaveAttribute(
    'href',
    '#/venues/7',
  )
})

it('cancels back to the catalogue when creating', () => {
  render(<VenueFormPage venueId={null} session={venueStaff} />)

  expect(screen.getByRole('link', { name: /Back to venues/ })).toHaveAttribute(
    'href',
    '#/venues',
  )
})

// --- US9.4: setup and turnaround time -------------------------------------------

const recheckWith = (conflicts: VenueRecheck['conflicts'], checkedBookings = 2): VenueRecheck => ({
  setupMinutes: 30,
  turnaroundMinutes: 45,
  checkedBookings,
  conflicts,
})

const bookingWindow = (bookingId: string, from: string, to: string) => ({
  bookingId,
  eventId: `9${bookingId}`,
  startsAt: from,
  endsAt: to,
  occupiedFrom: from,
  occupiedTo: to,
})

const clash = (causedByChange: boolean, first = '1', second = '2') => ({
  first: bookingWindow(first, '2027-03-01T09:30', '2027-03-01T12:45'),
  second: bookingWindow(second, '2027-03-01T12:00', '2027-03-01T14:45'),
  causedByChange,
})

describe('US9.4 — setup and turnaround time', () => {
  it('offers both fields on create, starting at the default of 0', () => {
    render(<VenueFormPage venueId={null} session={venueStaff} />)

    expect(screen.getByLabelText('Setup time (minutes)')).toHaveValue('0')
    expect(screen.getByLabelText('Turnaround time (minutes)')).toHaveValue('0')
    expect(screen.getByLabelText('Setup time (minutes)')).toHaveAccessibleDescription(
      'Time to prepare the room before each booking. Whole minutes, 0 to 1440.',
    )
    expect(screen.getByLabelText('Turnaround time (minutes)')).toHaveAccessibleDescription(
      'Time to reset the room after each booking. Whole minutes, 0 to 1440.',
    )
  })

  it('sends the values typed on create', async () => {
    createVenueMock.mockResolvedValue(buildVenue({ id: '42' }))

    render(<VenueFormPage venueId={null} session={venueStaff} />)
    await fillRequired()
    await userEvent.clear(screen.getByLabelText('Setup time (minutes)'))
    await userEvent.type(screen.getByLabelText('Setup time (minutes)'), '30')
    await userEvent.clear(screen.getByLabelText('Turnaround time (minutes)'))
    await userEvent.type(screen.getByLabelText('Turnaround time (minutes)'), ' 1440 ')
    await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(createVenueMock).toHaveBeenCalled())
    expect(createVenueMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({ setupMinutes: 30, turnaroundMinutes: 1440 }),
    )
    expect(window.location.hash).toBe('#/venues/42')
  })

  it('reads an emptied box as 0', async () => {
    createVenueMock.mockResolvedValue(buildVenue({ id: '42' }))

    render(<VenueFormPage venueId={null} session={venueStaff} />)
    await fillRequired()
    await userEvent.clear(screen.getByLabelText('Setup time (minutes)'))
    await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

    await waitFor(() => expect(createVenueMock).toHaveBeenCalled())
    expect(createVenueMock.mock.calls[0][0].setupMinutes).toBe(0)
  })

  it.each([
    ['Setup time (minutes)', '-1', 'The setup time cannot be negative.'],
    ['Setup time (minutes)', '1.5', 'Give the setup time as a whole number of minutes, 0 or more.'],
    ['Setup time (minutes)', '1441', 'Keep the setup time to 1440 minutes (24 hours) or fewer.'],
    ['Turnaround time (minutes)', 'abc', 'Give the turnaround time as a whole number of minutes, 0 or more.'],
    ['Turnaround time (minutes)', '-5', 'The turnaround time cannot be negative.'],
    ['Turnaround time (minutes)', '2000', 'Keep the turnaround time to 1440 minutes (24 hours) or fewer.'],
  ])('refuses %s of %o and sends nothing', async (label, value, message) => {
    render(<VenueFormPage venueId={null} session={venueStaff} />)
    await fillRequired()
    await userEvent.clear(screen.getByLabelText(label))
    await userEvent.type(screen.getByLabelText(label), value)
    await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(createVenueMock).not.toHaveBeenCalled()
  })

  it('shows the server’s refusal if it reads a value differently', async () => {
    createVenueMock.mockRejectedValue(new VenueRuleError('The setup time cannot be negative.'))

    render(<VenueFormPage venueId={null} session={venueStaff} />)
    await fillRequired()
    await userEvent.click(screen.getByRole('button', { name: 'Add venue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The setup time cannot be negative.')
  })

  it('loads the stored values on edit, and says changing them re-checks bookings', async () => {
    getVenueMock.mockResolvedValue(buildVenue({ setupMinutes: 30, turnaroundMinutes: 45 }))

    render(<VenueFormPage venueId="1" session={venueStaff} />)

    expect(await screen.findByLabelText('Setup time (minutes)')).toHaveValue('30')
    expect(screen.getByLabelText('Turnaround time (minutes)')).toHaveValue('45')
    expect(screen.getByText(/Changing either time re-checks this venue’s bookings/)).toBeVisible()
  })

  it('shows 0 for a record saved before US9.4', async () => {
    getVenueMock.mockResolvedValue(buildVenue())

    render(<VenueFormPage venueId="1" session={venueStaff} />)

    expect(await screen.findByLabelText('Setup time (minutes)')).toHaveValue('0')
    expect(screen.getByLabelText('Turnaround time (minutes)')).toHaveValue('0')
  })

  it('sends changed values on edit', async () => {
    getVenueMock.mockResolvedValue(buildVenue())
    saveVenueMock.mockResolvedValue({ ...buildVenue(), recheck: null })

    render(<VenueFormPage venueId="1" session={venueStaff} />)
    const setup = await screen.findByLabelText('Setup time (minutes)')
    await userEvent.clear(setup)
    await userEvent.type(setup, '15')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(saveVenueMock).toHaveBeenCalled())
    expect(saveVenueMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ setupMinutes: 15, turnaroundMinutes: 0 }),
    )
  })

  it.each([
    ['no re-check ran', null],
    ['the re-check found nothing', recheckWith([])],
  ])('goes to the venue when %s', async (_, recheck) => {
    getVenueMock.mockResolvedValue(buildVenue({ id: '7' }))
    saveVenueMock.mockResolvedValue({ ...buildVenue({ id: '7' }), recheck })

    render(<VenueFormPage venueId="7" session={venueStaff} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(window.location.hash).toBe('#/venues/7'))
  })

  it('lists the bookings the re-check found clashing, and removes none', async () => {
    window.location.hash = '#/venues/1/edit'
    getVenueMock.mockResolvedValue(buildVenue())
    saveVenueMock.mockResolvedValue({
      ...buildVenue(),
      recheck: recheckWith([clash(true), clash(false, '3', '4')], 4),
    })

    render(<VenueFormPage venueId="1" session={venueStaff} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Save changes' }))

    expect(
      await screen.findByRole('heading', { name: 'Saved — 2 booking clashes need attention' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      "With 30 minutes' setup and 45 minutes' turnaround, 4 active bookings were checked again. These now overlap. Nothing has been cancelled or removed.",
    )
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]).getByText('New with this change')).toHaveClass('venue-recheck-tag-new')
    expect(within(items[0]).getByText(/^Booking 1 \(event 91\) occupies/)).toBeInTheDocument()
    expect(within(items[0]).getByText(/^Booking 2 \(event 92\) occupies/)).toBeInTheDocument()
    expect(within(items[1]).getByText('Already overlapping')).not.toHaveClass(
      'venue-recheck-tag-new',
    )
    // Stays put until Venue Staff have read it.
    expect(window.location.hash).toBe('#/venues/1/edit')

    await userEvent.click(screen.getByRole('button', { name: 'View venue' }))
    expect(window.location.hash).toBe('#/venues/1')
  })

  it('reads one clash and one booking in the singular', async () => {
    getVenueMock.mockResolvedValue(buildVenue())
    saveVenueMock.mockResolvedValue({ ...buildVenue(), recheck: recheckWith([clash(true)], 1) })

    render(<VenueFormPage venueId="1" session={venueStaff} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Save changes' }))

    expect(
      await screen.findByRole('heading', { name: 'Saved — 1 booking clash needs attention' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('1 active booking was checked again.')
  })
})
