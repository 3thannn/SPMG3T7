import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EquipmentReservation from './EquipmentReservation'
import { decideEquipmentRequest, getEquipmentAvailability, type EquipmentRequest } from '../equipmentStore'
import { buildSession } from '../test/sessions'

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
