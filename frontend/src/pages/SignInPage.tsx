import { useState, type FormEvent } from 'react'
import './SignInPage.css'
import { AuthError, login, type Session } from '../api'
import { navigate } from '../router'

type SignInPageProps = {
  onSignedIn: (session: Session) => void
  /** Why the user is looking at this page — an expired session, a sign-out. */
  notice?: string
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

export default function SignInPage({ onSignedIn, notice }: SignInPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')

    const errors = validate(email, password)
    setFieldErrors(errors)
    if (errors.email || errors.password) {
      return
    }

    setSubmitting(true)
    try {
      const session = await login({ email, password })
      onSignedIn(session)
      // US1.1: the server decides which view suits the role, not this page.
      navigate(session.home)
    } catch (error) {
      // A rejected credential and an unreachable server are different problems
      // with different fixes, so they never share a message. Telling someone
      // their password is wrong when the API is down sends them to reset a
      // password that was fine.
      if (error instanceof AuthError) {
        setFormError(error.message)
      } else if (error instanceof Error && error.name === 'TypeError') {
        setFormError('Could not reach the server. Check that the API is running, then try again.')
      } else {
        setFormError(
          error instanceof Error ? error.message : 'Something went wrong. Try again.',
        )
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

        {notice && (
          <p className="signin-notice" role="status">
            {notice}
          </p>
        )}

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
      </div>
    </div>
  )
}
