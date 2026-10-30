import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventEquipment from './EventEquipment'
import {
  createEquipmentRequest, listEquipment, listEventEquipmentRequests,
  updateEquipmentRequest, removeEquipmentRequest, type EquipmentRequest,
} from '../equipmentStore'
import type { EventRecord } from '../eventsStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipment: vi.fn(async () => [{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 1, outOfServiceReason: 'Damaged', usableQuantity: 0 }]),
  listEventEquipmentRequests: vi.fn(async () => []),
  createEquipmentRequest: vi.fn(),
  updateEquipmentRequest: vi.fn(),
  removeEquipmentRequest: vi.fn(),
}))

const catalogue = vi.mocked(listEquipment)
const list = vi.mocked(listEventEquipmentRequests)
const create = vi.mocked(createEquipmentRequest)
const update = vi.mocked(updateEquipmentRequest)
const coordinator = buildSession({ role: 'Event Coordinator', id: '2' })
const organiser = buildSession({ role: 'Event Organiser', id: '1' })
const event = {
  id: '101', title: 'Open Day', status: 'Planning', coordinatorId: '2',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
} as EventRecord
const line: EquipmentRequest = {
  id: '1', eventId: '101', eventTitle: 'Open Day', equipmentType: 'Microphone', requestedEquipmentId: '1', equipmentName: 'Mic',
  quantity: 1, technicalRequirements: 'Two channels', supportNotes: '',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
  status: 'Requested', createdAt: '2026-10-13T09:00:00', version: 1,
}

afterEach(() => { vi.resetAllMocks(); vi.unstubAllEnvs() })

it('distinguishes catalogue items with the same type and submits the chosen ID', async () => {
  catalogue.mockResolvedValue([
    { id: '1', name: 'Handheld mic', type: 'Microphone', description: 'For speeches', location: 'Main Store', totalQuantity: 5, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 5 },
    { id: '2', name: 'Lapel mic', type: 'Microphone', description: 'Hands-free', location: 'East Store', totalQuantity: 3, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 3 },
  ])
  list.mockResolvedValue([])
  create.mockResolvedValue({ ...line, requestedEquipmentId: '2', equipmentName: 'Lapel mic' })
  render(<EventEquipment event={event} session={coordinator} />)
  await userEvent.selectOptions(await screen.findByLabelText('Catalogue item'), '2')
  expect(screen.getByText('Hands-free')).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'Handheld mic' })).toBeInTheDocument()
  expect(screen.getByRole('group', { name: 'Microphone' })).toBeInTheDocument()
  expect(screen.getByText('Location: East Store')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  expect(create).toHaveBeenCalledWith('101', expect.objectContaining({ equipmentId: 2 }), coordinator)
})

it('lets the Coordinator revise and resubmit an Unavailable line', async () => {
  list.mockResolvedValueOnce([{ ...line, status: 'Unavailable', unavailableReason: 'Only 2 available', version: 2 }])
    .mockResolvedValueOnce([{ ...line, quantity: 2, version: 3 }])
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: 'Wireless', location: 'Store', totalQuantity: 3, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 3 }])
  update.mockResolvedValue({ ...line, quantity: 2, version: 3 })
  render(<EventEquipment event={event} session={coordinator} />)
  expect(await screen.findByText('Unavailable reason: Only 2 available')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Revise and resubmit' }))
  const form = screen.getByRole('heading', { name: 'Revise and resubmit equipment request' }).closest('form')!
  await userEvent.clear(within(form).getByLabelText('Quantity'))
  await userEvent.type(within(form).getByLabelText('Quantity'), '2')
  await userEvent.click(within(form).getByRole('button', { name: 'Resubmit request' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('1', expect.objectContaining({ version: 2, quantity: 2 }), coordinator))
  expect(await screen.findByRole('status')).toHaveTextContent('Resubmitted Microphone request.')
  expect(screen.queryByText('Unavailable reason: Only 2 available')).not.toBeInTheDocument()
})

it('lets the Coordinator remove an Unavailable line', async () => {
  list.mockResolvedValueOnce([{ ...line, status: 'Unavailable', version: 2 }]).mockResolvedValueOnce([])
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: 'Wireless', location: 'Store', totalQuantity: 3, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 3 }])
  vi.mocked(removeEquipmentRequest).mockResolvedValue(undefined)
  render(<EventEquipment event={event} session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Remove' }))
  expect(removeEquipmentRequest).toHaveBeenCalledWith('1', 2, coordinator)
  expect(await screen.findByRole('status')).toHaveTextContent('Removed Microphone request.')
})

