import type { Session } from '../api'

interface Props {
  session: Session
}

/**
 * US8.2: Coordinator Lead's landing page - unassigned event queue.
 *
 * Placeholder for now. Full implementation will show Submitted events with no
 * assigned Coordinator, oldest first, with ability to assign (US8.3).
 */
export default function UnassignedQueuePage({ session }: Props) {
  return (
    <div className="page shell">
      <div className="card">
        <h2>Unassigned Event Queue</h2>
        <p>Welcome, {session.name}.</p>
        <p>
          This is the Coordinator Lead's landing page. The full unassigned queue
          (US8.2) and assignment UI (US8.3) are under construction.
        </p>
        <p>
          <strong>What will be here:</strong>
        </p>
        <ul>
          <li>List of Submitted events with no assigned Coordinator</li>
          <li>Events shown oldest first</li>
          <li>For each event: name, proposed date, attendance, Organiser, submitted time</li>
          <li>Ability to assign a Coordinator to each event</li>
        </ul>
      </div>
    </div>
  )
}
