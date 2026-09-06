import './TopNav.css'
import { navigate } from '../router'
import type { Session } from '../api'

type TopNavProps = {
  route: string
  session: Session | null
  onSignOut: () => void
}

const LINKS: { label: string; path: string }[] = [
  { label: 'Events', path: '/events' },
  { label: 'Create', path: '/events/new' },
]

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

        {session && (
          /* A segmented rail rather than loose text links — the active section
             sits in a raised pill, so where you are is legible at a glance. */
          <nav className="topnav-rail" aria-label="Main">
            {LINKS.map((link) => (
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
