import { useState, type FormEvent } from 'react'
import './SignInPage.css'
import { AuthError, login, previewSession, type Session } from '../api'
import { navigate } from '../router'

type SignInPageProps = {
  onSignedIn: (session: Session) => void
}

type FieldErrors = {
  email?: string
  password?: string
}

function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {}

  if (!email.trim()) {
    errors.email = 'Enter your email address.'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Enter a valid email address.'
  }

  if (!password) {
    errors.password = 'Enter your password.'
  }

  return errors
}

export default function SignInPage({ onSignedIn }: SignInPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState('')
  const [offerPreview, setOfferPreview] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  function completeSignIn(session: Session) {
    onSignedIn(session)
    navigate('/events')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    setOfferPreview(false)

    const errors = validate(email, password)
    setFieldErrors(errors)
    if (errors.email || errors.password) {
      return
    }

    setSubmitting(true)
    try {
      completeSignIn(await login({ email, password }))
    } catch (error) {
      // Anything that is not an explicit rejection is a connectivity or server
      // problem, and saying so is more useful than "login failed".
      if (error instanceof AuthError) {
        setFormError(error.message)
      } else {
        setFormError('Could not reach the server. The backend has no sign-in route yet.')
        setOfferPreview(true)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page signin-page">
      <div className="signin-card card">
        <div className="signin-head">
          <h2>Sign in</h2>
          <p className="muted">Welcome back. Pick up where your events left off.</p>
        </div>

        <form className="signin-form" onSubmit={handleSubmit} noValidate>
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
              disabled={submitting}
            />
            {fieldErrors.email && (
              <span className="field-error" id="email-error">
                {fieldErrors.email}
              </span>
            )}
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'password-error' : undefined}
              disabled={submitting}
            />
            {fieldErrors.password && (
              <span className="field-error" id="password-error">
                {fieldErrors.password}
              </span>
            )}
          </div>

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {offerPreview && (
          <div className="signin-preview">
            <p className="muted">
              Auth is not built yet. You can continue without it to work on the Sprint 1 event
              screens.
            </p>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => completeSignIn(previewSession())}
            >
              Continue without signing in
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
