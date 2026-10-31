/**
 * US19.3: the request page around the reservation card, on the paths
 * EquipmentRequestDetailPage.test.tsx does not reach. The card has its own
 * tests; here it is a stand-in that can ask the page to reload or report a
 * decision, which is all the page does with it.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EquipmentRequestDetailPage from './EquipmentRequestDetailPage'
import {
  getEquipmentRequest,
  updateEquipmentRequest,
  type EquipmentRequest,
  type EquipmentRequestDetail,
} from '../equipmentStore'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  getEquipmentRequest: vi.fn(),
  updateEquipmentRequest: vi.fn(),
}))

vi.mock('../components/EquipmentReservation', () => ({
  default: ({
    onRefresh,
    onDecided,
  }: {
    onRefresh: () => Promise<void>
    onDecided: (updated: EquipmentRequest) => void
  }) => (
    <>
      <button type="button" onClick={() => void onRefresh()}>
        Stand-in: refresh
      </button>
      <button
        type="button"
        onClick={() => onDecided({ status: 'Reserved', version: 4 } as EquipmentRequest)}
      >
        Stand-in: reserved
      </button>
    </>
  ),
}))

const get = vi.mocked(getEquipmentRequest)
const update = vi.mocked(updateEquipmentRequest)
const support = buildSession({ role: 'Technical Support', id: '6', name: 'Bryan' })

const REQUEST: EquipmentRequestDetail = {
  id: '17',
  eventId: '101',
  eventTitle: 'Open Day',
  equipmentType: 'Microphone',
  quantity: 1,
  technicalRequirements: 'Two channels',
  supportNotes: '',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
  status: 'Requested',
  createdAt: '2026-10-13T09:00:00',
  version: 3,
  removedByName: '',
}

const UNREACHABLE = new TypeError('Failed to fetch')

afterEach(() => {
  vi.resetAllMocks()
})

it('says when the request could not be loaded for a reason other than not existing', async () => {
  get.mockRejectedValue(UNREACHABLE)
  render(<EquipmentRequestDetailPage session={support} id="17" />)

  expect(await screen.findByText(/Could not load this equipment request/)).toBeInTheDocument()
})

it('ignores a failure that lands after the page has gone', async () => {
  let fail!: (error: Error) => void
  get.mockReturnValue(new Promise((_resolve, reject) => (fail = reject)))
  const { unmount } = render(<EquipmentRequestDetailPage session={support} id="17" />)

  unmount()
  fail(UNREACHABLE)
  await Promise.resolve()

  expect(get).toHaveBeenCalledTimes(1)
})

it('reloads the request when the reservation card asks', async () => {
  const user = userEvent.setup()
  get.mockResolvedValueOnce(REQUEST).mockResolvedValueOnce({ ...REQUEST, quantity: 2 })
  render(<EquipmentRequestDetailPage session={support} id="17" />)

  await user.click(await screen.findByRole('button', { name: 'Stand-in: refresh' }))

  await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
})

it('shows the decision the reservation card reports', async () => {
  const user = userEvent.setup()
  get.mockResolvedValue(REQUEST)
  render(<EquipmentRequestDetailPage session={support} id="17" />)

  await user.click(await screen.findByRole('button', { name: 'Stand-in: reserved' }))

  expect(await screen.findByText('Equipment reserved.')).toBeInTheDocument()
})

it('abandoning an update leaves the request as it was', async () => {
  const user = userEvent.setup()
  get.mockResolvedValue(REQUEST)
  render(<EquipmentRequestDetailPage session={support} id="17" />)

  await user.click(await screen.findByRole('button', { name: 'Update request' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.getByRole('button', { name: 'Update request' })).toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
})

it('says the update was saved but the page could not refresh', async () => {
  const user = userEvent.setup()
  get.mockResolvedValueOnce(REQUEST).mockRejectedValueOnce(UNREACHABLE)
  update.mockResolvedValue({ ...REQUEST, supportNotes: 'Ready', version: 4 })
  render(<EquipmentRequestDetailPage session={support} id="17" />)

  await user.click(await screen.findByRole('button', { name: 'Update request' }))
  await user.type(screen.getByLabelText('Arrangement notes'), 'Ready')
  await user.click(screen.getByRole('button', { name: 'Save request' }))

  expect(await screen.findByText(/Could not refresh this request/)).toBeInTheDocument()
  expect(screen.getByText('Request updated.')).toBeInTheDocument()
})
