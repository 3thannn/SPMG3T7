import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EquipmentQueuePage from './EquipmentQueuePage'
import { listEquipmentQueue, updateEquipmentRequest, type EquipmentRequest } from '../equipmentStore'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipmentQueue: vi.fn(), updateEquipmentRequest: vi.fn(),
}))

const list = vi.mocked(listEquipmentQueue)
const update = vi.mocked(updateEquipmentRequest)
const session = buildSession({ role: 'Technical Support', id: '6', name: 'Bryan' })
const request: EquipmentRequest = {
  id: '17', eventId: '101', eventTitle: 'Open Day', equipmentType: 'Microphone',
  quantity: 1, technicalRequirements: 'Two channels', supportNotes: '',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
  status: 'Requested', createdAt: '2026-10-13T09:00:00', version: 3,
}

afterEach(() => vi.resetAllMocks())

it('shows a linked request and keeps Coordinator requirements separate from staff notes', async () => {
  list.mockResolvedValue([request])
  update.mockResolvedValue({ ...request, supportNotes: 'Ready', version: 4 })
  render(<EquipmentQueuePage session={session} focusId="17" />)
  expect(await screen.findByText('Technical requirements: Two channels')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Update request' }))
  await userEvent.type(screen.getByLabelText('Arrangement notes'), 'Ready')
  await userEvent.click(screen.getByRole('button', { name: 'Save request' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('17', {
    supportNotes: 'Ready', quantity: 1, startsAt: '2027-11-02T09:00',
    endsAt: '2027-11-02T17:00', version: 3,
  }, session))
})

it('explains when a notification points to a removed request', async () => {
  list.mockResolvedValue([])
  render(<EquipmentQueuePage session={session} focusId="17" />)
  expect(await screen.findByRole('status')).toHaveTextContent('no longer in the Requested queue')
})
