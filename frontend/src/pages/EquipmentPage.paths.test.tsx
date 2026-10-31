/**
 * US19 catalogue pages: the failures and form paths EquipmentPage.test.tsx does
 * not reach. A load or save that fails says what could not be done, an answer
 * that lands after the page has gone changes nothing, and the out-of-service
 * rule is checked before anything is sent.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EquipmentDetailPage, EquipmentFormPage, EquipmentPage } from './EquipmentPage'
import { getEquipment, listEquipment, saveEquipment, type Equipment } from '../equipmentStore'
import { ApiError } from '../api'
import { buildSession } from '../test/sessions'

vi.mock('../equipmentStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../equipmentStore')>()),
  listEquipment: vi.fn(),
  saveEquipment: vi.fn(),
  getEquipment: vi.fn(),
  deleteEquipment: vi.fn(),
}))

const list = vi.mocked(listEquipment)
const save = vi.mocked(saveEquipment)
const get = vi.mocked(getEquipment)
const support = buildSession({ role: 'Technical Support' })

const PROJECTOR: Equipment = {
  id: '1',
  name: 'Projector',
  type: 'Projector',
  description: 'Short throw',
  location: 'AV Store',
  totalQuantity: 4,
  outOfServiceQuantity: 0,
  outOfServiceReason: '',
  usableQuantity: 4,
}

const UNREACHABLE = new TypeError('Failed to fetch')

afterEach(() => {
  window.location.hash = ''
  vi.resetAllMocks()
})

describe('loading', () => {
  it('the catalogue says when it could not be loaded', async () => {
    list.mockRejectedValue(UNREACHABLE)
    render(<EquipmentPage session={support} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load equipment.')
  })

  it("one item shows the server's reason when it could not be loaded", async () => {
    get.mockRejectedValue(new ApiError('That item does not exist.', 'unknown', 404))
    render(<EquipmentDetailPage session={support} id="1" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('That item does not exist.')
  })

  it('the edit form says when the item could not be loaded', async () => {
    get.mockRejectedValue(UNREACHABLE)
    render(<EquipmentFormPage session={support} id="1" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load equipment.')
  })

  it('the catalogue ignores a failure that lands after the page has gone', async () => {
    let fail!: (error: Error) => void
    list.mockReturnValueOnce(new Promise((_resolve, reject) => (fail = reject)))
    const { unmount } = render(<EquipmentPage session={support} />)

    unmount()
    fail(UNREACHABLE)
    await Promise.resolve()

    expect(list).toHaveBeenCalledTimes(1)
  })

  it.each(['arrives', 'fails'])('one item ignores an answer that %s after the page has gone', async (outcome) => {
    let deliver!: (item: Equipment) => void
    let fail!: (error: Error) => void
    get.mockReturnValueOnce(new Promise((resolve, reject) => ((deliver = resolve), (fail = reject))))
    const { unmount } = render(<EquipmentDetailPage session={support} id="1" />)

    unmount()
    if (outcome === 'arrives') deliver(PROJECTOR)
    else fail(UNREACHABLE)
    await Promise.resolve()

    expect(get).toHaveBeenCalledTimes(1)
  })
})

describe('the edit form', () => {
  it('fills from the item and saves it back to the same id', async () => {
    const user = userEvent.setup()
    get.mockResolvedValue(PROJECTOR)
    save.mockResolvedValue(PROJECTOR)
    render(<EquipmentFormPage session={support} id="1" />)
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Projector'))

    await user.clear(screen.getByLabelText('Description'))
    await user.type(screen.getByLabelText('Description'), 'Long throw')
    await user.click(screen.getByRole('button', { name: 'Save equipment' }))

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Projector', description: 'Long throw' }),
      support,
      '1',
    )
    await waitFor(() => expect(window.location.hash).toBe('#/equipment'))
  })

  it('asks for a reason before any units are put out of service', async () => {
    const user = userEvent.setup()
    get.mockResolvedValue(PROJECTOR)
    render(<EquipmentFormPage session={support} id="1" />)
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Projector'))

    await user.clear(screen.getByLabelText('Out-of-service quantity'))
    await user.type(screen.getByLabelText('Out-of-service quantity'), '1')
    await user.click(screen.getByRole('button', { name: 'Save equipment' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Give a reason for out-of-service units.',
    )
    expect(save).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('Out-of-service reason'), 'Lamp blown')
    save.mockResolvedValue(PROJECTOR)
    await user.click(screen.getByRole('button', { name: 'Save equipment' }))

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ outOfServiceQuantity: 1, outOfServiceReason: 'Lamp blown' }),
      support,
      '1',
    )
  })

  it('says a save failed and stays on the form', async () => {
    const user = userEvent.setup()
    get.mockResolvedValue(PROJECTOR)
    save.mockRejectedValue(new ApiError('A projector with that name exists.', 'rule_refused', 409))
    render(<EquipmentFormPage session={support} id="1" />)
    await waitFor(() => expect(screen.getByLabelText('Name')).toHaveValue('Projector'))

    await user.click(screen.getByRole('button', { name: 'Save equipment' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A projector with that name exists.')
    expect(window.location.hash).toBe('')
  })
})
