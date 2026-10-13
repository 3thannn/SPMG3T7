import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { EquipmentDetailPage, EquipmentFormPage, EquipmentPage } from './EquipmentPage'
import { getEquipment, listEquipment, saveEquipment } from '../equipmentStore'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipment: vi.fn(), saveEquipment: vi.fn(),
  getEquipment: vi.fn(),
}))

const list = vi.mocked(listEquipment)
const save = vi.mocked(saveEquipment)
const get = vi.mocked(getEquipment)
const support = buildSession({ role: 'Technical Support' })
const coordinator = buildSession({ role: 'Event Coordinator' })
afterEach(() => vi.resetAllMocks())

it('shows usable stock and read-only access for Coordinators', async () => {
  list.mockResolvedValue([{
    id: '1', name: 'Projector', type: 'Projector', description: '', location: 'AV Store',
    totalQuantity: 4, outOfServiceQuantity: 4, outOfServiceReason: 'Maintenance', usableQuantity: 0,
  }])
  render(<EquipmentPage session={coordinator} />)
  expect(await screen.findByText('Usable:', { exact: false })).toBeInTheDocument()
  expect(screen.getByText('4 out of service: Maintenance')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Edit equipment' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Add equipment' })).not.toBeInTheDocument()
})

it('refuses an out-of-service count above total before saving', async () => {
  render(<EquipmentFormPage session={support} />)
  await userEvent.type(screen.getByLabelText('Name'), 'Projector')
  await userEvent.type(screen.getByLabelText('Type'), 'Projector')
  await userEvent.type(screen.getByLabelText('Location'), 'AV Store')
  await userEvent.clear(screen.getByLabelText('Total quantity'))
  await userEvent.type(screen.getByLabelText('Total quantity'), '1')
  await userEvent.clear(screen.getByLabelText('Out-of-service quantity'))
  await userEvent.type(screen.getByLabelText('Out-of-service quantity'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Save equipment' }))
  expect(screen.getByRole('alert')).toHaveTextContent('no greater than the total')
  expect(save).not.toHaveBeenCalled()
})

it('shows full item details to a Coordinator without edit controls', async () => {
  get.mockResolvedValue({
    id: '1', name: 'Projector', type: 'Projector', description: 'Laser', location: 'AV Store',
    totalQuantity: 4, outOfServiceQuantity: 1, outOfServiceReason: 'Maintenance', usableQuantity: 3,
  })
  render(<EquipmentDetailPage session={coordinator} id="1" />)
  expect(await screen.findByRole('heading', { name: 'Projector' })).toBeInTheDocument()
  expect(screen.getByText('Reason: Maintenance')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Edit equipment' })).not.toBeInTheDocument()
})
