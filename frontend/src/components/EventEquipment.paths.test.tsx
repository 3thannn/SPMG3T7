/**
 * US19: the event's equipment card and request editor, on the paths
 * EventEquipment.test.tsx does not reach — the catalogue or the lines failing
 * to load, a removal refused, a retry, an edit abandoned, and the editor's own
 * checks before anything is sent.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import EventEquipment, { RequestEditor } from './EventEquipment'
import {
  listEquipment,
  listEventEquipmentRequests,
  removeEquipmentRequest,
  type Equipment,
  type EquipmentRequest,
} from '../equipmentStore'
import type { EventRecord } from '../eventsStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipment: vi.fn(async () => []),
  listEventEquipmentRequests: vi.fn(async () => []),
  removeEquipmentRequest: vi.fn(),
}))

const catalogue = vi.mocked(listEquipment)
const list = vi.mocked(listEventEquipmentRequests)
const remove = vi.mocked(removeEquipmentRequest)
const coordinator = buildSession({ role: 'Event Coordinator', id: '2' })

const EVENT = {
  id: '101',
  title: 'Open Day',
  status: 'Planning',
  coordinatorId: '2',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
} as EventRecord

function item(id: string, name: string, type: string): Equipment {
  return {
    id,
    name,
    type,
    description: '',
    location: 'Store',
    totalQuantity: 3,
    outOfServiceQuantity: 0,
    outOfServiceReason: '',
    usableQuantity: 3,
  }
}

const LINE: EquipmentRequest = {
  id: '1',
  eventId: '101',
  eventTitle: 'Open Day',
  equipmentType: 'Microphone',
  requestedEquipmentId: '1',
  equipmentName: 'Mic',
  quantity: 1,
  technicalRequirements: '',
  supportNotes: '',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
  status: 'Requested',
  createdAt: '2026-10-13T09:00:00',
  version: 1,
}

const BLANK_FORM = {
  equipmentType: '',
  quantity: '1',
  technicalRequirements: '',
  supportNotes: '',
  startsAt: '2027-11-02T09:00',
  endsAt: '2027-11-02T17:00',
}

const UNREACHABLE = new TypeError('Failed to fetch')

afterEach(() => {
  vi.resetAllMocks()
})

it('groups the catalogue by type, alphabetically', async () => {
  catalogue.mockResolvedValue([
    item('1', 'Mic', 'Microphone'),
    item('2', 'Beamer', 'Projector'),
    item('3', 'Cable', 'Audio'),
  ])
  list.mockResolvedValue([])
  render(<EventEquipment event={EVENT} session={coordinator} />)

  await screen.findByRole('group', { name: 'Audio' })

  const groups = screen.getAllByRole('group').map((group) => group.getAttribute('label'))
  expect(groups.filter(Boolean)).toEqual(['Audio', 'Microphone', 'Projector'])
})

it('says when the catalogue could not be loaded', async () => {
  catalogue.mockRejectedValue(UNREACHABLE)
  list.mockResolvedValue([])
  render(<EventEquipment event={EVENT} session={coordinator} />)

  expect(await screen.findByText(/Could not load the equipment catalogue/)).toBeInTheDocument()
})

it('ignores a catalogue that arrives after the card has gone', async () => {
  let deliver!: (items: Equipment[]) => void
  catalogue.mockReturnValue(new Promise((resolve) => (deliver = resolve)))
  list.mockResolvedValue([])
  const { unmount } = render(<EventEquipment event={EVENT} session={coordinator} />)

  unmount()
  deliver([item('1', 'Mic', 'Microphone')])
  await Promise.resolve()

  expect(catalogue).toHaveBeenCalledTimes(1)
})

it('offers a retry when the lines could not be loaded, and loads them again', async () => {
  const user = userEvent.setup()
  list.mockRejectedValueOnce(UNREACHABLE).mockResolvedValueOnce([LINE])
  render(<EventEquipment event={EVENT} session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Retry equipment requests' }))

  expect(await screen.findByText('Mic')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Retry equipment requests' })).not.toBeInTheDocument()
})

it('keeps the retry when loading fails again', async () => {
  const user = userEvent.setup()
  list.mockRejectedValue(UNREACHABLE)
  render(<EventEquipment event={EVENT} session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Retry equipment requests' }))

  await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  expect(await screen.findByText(/Could not refresh equipment requests/)).toBeInTheDocument()
})

it('says why a removal was refused and keeps the line', async () => {
  const user = userEvent.setup()
  catalogue.mockResolvedValue([item('1', 'Mic', 'Microphone')])
  list.mockResolvedValue([LINE])
  remove.mockRejectedValue(
    new ApiError('This request changed. Reload it before removing it.', 'stale_request', 409),
  )
  render(<EventEquipment event={EVENT} session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Remove' }))

  expect(
    await screen.findByText('This request changed. Reload it before removing it.'),
  ).toBeInTheDocument()
  const lines = screen.getByRole('list', { name: 'Equipment requests for this event' })
  expect(within(lines).getByText('Mic')).toBeInTheDocument()
})

it('abandoning an edit leaves the line as it was', async () => {
  const user = userEvent.setup()
  catalogue.mockResolvedValue([item('1', 'Mic', 'Microphone')])
  list.mockResolvedValue([LINE])
  render(<EventEquipment event={EVENT} session={coordinator} />)

  await user.click(await screen.findByRole('button', { name: 'Edit' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.queryByRole('button', { name: 'Save request' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
})

it('the editor asks for an item before sending anything', async () => {
  const user = userEvent.setup()
  const onSave = vi.fn()
  render(
    <RequestEditor
      initial={BLANK_FORM}
      items={[item('1', 'Mic', 'Microphone')]}
      support={false}
      onSave={onSave}
    />,
  )

  await user.click(screen.getByRole('button', { name: 'Request equipment' }))

  expect(screen.getByRole('alert')).toHaveTextContent(
    'Choose an item from the equipment catalogue.',
  )
  expect(onSave).not.toHaveBeenCalled()
})

it('the editor sends the start time typed', async () => {
  const user = userEvent.setup()
  const onSave = vi.fn(async () => {})
  render(
    <RequestEditor
      initial={{ ...BLANK_FORM, equipmentId: '1', equipmentType: 'Microphone' }}
      items={[item('1', 'Mic', 'Microphone')]}
      support={false}
      onSave={onSave}
    />,
  )

  await user.clear(screen.getByLabelText('Needed from'))
  await user.type(screen.getByLabelText('Needed from'), '2027-11-02T10:00')
  await user.click(screen.getByRole('button', { name: 'Request equipment' }))

  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ startsAt: '2027-11-02T10:00' }))
})
