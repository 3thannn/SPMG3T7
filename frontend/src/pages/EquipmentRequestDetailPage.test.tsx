import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EquipmentRequestDetailPage from './EquipmentRequestDetailPage'
import {
  getEquipmentRequest, updateEquipmentRequest, type EquipmentRequestDetail,
} from '../equipmentStore'
import { buildSession } from '../test/sessions'
import { ApiError } from '../api'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  getEquipmentRequest: vi.fn(), updateEquipmentRequest: vi.fn(),
}))

const get = vi.mocked(getEquipmentRequest)
const update = vi.mocked(updateEquipmentRequest)
const session = buildSession({ role: 'Technical Support', id: '6', name: 'Bryan' })
const request: EquipmentRequestDetail = {
  id: '17', eventId: '101', eventTitle: 'Open Day', equipmentType: 'Microphone',
  quantity: 1, technicalRequirements: 'Two channels', supportNotes: '',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
  status: 'Requested', createdAt: '2026-10-13T09:00:00', version: 3,
  removedByName: '',
}

afterEach(() => vi.resetAllMocks())

it('shows request details and updates Technical Support notes', async () => {
  get.mockResolvedValueOnce(request).mockResolvedValueOnce({ ...request, supportNotes: 'Ready', version: 4 })
  update.mockResolvedValue({ ...request, supportNotes: 'Ready', version: 4 })
  render(<EquipmentRequestDetailPage session={session} id="17" />)
  expect(await screen.findByRole('heading', { name: 'Microphone request' })).toBeInTheDocument()
  const back = screen.getByRole('link', { name: /All equipment requests/ })
  expect(back).toHaveAttribute('href', '#/equipment-requests')
  expect(back).toHaveClass('equipment-request-back')
  expect(screen.getByText('Two channels')).toBeInTheDocument()
  expect(screen.getByText('Not recorded yet')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Update request' }))
  await userEvent.type(screen.getByLabelText('Arrangement notes'), 'Ready')
  await userEvent.click(screen.getByRole('button', { name: 'Save request' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('17', {
    supportNotes: 'Ready', quantity: 1, startsAt: '2027-11-02T09:00',
    endsAt: '2027-11-02T17:00', version: 3,
  }, session))
  expect(await screen.findByText('Ready')).toBeInTheDocument()
})

it('identifies who removed a request when an old notification is opened', async () => {
  get.mockResolvedValue({ ...request, status: 'Removed', removedByName: 'Priya' })
  render(<EquipmentRequestDetailPage session={session} id="17" />)
  expect(await screen.findByRole('status')).toHaveTextContent('Priya removed this request.')
  expect(screen.queryByRole('button', { name: 'Update request' })).not.toBeInTheDocument()
})

it('explains when the request ID does not exist', async () => {
  get.mockRejectedValue(new ApiError('Not found', 'unknown', 404))
  render(<EquipmentRequestDetailPage session={session} id="999" />)
  expect(await screen.findByRole('heading', { name: 'Request not found' })).toBeInTheDocument()
})
