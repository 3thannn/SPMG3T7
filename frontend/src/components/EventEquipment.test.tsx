import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventEquipment from './EventEquipment'
import {
  createEquipmentRequest, listEquipment, listEventEquipmentRequests,
  updateEquipmentRequest, type EquipmentRequest,
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
  list.mockResolvedValue([])
  create.mockResolvedValue(line)
  const onChanged = vi.fn()
  render(<EventEquipment event={event} session={coordinator} onChanged={onChanged} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Add equipment request' }))
  expect(screen.getByLabelText('Needed from')).toHaveValue('2027-11-02T09:00')
  expect(screen.getByLabelText('Needed until')).toHaveValue('2027-11-02T17:00')
  await userEvent.selectOptions(screen.getByLabelText('Equipment type'), 'Microphone')
  await userEvent.type(screen.getByLabelText('Technical requirements'), 'Two channels')
  await userEvent.click(screen.getByRole('button', { name: 'Save request' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('101', {
    equipmentType: 'Microphone', technicalRequirements: 'Two channels',
    quantity: 1, startsAt: '2027-11-02T09:00', endsAt: '2027-11-02T17:00',
  }, coordinator))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
})

it('hides request controls from unassigned Coordinators and non-Planning events', async () => {
  render(<EventEquipment event={{ ...event, coordinatorId: '3' }} session={coordinator} />)
  expect(screen.queryByRole('button', { name: 'Add equipment request' })).not.toBeInTheDocument()
  expect(list).not.toHaveBeenCalled()
})

it('shows a stale-edit conflict without replacing the request', async () => {
  catalogue.mockResolvedValue([{ id: '1', name: 'Mic', type: 'Microphone', description: '', location: 'Store', totalQuantity: 1, outOfServiceQuantity: 0, outOfServiceReason: '', usableQuantity: 1 }])
  list.mockResolvedValue([line])
  update.mockRejectedValue(new ApiError('This request changed. Reload it before editing.', 'unknown', 409))
  render(<EventEquipment event={event} session={coordinator} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save request' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('This request changed')
  expect(screen.getByText('Microphone · 1 · Requested')).toBeInTheDocument()
})
