import './TopNav.css'
import { navigate } from '../router'
import { canOpen } from '../permissions'
import type { Session } from '../api'

type TopNavProps = {
  route: string
  session: Session | null
  onSignOut: () => void
}

type NavLink = { label: string; path: string }

/**
 * Every section the app has, in the order they are offered. `linksFor` drops the
 * ones this role cannot open, so a link appearing here does not mean everyone
 * sees it — Create is an Organiser's, Venues a Coordinator's and Venue Staff's
 * (US9.2), and Add venue only Venue Staff's (US9.1a).
 */
const NAV_LINKS: NavLink[] = [
  { label: 'Events', path: '/events' },
  { label: 'Create', path: '/events/new' },
  { label: 'Unassigned Queue', path: '/unassigned-queue' },
  { label: 'Safety Review', path: '/safety-review' },
  { label: 'Venues', path: '/venues' },
  { label: 'Add venue', path: '/venues/new' },
]

/**
 * US1.3: the rail only offers what this role may open.
 *
 * Hiding a link is a courtesy rather than a control — the route guard and the
 * API both refuse regardless — but leading someone to a page that will turn
 * them away is a poor way to tell them what their role is for.
 */
function linksFor(session: Session): NavLink[] {
  return NAV_LINKS.filter((link) => canOpen(session, link.path))
}

function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?'
}

export default function TopNav({ route, session, onSignOut }: TopNavProps) {
  return (
    <header className="topnav">
      <div className="shell topnav-inner">
        <a
          className="topnav-brand"
          href="#/"
          onClick={(event) => {
            event.preventDefault()
            navigate('/')
          }}
        >
          <span className="topnav-wordmark">
            Event<span className="topnav-wordmark-tail">Hub</span>
          </span>
        </a>

        {session && linksFor(session).length > 0 && (
          /* A segmented rail rather than loose text links — the active section
             sits in a raised pill, so where you are is legible at a glance. */
          <nav className="topnav-rail" aria-label="Main">
            {linksFor(session).map((link) => (
              <a
                key={link.path}
                href={`#${link.path}`}
                className={route === link.path ? 'is-active' : undefined}
                aria-current={route === link.path ? 'page' : undefined}
                onClick={(event) => {
                  event.preventDefault()
                  navigate(link.path)
                }}
              >
                {link.label}
              </a>
            ))}
          </nav>
        )}

        <div className="topnav-end">
          {session ? (
            <>
              <span className="topnav-identity">
                <span className="topnav-name">{session.name}</span>
                <span className="topnav-role">{session.role}</span>
              </span>
              <span className="topnav-avatar" title={session.name}>
                {initial(session.name)}
              </span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onSignOut}>
                Sign out
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => navigate('/signin')}
            >
              Sign in
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
