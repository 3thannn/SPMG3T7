import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventEquipment from './EventEquipment'
import {
  createEquipmentRequest, listEquipment, listEventEquipmentRequests,
  updateEquipmentRequest, type EquipmentRequest,
} from '../equipmentStore'
import type { EventRecord } from '../eventsStore'
import { formatBookingTimes } from '../eventsStore'
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
  id: '1', eventId: '101', eventTitle: 'Open Day', equipmentType: 'Microphone',
  quantity: 1, technicalRequirements: 'Two channels', supportNotes: '',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
  status: 'Requested', createdAt: '2026-10-13T09:00:00', version: 1,
}

afterEach(() => { vi.resetAllMocks() })

it('offers catalogue types and event-time defaults to the assigned Coordinator', async () => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 1, outOfServiceReason: 'Damaged', usableQuantity: 0 }])
  list.mockResolvedValueOnce([]).mockResolvedValueOnce([line])
  create.mockResolvedValue(line)
  render(<EventEquipment event={event} session={coordinator} />)
  expect(await screen.findByRole('heading', { name: 'Request equipment' })).toBeInTheDocument()
  expect(screen.getByLabelText('Needed from')).toHaveValue('2027-11-02T09:00')
  expect(screen.getByLabelText('Needed until')).toHaveValue('2027-11-02T17:00')
  await userEvent.selectOptions(screen.getByLabelText('Equipment type'), 'Microphone')
  await userEvent.type(screen.getByLabelText('Technical requirements (optional)'), 'Two channels')
  await userEvent.click(screen.getByRole('button', { name: 'Request equipment' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('101', {
    equipmentType: 'Microphone', technicalRequirements: 'Two channels',
    quantity: 1, startsAt: '2027-11-02T09:00', endsAt: '2027-11-02T17:00',
  }, coordinator))
  expect(await screen.findByText('Quantity: 1')).toBeInTheDocument()
  expect(screen.getByText(formatBookingTimes(line.startsAt, line.endsAt))).toBeInTheDocument()
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
  await userEvent.selectOptions(await screen.findByLabelText('Equipment type'), 'Microphone')
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
  await userEvent.selectOptions(await screen.findByLabelText('Equipment type'), 'Microphone')
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
