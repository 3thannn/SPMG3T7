import { useState, type FormEvent } from 'react'
import './LoginForm.css'
import { AuthError, login, type Session } from './api'

type LoginFormProps = {
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

export default function LoginForm({ onSignedIn }: LoginFormProps) {
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
      onSignedIn(await login({ email, password }))
    } catch (error) {
      // Anything that is not an explicit rejection is a connectivity or server
      // problem, and saying so is more useful than "login failed".
      setFormError(
        error instanceof AuthError
          ? error.message
          : 'Could not reach the server. Check your connection and try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="login" onSubmit={handleSubmit} noValidate>
      <h2>Sign in</h2>

      {formError && (
        <p className="login-error" role="alert">
          {formError}
        </p>
      )}

      <div className="login-field">
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
          <span className="login-field-error" id="email-error">
            {fieldErrors.email}
          </span>
        )}
      </div>

      <div className="login-field">
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
          <span className="login-field-error" id="password-error">
            {fieldErrors.password}
          </span>
        )}
      </div>

      <button type="submit" disabled={submitting}>
        {submitting ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}
