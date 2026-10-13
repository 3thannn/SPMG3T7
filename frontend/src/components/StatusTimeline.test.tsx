import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import StatusTimeline from './StatusTimeline'
import type { EquipmentHistoryEntry } from '../equipmentStore'
import type { StatusChange } from '../status'

const status: StatusChange[] = [
  { from: null, to: 'Draft', at: '2026-10-13T09:00:00', byId: '1', byName: 'Dylan' },
  { from: 'Draft', to: 'Submitted', at: '2026-10-13T10:00:00', byId: '1', byName: 'Dylan' },
  { from: 'Approved', to: 'Planning', at: '2026-10-13T11:00:00', byId: '2', byName: 'Priya' },
]
const before = {
  equipment_type: 'Microphone', quantity: 1, technical_requirements: 'Two channels',
  support_notes: '', start_at: '2027-11-02T09:00', end_at: '2027-11-02T17:00',
}
const equipment: EquipmentHistoryEntry[] = [
  { id: '3', requestId: '5', action: 'Removed', at: '2026-10-13T14:00:00', byName: 'Priya', before: { ...before, quantity: 2 }, after: null },
  { id: '2', requestId: '5', action: 'Updated', at: '2026-10-13T13:00:00', byName: 'Bryan', before, after: { ...before, quantity: 2, support_notes: 'Tested' } },
  { id: '1', requestId: '5', action: 'Created', at: '2026-10-13T12:00:00', byName: 'Priya', before: null, after: before },
]

it('keeps one oldest-first timeline from Draft through request removal', () => {
  const { container } = render(<StatusTimeline history={status} equipmentHistory={equipment} />)
  const entries = [...container.querySelectorAll('ol.timeline > li')]
  expect(entries).toHaveLength(6)
  expect(entries[0]).toHaveTextContent('Created as')
  expect(entries[0]).toHaveTextContent('Status: Draft')
  expect(entries[1]).toHaveTextContent('Submitted')
  expect(entries[2]).toHaveTextContent('Planning')
  expect(entries[3]).toHaveTextContent('Created Microphone request')
  expect(entries[4]).toHaveTextContent('Updated Microphone request')
  expect(entries[5]).toHaveTextContent('Removed Microphone request')
  expect(screen.getByText('Quantity: 1 → 2')).toBeInTheDocument()
  expect(screen.getByText('Arrangement notes: None → Tested')).toBeInTheDocument()
  expect(entries[4]).toHaveTextContent('Bryan')
})
