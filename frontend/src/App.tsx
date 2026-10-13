import { useCallback, useEffect, useState } from 'react'
import './App.css'
import TopNav from './components/TopNav'
import AccessDeniedPage from './pages/AccessDeniedPage'
import EventDetailPage from './pages/EventDetailPage'
import EventsPage from './pages/EventsPage'
import LandingPage from './pages/LandingPage'
import NewEventPage from './pages/NewEventPage'
import NotificationsPage from './pages/NotificationsPage'
import { EquipmentPage, EquipmentDetailPage, EquipmentFormPage } from './pages/EquipmentPage'
import EquipmentQueuePage from './pages/EquipmentQueuePage'
import SafetyReviewPage from './pages/SafetyReviewPage'
import SignInPage from './pages/SignInPage'
import UnassignedQueuePage from './pages/UnassignedQueuePage'
import VenueDetailPage from './pages/VenueDetailPage'
import VenueFormPage from './pages/VenueFormPage'
import VenuesPage from './pages/VenuesPage'
import {
  matchEventDetail,
  matchVenueDetail,
  matchVenueEdit,
  navigate,
  useRoute,
  useScrollToTopOnRouteChange,
} from './router'
import { canOpen } from './permissions'
import { clearStoredSession, loadStoredSession, storeSession } from './session'
import { useIdleSignOut } from './useIdleSignOut'
import { fetchHealth, fetchMe, logout, SessionExpiredError, type Session } from './api'

type Backend = 'checking' | 'connected' | 'unreachable'

/** Public routes. Everything else needs a session. */
const OPEN_ROUTES = new Set(['/', '/signin'])

export default function App() {
  const [backend, setBackend] = useState<Backend>('checking')
  // Seeded from storage during the first render rather than in an effect, so
  // the header shows the signed-in user in the very first frame and there is no
  // signed-out flash on every reload.
  const [session, setSession] = useState<Session | null>(loadStoredSession)
  const [restoring, setRestoring] = useState(session !== null)
  const [notice, setNotice] = useState('')
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

  /*
   * Revive a stored session, but only on the server's say-so.
   *
   * The stored copy is shown straight away so the header does not flicker, then
   * the token is put to the server for confirmation. A session signed out on
   * another device, or one that lapsed while the tab was shut, fails that check
   * and is dropped here — which is what US1.2's "subsequent requests require
   * re-authentication" amounts to once a token can outlive the page.
   * It also re-reads the role each load, so a role change lands without
   * waiting for the user to sign in again.
   */
  useEffect(() => {
    const stored = loadStoredSession()
    if (!stored) return

    let cancelled = false

    fetchMe(stored.token)
      .then((fresh) => {
        if (cancelled) return
        setSession(fresh)
        storeSession(fresh)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSession(null)
        clearStoredSession()
        if (error instanceof SessionExpiredError) {
          setNotice(error.message)
        }
        // Anything else — a revoked token, an unreachable API — leaves the user
        // signed out without an explanation they did not ask for.
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const signOut = useCallback(
    (reason: 'manual' | 'idle' = 'manual') => {
      // US1.2: tell the server, so the token stops working everywhere rather
      // than only in this tab. `logout` never rejects, so nothing is awaited —
      // the session is cleared here whether or not the server heard about it.
      if (session) void logout(session.token)

      if (reason === 'idle') {
        setNotice(`You were signed out after ${session?.idleMinutes ?? 30} minutes of inactivity.`)
      }

      setSession(null)
      clearStoredSession()
      // An idle sign-out lands on the form, where the reason is waiting; a
      // deliberate one lands on the landing page, because leaving was the point.
      navigate(reason === 'idle' ? '/signin' : '/')
    },
    [session],
  )

  // US1.1: the session lapses after a period of inactivity, on both ends.
  useIdleSignOut(session ? session.idleMinutes : null, () => signOut('idle'))

  const handleSignedIn = useCallback((next: Session) => {
    setNotice('')
    setSession(next)
    storeSession(next)
  }, [])

  // A signed-in user has no business on the sign-in form; send them to the view
  // their role actually works from.
  useEffect(() => {
    if (session && route === '/signin') navigate(session.home)
  }, [session, route])

  return (
    <>
      <TopNav route={route} session={session} onSignOut={() => signOut('manual')} />
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
      return <LandingPage session={session} />
    }

    if (route === '/signin') {
      return <SignInPage onSignedIn={handleSignedIn} notice={notice} />
    }

    if (!OPEN_ROUTES.has(route)) {
      // Deciding before the stored token has been checked would sign the user
      // out on every reload for as long as that request takes.
      if (restoring) {
        return (
          <div className="page shell">
            <div className="card empty" role="status">
              <p>Restoring your session…</p>
            </div>
          </div>
        )
      }

      if (!session) {
        return <SignInPage onSignedIn={handleSignedIn} notice={notice} />
      }

      // US1.3: the role is checked before the page is built, so a blocked page
      // never renders a frame of the data it was guarding.
      if (!canOpen(session, route)) {
        return <AccessDeniedPage session={session} route={route} />
      }
    }

    if (!session) {
      return <SignInPage onSignedIn={handleSignedIn} notice={notice} />
    }

    if (route === '/events') {
      return <EventsPage session={session} />
    }

    if (route === '/events/new') {
      return <NewEventPage session={session} />
    }

    if (route === '/notifications') {
      return <NotificationsPage session={session} />
    }

    if (route === '/equipment') return <EquipmentPage session={session} />
    if (route === '/equipment/new') return <EquipmentFormPage session={session} />
    const equipmentEdit = /^\/equipment\/([^/]+)\/edit$/.exec(route)
    if (equipmentEdit) return <EquipmentFormPage session={session} id={equipmentEdit[1]} />
    const equipmentDetail = /^\/equipment\/([^/]+)$/.exec(route)
    if (equipmentDetail) return <EquipmentDetailPage session={session} id={equipmentDetail[1]} />
    if (route === '/equipment-requests') return <EquipmentQueuePage session={session} />
    const queueFocus = /^\/equipment-requests\/([^/]+)$/.exec(route)
    if (queueFocus) return <EquipmentQueuePage session={session} focusId={queueFocus[1]} />

    if (route === '/venues') {
      return <VenuesPage session={session} />
    }

    if (route === '/venues/new') {
      return <VenueFormPage venueId={null} session={session} />
    }

    if (route === '/unassigned-queue') {
      return <UnassignedQueuePage session={session} />
    }

    if (route === '/safety-review') {
      return <SafetyReviewPage session={session} />
    }

    const eventId = matchEventDetail(route)
    if (eventId) {
      return <EventDetailPage eventId={eventId} session={session} />
    }

    // Before the detail route, which would otherwise match "/venues/7/edit"
    // as nothing at all and fall through to the not-found page.
    const editingVenueId = matchVenueEdit(route)
    if (editingVenueId) {
      return <VenueFormPage venueId={editingVenueId} session={session} />
    }

    const venueId = matchVenueDetail(route)
    if (venueId) {
      return <VenueDetailPage venueId={venueId} session={session} />
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
