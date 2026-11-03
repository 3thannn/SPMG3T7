import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { EquipmentPage } from './EquipmentPage'
import { listEquipment } from '../equipmentStore'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipment: vi.fn(), saveEquipment: vi.fn(),
  getEquipment: vi.fn(), deleteEquipment: vi.fn(),
}))

const list = vi.mocked(listEquipment)




const coordinator = buildSession({ role: 'Event Coordinator' })
afterEach(() => vi.resetAllMocks())

it('shows usable stock and read-only access for Coordinators', async () => {
  list.mockResolvedValue([{
    id: '1', name: 'Projector', type: 'Projector', description: '', location: 'AV Store',
    totalQuantity: 4, outOfServiceQuantity: 4, outOfServiceReason: 'Maintenance', usableQuantity: 0,
  }])
  render(<EquipmentPage session={coordinator} />)
  expect(await screen.findByRole('link', { name: /Projector.*AV Store/ })).toHaveAttribute('href', '#/equipment/1')
  expect(screen.getByText('Usable of 4')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Edit equipment' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Add equipment' })).not.toBeInTheDocument()
})
