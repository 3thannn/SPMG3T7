import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EquipmentReservation from './EquipmentReservation'
import { decideEquipmentRequest, getEquipmentAvailability, formatEquipmentTimes, type EquipmentRequest } from '../equipmentStore'
import { buildSession } from '../test/sessions'
import { ApiError } from '../api'

vi.mock('../equipmentStore', async (original) => ({
  ...(await original<typeof import('../equipmentStore')>()),
  getEquipmentAvailability: vi.fn(), decideEquipmentRequest: vi.fn(),
}))
const session = buildSession({ role: 'Technical Support' })
const request: EquipmentRequest = {
  id: '1', eventId: '2', eventTitle: 'Open Day', equipmentType: 'Projector', quantity: 2,
  technicalRequirements: '', supportNotes: '', startsAt: '2027-11-02T09:00',
  endsAt: '2027-11-02T17:00', status: 'Requested', createdAt: '', version: 1, requestedEquipmentId: '3',
}
const item = { equipmentId: '3', name: 'Projector A', location: 'Store', totalQuantity: 10,
  outOfServiceQuantity: 2, reservedQuantity: 6, availableQuantity: 2, shortfall: 0 }
const onDecided = vi.fn()
const onRefresh = vi.fn().mockResolvedValue(undefined)
afterEach(() => vi.unstubAllEnvs())
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getEquipmentAvailability).mockResolvedValue([item])
})
function show() {
  render(<EquipmentReservation request={request} session={session} onDecided={onDecided} onRefresh={onRefresh} />)
}
async function select() {
  await screen.findByText('Total stock')
}
it('reserves exact available quantity and submits the version and selected item', async () => {
  vi.mocked(decideEquipmentRequest).mockResolvedValue({ ...request, status: 'Reserved', equipmentId: '3' })
  show()
  expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
  await select()
  await userEvent.click(screen.getByRole('button', { name: 'Reserve' }))
  expect(decideEquipmentRequest).toHaveBeenCalledWith('1', 1, { equipmentId: 3 }, session)
  expect(onDecided).toHaveBeenCalledWith(expect.objectContaining({ status: 'Reserved' }))
})

it('uses the Coordinator-selected item automatically and prevents changing it', async () => {
  vi.mocked(decideEquipmentRequest).mockResolvedValue({ ...request, status: 'Reserved', equipmentId: '3' })
  render(<EquipmentReservation request={{ ...request, requestedEquipmentId: '3' }} session={session}
    onDecided={onDecided} onRefresh={onRefresh} />)
  await screen.findByText('Total stock')
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByText('Projector A')).not.toBeInTheDocument()
  expect(screen.getByText('Store')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Reserve' }))
  expect(decideEquipmentRequest).toHaveBeenCalledWith('1', 1, { equipmentId: 3 }, session)
})

it('does not infer an item or offer a selector for an unlinked legacy request', async () => {
  vi.mocked(getEquipmentAvailability).mockResolvedValue([])
  render(<EquipmentReservation request={{ ...request, requestedEquipmentId: null }} session={session}
    onDecided={onDecided} onRefresh={onRefresh} />)
  expect(await screen.findByText(/No item has been selected/)).toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
})
it('shows a shortfall and blocks Reserve while allowing Unavailable with a reason', async () => {
  vi.mocked(getEquipmentAvailability).mockResolvedValue([{ ...item, availableQuantity: 1, shortfall: 1 }])
  vi.mocked(decideEquipmentRequest).mockResolvedValue({ ...request, status: 'Unavailable' })
  show(); await select()
  expect(screen.getByRole('status')).toHaveTextContent('Shortfall: 1')
  expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Mark Unavailable' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Give a reason')
  expect(decideEquipmentRequest).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('Reason for Unavailable'), 'Insufficient stock')
  await userEvent.click(screen.getByRole('button', { name: 'Mark Unavailable' }))
  expect(decideEquipmentRequest).toHaveBeenCalledWith('1', 1, { reason: 'Insufficient stock' }, session)
})
it('shows server conflicts and refreshes availability and request before retrying', async () => {
  vi.mocked(decideEquipmentRequest).mockRejectedValue(new ApiError('Shortfall: 1.', 'insufficient_stock', 409))
  show(); await select()
  vi.mocked(getEquipmentAvailability).mockResolvedValue([{ ...item, availableQuantity: 1, shortfall: 1 }])
  await userEvent.click(screen.getByRole('button', { name: 'Reserve' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Shortfall: 1')
  await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  expect(onDecided).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
})
it('handles unavailable catalogue data', async () => {
  vi.mocked(getEquipmentAvailability).mockRejectedValue(new Error('Offline'))
  show()
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
})

it.each(['UTC', 'Asia/Singapore', 'America/New_York'])('keeps planned SGT windows correct in %s, including midnight', (timezone) => {
  vi.stubEnv('TZ', timezone)
  expect(formatEquipmentTimes('2027-11-02T23:00', '2027-11-03T01:00'))
    .toBe('02 Nov 2027, 23:00 – 03 Nov 2027, 01:00')
})
