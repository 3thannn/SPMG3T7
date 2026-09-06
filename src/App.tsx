import { useEffect, useState } from 'react'
import './App.css'
import LoginForm from './LoginForm'
import { fetchHealth, type Session } from './api'

type Status = 'checking' | 'connected' | 'unreachable'

export default function App() {
  const [status, setStatus] = useState<Status>('checking')
  const [session, setSession] = useState<Session | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchHealth()
      .then(() => {
        if (!cancelled) setStatus('connected')
      })
      .catch(() => {
        if (!cancelled) setStatus('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main>
      <h1>SPMG3T7</h1>
      <p role="status">
        {status === 'checking' && 'Checking backend…'}
        {status === 'connected' && 'Backend connected'}
        {status === 'unreachable' && 'Backend unreachable'}
      </p>

      {session ? (
        <div className="session">
          <p>Signed in as {session.email}</p>
          <button type="button" onClick={() => setSession(null)}>
            Sign out
          </button>
        </div>
      ) : (
        <LoginForm onSignedIn={setSession} />
      )}
    </main>
  )
}
