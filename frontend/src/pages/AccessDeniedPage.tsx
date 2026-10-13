import './AccessDeniedPage.css'
import type { Session } from '../api'
import { denialMessage } from '../permissions'
import { navigate } from '../router'

type AccessDeniedPageProps = {
  session: Session
  route: string
}

/**
 * US1.3: what a blocked page looks like.
 *
 * The point of the page is the second paragraph. Being told "no" is not useful
 * on its own — the user needs to know it was their role that was refused rather
 * than a broken link, that signing in again will not change it, and where they
 * can actually go. So the message names the role, names what it could not open,
 * and the button leads to the view that role does have.
 */
export default function AccessDeniedPage({ session, route }: AccessDeniedPageProps) {
  return (
    <div className="page shell access-denied">
      <div className="card card-pad access-denied-card">
        <p className="access-denied-eyebrow">Access denied</p>
        <h2 className="access-denied-title">This page is not open to your role</h2>

        <p className="access-denied-message" role="alert">
          {denialMessage(session, route)}
        </p>

        <div className="access-denied-actions">
          <button type="button" className="btn btn-primary" onClick={() => navigate(session.home)}>
            Go to my dashboard
          </button>
          <code className="access-denied-route">{route}</code>
        </div>
      </div>
    </div>
  )
}
