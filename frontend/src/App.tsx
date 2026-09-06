import { useEffect, useState } from 'react'
import './App.css'
import TopNav from './components/TopNav'
import EventDetailPage from './pages/EventDetailPage'
import EventsPage from './pages/EventsPage'
import LandingPage from './pages/LandingPage'
import NewEventPage from './pages/NewEventPage'
import SignInPage from './pages/SignInPage'
import { matchEventDetail, navigate, useRoute, useScrollToTopOnRouteChange } from './router'
import { fetchHealth, type Session } from './api'

type Backend = 'checking' | 'connected' | 'unreachable'

export default function App() {
  const [backend, setBackend] = useState<Backend>('checking')
  const [session, setSession] = useState<Session | null>(null)
  const route = useRoute()

  useScrollToTopOnRouteChange(route)

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then(() => {
        if (!cancelled) setBackend('connected')
      })
      .catch(() => {
        if (!cancelled) setBackend('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleSignOut() {
    setSession(null)
    navigate('/')
  }

  return (
    <>
      <TopNav route={route} session={session} onSignOut={handleSignOut} />
      {renderRoute()}
      <footer className="app-footer">
        <div className="shell app-footer-inner">
          <span>SPMG3T7 · Sprint 1</span>
          <span role="status" className="app-health" data-state={backend}>
            {backend === 'checking' && 'Checking backend…'}
            {backend === 'connected' && 'Backend connected'}
            {backend === 'unreachable' && 'Backend unreachable'}
          </span>
        </div>
      </footer>
    </>
  )

  function renderRoute() {
    if (route === '/') {
      return <LandingPage session={session} backend={backend} />
    }

    if (route === '/signin') {
      return <SignInPage onSignedIn={setSession} />
    }

    // Everything below needs a session; send anonymous visitors to sign in
    // rather than rendering an empty shell.
    if (!session) {
      return <SignInPage onSignedIn={setSession} />
    }

    if (route === '/events') {
      return <EventsPage session={session} />
    }

    if (route === '/events/new') {
      return <NewEventPage session={session} />
    }

    const eventId = matchEventDetail(route)
    if (eventId) {
      return <EventDetailPage eventId={eventId} session={session} />
    }

    return (
      <div className="page shell">
        <div className="card empty">
          <h3>Page not found</h3>
          <p>Nothing lives at {route}.</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate('/')}
            style={{ marginTop: '1.25rem' }}
          >
            Back home
          </button>
        </div>
      </div>
    )
  }
}
