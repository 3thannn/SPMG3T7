import { useEffect, useState } from 'react'
import './App.css'
import { fetchHealth } from './api'

type Status = 'checking' | 'connected' | 'unreachable'

export default function App() {
  const [status, setStatus] = useState<Status>('checking')

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
      <p>Frontend is running.</p>
      <p role="status">
        {status === 'checking' && 'Checking backend…'}
        {status === 'connected' && 'Backend online'}
        {status === 'unreachable' && 'Backend unreachable'}
      </p>
    </main>
  )
}
