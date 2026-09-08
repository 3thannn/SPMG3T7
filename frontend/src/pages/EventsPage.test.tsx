import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'
import EventsPage from './EventsPage'
import { __resetStore, createEvent } from '../eventsStore'
import { buildSession } from '../test/sessions'

const organiser = buildSession({ role: 'Organiser', id: 'user_1', name: 'Dylan' })

const coordinator = buildSession({
  role: 'Coordinator',
  id: 'user_9',
  name: 'Ethan',
  email: 'ethan@example.edu',
})

const draft = { title: 'Mine', description: '', startsAt: '', location: 'Hall' }

beforeEach(() => {
  __resetStore([])
})

it('shows a status badge on every event in the list', async () => {
  await createEvent(draft, { id: 'user_1', name: 'Dylan' })

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('Mine')).toBeInTheDocument()
  expect(screen.getByText('Draft')).toBeInTheDocument()
})

it('limits an Organiser to the events they own', async () => {
  await createEvent(draft, { id: 'user_1', name: 'Dylan' })
  await createEvent({ ...draft, title: 'Theirs' }, { id: 'user_2', name: 'Ariel' })

  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('Mine')).toBeInTheDocument()
  expect(screen.queryByText('Theirs')).not.toBeInTheDocument()
})

it('shows a Coordinator every event, with its organiser named', async () => {
  await createEvent(draft, { id: 'user_1', name: 'Dylan' })
  await createEvent({ ...draft, title: 'Theirs' }, { id: 'user_2', name: 'Ariel' })

  render(<EventsPage session={coordinator} />)

  expect(await screen.findByText('Mine')).toBeInTheDocument()
  expect(screen.getByText('Theirs')).toBeInTheDocument()
  expect(screen.getByText(/Organiser: Ariel/)).toBeInTheDocument()
})

it('tells an Organiser with no events what to do next', async () => {
  render(<EventsPage session={organiser} />)

  expect(await screen.findByText('No events yet')).toBeInTheDocument()
})
