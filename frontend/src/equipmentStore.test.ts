/** US19: the equipment client — what each call sends, and the helpers the pages share. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  createEquipmentRequest,
  decideEquipmentRequest,
  deleteEquipment,
  equipmentErrorMessage,
  formatEquipmentTimes,
  getEquipment,
  getEquipmentAvailability,
  getEquipmentRequest,
  listEquipment,
  listEquipmentQueue,
  listEventEquipmentHistory,
  listEventEquipmentRequests,
  removeEquipmentRequest,
  saveEquipment,
  updateEquipmentRequest,
  valuesFor,
  type EquipmentInput,
  type EquipmentRequest,
} from './equipmentStore'
import { ok, sent, stubFetch } from './test/fetch'
import { buildSession } from './test/sessions'

afterEach(() => {
  vi.unstubAllGlobals()
})

const tech = buildSession({ role: 'Technical Support', token: 'session-token' })

const ITEM: EquipmentInput = {
  name: 'Wireless microphone',
  type: 'Microphone',
  description: 'UHF',
  location: 'AV Store',
  totalQuantity: 5,
  outOfServiceQuantity: 1,
  outOfServiceReason: 'Battery damage',
}

const REQUEST: EquipmentRequest = {
  id: '30',
  eventId: '7',
  eventTitle: 'Open Day',
  equipmentType: 'Microphone',
  quantity: 2,
  technicalRequirements: 'Two channels',
  supportNotes: '',
  startsAt: '2027-11-02T09:00:00',
  endsAt: '2027-11-02T17:00:00',
  status: 'Requested',
  requestedEquipmentId: '5',
  createdAt: '2026-10-01T09:00:00',
  version: 1,
}

describe('the equipment calls', () => {
  it.each([
    ['lists the catalogue', () => listEquipment(tech), '/equipment', 'GET'],
    ['reads one item', () => getEquipment('5', tech), '/equipment/5', 'GET'],
    ['adds an item', () => saveEquipment(ITEM, tech), '/equipment', 'POST'],
    ['updates an item', () => saveEquipment(ITEM, tech, '5'), '/equipment/5', 'PUT'],
    ['deletes an item', () => deleteEquipment('5', tech), '/equipment/5', 'DELETE'],
    [
      "lists an event's lines, removed ones included",
      () => listEventEquipmentRequests('7', tech),
      '/events/7/equipment-requests?includeRemoved=true',
      'GET',
    ],
    [
      "reads an event's history",
      () => listEventEquipmentHistory('7', tech),
      '/events/7/equipment-history',
      'GET',
    ],
    ['reads the queue', () => listEquipmentQueue(tech), '/equipment-requests', 'GET'],
    ['reads one request', () => getEquipmentRequest('30', tech), '/equipment-requests/30', 'GET'],
    [
      "reads a request's availability",
      () => getEquipmentAvailability('30', tech),
      '/equipment-requests/30/availability',
      'GET',
    ],
    [
      'removes a request at the version it was read at',
      () => removeEquipmentRequest('30', 3, tech),
      '/equipment-requests/30?version=3',
      'DELETE',
    ],
  ])('%s', async (_name, call, path, method) => {
    const spy = stubFetch(ok([]))

    await call()

    expect(sent(spy)).toMatchObject({ path, method })
    expect(spy.mock.calls[0][1].headers.Authorization).toBe('Bearer session-token')
  })

  it('sends a new item as it was typed', async () => {
    const spy = stubFetch(ok({ id: '5', ...ITEM, usableQuantity: 4 }))

    const saved = await saveEquipment(ITEM, tech)

    expect(sent(spy).body).toEqual(ITEM)
    expect(saved.usableQuantity).toBe(4)
  })

  it('creates a request on its event', async () => {
    const spy = stubFetch(ok(REQUEST, 201))

    await createEquipmentRequest('7', { equipmentId: 5, quantity: 2 }, tech)

    expect(sent(spy)).toEqual({
      path: '/events/7/equipment-requests',
      method: 'POST',
      body: { equipmentId: 5, quantity: 2 },
    })
  })

  it('patches only the fields that changed', async () => {
    const spy = stubFetch(ok(REQUEST))

    await updateEquipmentRequest('30', { version: 1, quantity: 3 }, tech)

    expect(sent(spy)).toEqual({
      path: '/equipment-requests/30',
      method: 'PATCH',
      body: { version: 1, quantity: 3 },
    })
  })

  it('reserves a named item', async () => {
    const spy = stubFetch(ok(REQUEST))

    await decideEquipmentRequest('30', 1, { equipmentId: 5 }, tech)

    expect(sent(spy)).toEqual({
      path: '/equipment-requests/30/reserve',
      method: 'POST',
      body: { version: 1, equipmentId: 5 },
    })
  })

  it('marks a request unavailable with its reason', async () => {
    const spy = stubFetch(ok(REQUEST))

    await decideEquipmentRequest('30', 1, { reason: 'All out for repair' }, tech)

    expect(sent(spy)).toEqual({
      path: '/equipment-requests/30/unavailable',
      method: 'POST',
      body: { version: 1, reason: 'All out for repair' },
    })
  })
})

describe('the shared helpers', () => {
  it('reads times without an offset as Singapore time', () => {
    expect(formatEquipmentTimes('2027-11-02T09:00', '2027-11-02T17:00')).toBe(
      formatEquipmentTimes('2027-11-02T09:00+08:00', '2027-11-02T17:00+08:00'),
    )
  })

  it('keeps an offset the server already sent', () => {
    expect(formatEquipmentTimes('2027-11-02T01:00Z', '2027-11-02T09:00Z')).toBe(
      formatEquipmentTimes('2027-11-02T09:00+08:00', '2027-11-02T17:00+08:00'),
    )
  })

  it('shows a refusal as the server worded it', () => {
    expect(equipmentErrorMessage(new ApiError('No stock left.', 'insufficient_stock', 409), 'reserve')).toBe(
      'No stock left.',
    )
  })

  it('describes anything else as a failure to reach the API', () => {
    expect(equipmentErrorMessage(new TypeError('Failed to fetch'), 'reserve this')).toBe(
      'Could not reserve this. The API could not be reached; check it is running and try again.',
    )
  })

  it("fills the edit form from a request, trimmed to the inputs' minutes", () => {
    expect(valuesFor(REQUEST)).toEqual({
      equipmentId: '5',
      equipmentType: 'Microphone',
      quantity: '2',
      technicalRequirements: 'Two channels',
      supportNotes: '',
      startsAt: '2027-11-02T09:00',
      endsAt: '2027-11-02T17:00',
    })
  })

  it('leaves the item empty on a request from before exact items', () => {
    expect(valuesFor({ ...REQUEST, requestedEquipmentId: null }).equipmentId).toBe('')
  })
})
