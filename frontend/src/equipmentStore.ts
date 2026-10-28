import { ApiError, authorizedFetch, unexpectedFailureMessage, type Session } from './api'
import { formatBookingTimes } from './eventsStore'

/** Equipment windows are naive SGT, independent of the viewer's timezone. */
export function formatEquipmentTimes(start: string, end: string): string {
  const planned = (value: string) => value && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? `${value}+08:00` : value
  return formatBookingTimes(planned(start), planned(end))
}

export function equipmentErrorMessage(error: unknown, action: string): string {
  return error instanceof ApiError ? error.message : unexpectedFailureMessage(error, action)
}

export type Equipment = {
  id: string
  name: string
  type: string
  description: string
  location: string
  totalQuantity: number
  outOfServiceQuantity: number
  outOfServiceReason: string
  usableQuantity: number
}

export type EquipmentInput = Omit<Equipment, 'id' | 'usableQuantity'>

export type EquipmentRequest = {
  id: string
  eventId: string
  eventTitle: string
  equipmentType: string
  quantity: number
  technicalRequirements: string
  supportNotes: string
  startsAt: string
  endsAt: string
  status: 'Requested' | 'Reserved' | 'Unavailable' | 'Removed'
  equipmentId?: string | null
  unavailableReason?: string
  createdAt: string
  version: number
}

export type EquipmentRequestDetail = EquipmentRequest & { removedByName: string }

export type EquipmentAvailability = {
  equipmentId: string
  name: string
  location: string
  totalQuantity: number
  outOfServiceQuantity: number
  reservedQuantity: number
  availableQuantity: number
  shortfall: number
}

export async function getEquipmentAvailability(id: string, session: Session): Promise<EquipmentAvailability[]> {
  return (await (await authorizedFetch(`/equipment-requests/${id}/availability`, session.token)).json()) as EquipmentAvailability[]
}

export async function decideEquipmentRequest(
  id: string, version: number, decision: { equipmentId: number } | { reason: string }, session: Session,
): Promise<EquipmentRequest> {
  const action = 'equipmentId' in decision ? 'reserve' : 'unavailable'
  return (await (await authorizedFetch(`/equipment-requests/${id}/${action}`, session.token, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version, ...decision }),
  })).json()) as EquipmentRequest
}

export type RequestSnapshot = {
  equipment_type: string
  quantity: number
  technical_requirements: string
  support_notes: string
  start_at: string
  end_at: string
}

export type EquipmentHistoryEntry = {
  id: string
  requestId: string
  action: 'Created' | 'Updated' | 'Removed'
  at: string
  byName: string
  before: RequestSnapshot | null
  after: RequestSnapshot | null
}

export type RequestFormValues = {
  equipmentType: string
  quantity: string
  technicalRequirements: string
  supportNotes: string
  startsAt: string
  endsAt: string
}

export function valuesFor(request: EquipmentRequest): RequestFormValues {
  return {
    equipmentType: request.equipmentType,
    quantity: String(request.quantity),
    technicalRequirements: request.technicalRequirements,
    supportNotes: request.supportNotes,
    startsAt: request.startsAt.slice(0, 16),
    endsAt: request.endsAt.slice(0, 16),
  }
}

export async function listEquipment(session: Session): Promise<Equipment[]> {
  return (await (await authorizedFetch('/equipment', session.token)).json()) as Equipment[]
}

export async function getEquipment(id: string, session: Session): Promise<Equipment> {
  return (await (await authorizedFetch(`/equipment/${id}`, session.token)).json()) as Equipment
}

export async function saveEquipment(
  item: EquipmentInput,
  session: Session,
  id?: string,
): Promise<Equipment> {
  const response = await authorizedFetch(id ? `/equipment/${id}` : '/equipment', session.token, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  })
  return (await response.json()) as Equipment
}

export async function deleteEquipment(id: string, session: Session): Promise<void> {
  await authorizedFetch(`/equipment/${id}`, session.token, { method: 'DELETE' })
}

export async function listEventEquipmentRequests(
  eventId: string,
  session: Session,
): Promise<EquipmentRequest[]> {
  const response = await authorizedFetch(`/events/${eventId}/equipment-requests`, session.token)
  return (await response.json()) as EquipmentRequest[]
}

export async function listEventEquipmentHistory(
  eventId: string,
  session: Session,
): Promise<EquipmentHistoryEntry[]> {
  const response = await authorizedFetch(`/events/${eventId}/equipment-history`, session.token)
  return (await response.json()) as EquipmentHistoryEntry[]
}

export async function listEquipmentQueue(session: Session): Promise<EquipmentRequest[]> {
  return (await (await authorizedFetch('/equipment-requests', session.token)).json()) as EquipmentRequest[]
}

export async function getEquipmentRequest(id: string, session: Session): Promise<EquipmentRequestDetail> {
  const response = await authorizedFetch(`/equipment-requests/${id}`, session.token)
  return (await response.json()) as EquipmentRequestDetail
}

export type RequestChanges = {
  version?: number
  equipmentType?: string
  quantity?: number
  technicalRequirements?: string
  supportNotes?: string
  startsAt?: string
  endsAt?: string
}

export async function createEquipmentRequest(
  eventId: string,
  changes: RequestChanges,
  session: Session,
): Promise<EquipmentRequest> {
  const response = await authorizedFetch(`/events/${eventId}/equipment-requests`, session.token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
  return (await response.json()) as EquipmentRequest
}

export async function updateEquipmentRequest(
  id: string,
  changes: RequestChanges,
  session: Session,
): Promise<EquipmentRequest> {
  const response = await authorizedFetch(`/equipment-requests/${id}`, session.token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
  return (await response.json()) as EquipmentRequest
}

export async function removeEquipmentRequest(
  id: string,
  version: number,
  session: Session,
): Promise<void> {
  await authorizedFetch(`/equipment-requests/${id}?version=${version}`, session.token, {
    method: 'DELETE',
  })
}
