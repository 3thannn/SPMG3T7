import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import EquipmentQueuePage from './EquipmentQueuePage'
import { listEquipmentQueue, type EquipmentRequest } from '../equipmentStore'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipmentQueue: vi.fn(),
}))

const list = vi.mocked(listEquipmentQueue)
const session = buildSession({ role: 'Technical Support', id: '6', name: 'Bryan' })
const request: EquipmentRequest = {
  id: '17', eventId: '101', eventTitle: 'Open Day', equipmentType: 'Microphone',
  quantity: 1, technicalRequirements: 'Two channels', supportNotes: '',
  startsAt: '2027-11-02T09:00:00', endsAt: '2027-11-02T17:00:00',
  status: 'Requested', createdAt: '2026-10-13T09:00:00', version: 3,
}

afterEach(() => vi.resetAllMocks())

it('shows scannable request cards that open distinct detail pages', async () => {
  list.mockResolvedValue([request, { ...request, id: '18', equipmentType: 'Projector' }])
  render(<EquipmentQueuePage session={session} />)
  const cards = await screen.findAllByRole('link')
  expect(cards).toHaveLength(2)
  expect(cards[0]).toHaveAttribute('href', '#/equipment-requests/17')
  expect(cards[1]).toHaveAttribute('href', '#/equipment-requests/18')
  expect(cards[0]).toHaveTextContent('Microphone')
  expect(cards[0]).toHaveTextContent('Open Day')
  expect(cards[0]).toHaveTextContent('Two channels')
  expect(screen.queryByRole('button', { name: 'Update request' })).not.toBeInTheDocument()
})

it('shows an empty queue message', async () => {
  list.mockResolvedValue([])
  render(<EquipmentQueuePage session={session} />)
  expect(await screen.findByRole('heading', { name: 'No equipment requests are waiting' })).toBeInTheDocument()
})
