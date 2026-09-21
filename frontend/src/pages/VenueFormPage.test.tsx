/**
 * The create and edit form — US9.1a and US9.1b.
 *
 * One page serves both, so most of these assert that it behaves as the right
 * one of the two: which fields it starts with, which call it makes on submit,
 * and where it goes afterwards. The validation is checked here as messages on
 * screen; the same rules are enforced again by the server, and that is where
 * they are the rule.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import VenueFormPage from './VenueFormPage'
import {
  VenueRuleError,
  createVenue,
  getVenue,
  saveVenue,
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
