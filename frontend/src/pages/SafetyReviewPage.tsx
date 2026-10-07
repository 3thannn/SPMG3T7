import type { Session } from '../api'

interface Props {
  session: Session
}

/**
 * US1.4: Safety Officer's landing page - safety review queue.
 *
 * Placeholder for Sprint 4. Full implementation (US17.1) will show events
 * awaiting Operational Safety Check.
 */
export default function SafetyReviewPage({ session }: Props) {
  return (
    <div className="page shell">
      <div className="card">
        <h2>Safety Review Queue</h2>
        <p>Welcome, {session.name}.</p>
        <p>
          This is the Safety Officer's landing page. The full safety review queue
          (US17.1) will be implemented in Sprint 4.
        </p>
        <p>
          <strong>What will be here (Sprint 4):</strong>
        </p>
        <ul>
          <li>Events awaiting Operational Safety Check</li>
          <li>Ability to approve, reject, or request changes for each event</li>
          <li>Safety checklist: attendance vs capacity, emergency access, accessibility, equipment placement</li>
        </ul>
      </div>
    </div>
  )
}