it.each(['Reserved', 'Removed'] as const)('does not offer recovery for %s lines', async (status) => {
  list.mockResolvedValue([{ ...line, status }]); catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: 'Wireless', location: 'Store', totalQuantity: 3, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 3 }])
  render(<EventEquipment event={event} session={coordinator} />)
  await screen.findByText('Quantity: 1')
  expect(screen.queryByRole('button', { name: 'Revise and resubmit' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
})

it.each(['UTC', 'Asia/Singapore'])('offers catalogue items and SGT event-time defaults in %s', async (timezone) => {
  vi.stubEnv('TZ', timezone)
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 1, outOfServiceReason: 'Damaged', usableQuantity: 0 }])
  list.mockResolvedValueOnce([]).mockResolvedValueOnce([line])
  create.mockResolvedValue(line)
  render(<EventEquipment event={event} session={coordinator} />)
  expect(await screen.findByRole('heading', { name: 'Request equipment' })).toBeInTheDocument()
  expect(screen.getByLabelText('Needed from')).toHaveValue('2027-11-02T09:00')
  expect(screen.getByLabelText('Needed until')).toHaveValue('2027-11-02T17:00')
  await userEvent.selectOptions(screen.getByLabelText('Catalogue item'), '1')
  await userEvent.type(screen.getByLabelText('Technical requirements (optional)'), 'Two channels')
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('101', {
    equipmentId: 1, technicalRequirements: 'Two channels',
    quantity: 1, startsAt: '2027-11-02T09:00', endsAt: '2027-11-02T17:00',
  }, coordinator))
  expect(await screen.findByText('Quantity: 1')).toBeInTheDocument()
  expect(screen.getByText('02 Nov 2027, 09:00 – 17:00')).toBeInTheDocument()
})

it('shows read-only equipment for the Organiser and before Planning', async () => {
  list.mockResolvedValue([line])
  render(<EventEquipment event={{ ...event, status: 'Approved' }} session={organiser} />)
  expect(await screen.findByText('Quantity: 1')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request equipment' })).not.toBeInTheDocument()
  expect(catalogue).not.toHaveBeenCalled()
})

it.each(['Submitted', 'Under Review', 'Approved'] as const)(
  'keeps the equipment section read-only while the event is %s', async (status) => {
    render(<EventEquipment event={{ ...event, status }} session={coordinator} />)
    expect(screen.getByRole('heading', { name: 'Equipment requests' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request equipment' })).not.toBeInTheDocument()
    expect(catalogue).not.toHaveBeenCalled()
  },
)

it('hides request controls from unassigned Coordinators', async () => {
  render(<EventEquipment event={{ ...event, coordinatorId: '3' }} session={coordinator} />)
  expect(screen.queryByRole('button', { name: 'Request equipment' })).not.toBeInTheDocument()
  expect(catalogue).not.toHaveBeenCalled()
})

it('shows a stale-edit conflict without replacing the request', async () => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  list.mockResolvedValue([line])
  update.mockRejectedValue(new ApiError('This request changed. Reload it before editing.', 'unknown', 409))
  render(<EventEquipment event={event} session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save request' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('This request changed')
  expect(screen.getByText('Quantity: 1')).toBeInTheDocument()
})

it('requires an equipment end time when the event has none', async () => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  create.mockResolvedValue(line)
  render(<EventEquipment event={{ ...event, endsAt: '' }} session={coordinator} />)
  await userEvent.selectOptions(await screen.findByLabelText('Catalogue item'), '1')
  expect(screen.getByLabelText('Needed until')).toHaveValue('')
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Enter a needed end time')
  expect(create).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('Needed until'), '2027-11-02T17:00')
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  await waitFor(() => expect(create).toHaveBeenCalled())
})

it.each(['0', '2147483648'])('refuses an out-of-range quantity of %s', async (quantity) => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  render(<EventEquipment event={event} session={coordinator} />)
  await userEvent.selectOptions(await screen.findByLabelText('Catalogue item'), '1')
  await userEvent.clear(screen.getByLabelText('Quantity'))
  await userEvent.type(screen.getByLabelText('Quantity'), quantity)
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Quantity must be a whole number')
  expect(create).not.toHaveBeenCalled()
})

it('shows the form after an Approved event enters Planning', async () => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  const view = render(<EventEquipment event={{ ...event, status: 'Approved' }} session={coordinator} />)
  expect(screen.getByText(/Request the first venue/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request equipment' })).not.toBeInTheDocument()
  view.rerender(<EventEquipment event={event} session={coordinator} />)
  expect(await screen.findByRole('button', { name: 'Request equipment' })).toBeEnabled()
})

it('shows a retry without risking a duplicate request when the list fails to load', async () => {
  list.mockRejectedValue(new Error('request list unavailable'))
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  render(<EventEquipment event={event} session={coordinator} />)
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Retry equipment requests' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Request equipment' })).not.toBeInTheDocument()
})
