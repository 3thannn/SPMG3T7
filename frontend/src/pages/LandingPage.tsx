import './LandingPage.css'
import { navigate } from '../router'
import StatusBadge from '../components/StatusBadge'
import { EVENT_STATUSES } from '../status'
import type { Session } from '../api'

type LandingPageProps = {
  session: Session | null
}

/**
 * The marketing surface.
 *
 * The floating pieces are the things an event actually produces — a date on a
 * calendar, a ticket, a run sheet, a guest list — rather than abstract shapes,
 * so the page says what the product is before anyone reads the heading.
 */
export default function LandingPage({ session }: LandingPageProps) {
  return (
    <div className="landing">
      <section className="landing-hero hero-ground">
        {/* Decorative only — the page reads identically with these removed. */}
        <div className="landing-floaters" aria-hidden="true">
          <article className="floater floater-calendar">
            <span className="cal-month">OCT</span>
            <span className="cal-day">14</span>
            <span className="cal-weekday">Thursday</span>
          </article>

          <article className="floater floater-event">
            <span className="fe-title">Faculty Welcome Night</span>
            <span className="fe-meta">Great Hall · 7:00 PM</span>
            <span className="status-badge status-badge-confirmed status-badge-sm">
              <span className="status-badge-dot" />
              Confirmed
            </span>
          </article>

          <article className="floater floater-ticket">
            <div className="ticket-top">
              <span className="ticket-label">ADMIT ONE</span>
              <span className="ticket-seat">ROW C · 14</span>
            </div>
            <div className="ticket-perf" />
            <div className="ticket-barcode">
              {Array.from({ length: 22 }).map((_, index) => (
                <i key={index} />
              ))}
            </div>
          </article>

          <article className="floater floater-agenda">
            <span className="agenda-head">Run sheet</span>
            {[
              { time: '18:30', width: '72%' },
              { time: '19:00', width: '54%' },
              { time: '20:15', width: '64%' },
            ].map((row) => (
              <span className="agenda-row" key={row.time}>
                <span className="agenda-time">{row.time}</span>
                <span className="agenda-bar" style={{ width: row.width }} />
              </span>
            ))}
          </article>

          <article className="floater floater-guests">
            <div className="guest-avatars">
              {['A', 'M', 'K', 'R'].map((letter) => (
                <span className="guest-avatar" key={letter}>
                  {letter}
                </span>
              ))}
            </div>
            <span className="guest-count">128 going</span>
          </article>
        </div>

        <div className="shell landing-hero-inner">
          <h1>EventHub</h1>

          <p className="landing-lede">
            Plan it, submit it, track it. One place for organisers and coordinators to see
            exactly where every event stands.
          </p>

          <div className="landing-actions">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              // The role's own landing page: an Attendee's events are /attend (US20.1).
              onClick={() => navigate(session ? session.home : '/signin')}
            >
              {session ? 'Go to events' : 'Sign in'} <span aria-hidden="true">→</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-lg"
              onClick={() => navigate(session ? '/events/new' : '/signin')}
            >
              Create an event
            </button>
          </div>
        </div>
      </section>

      <section className="shell landing-statuses">
        <h2>Every stage, one vocabulary</h2>
        <p className="landing-section-lede">
          An event carries the same status label wherever it appears, so nobody has to guess
          what stage means what.
        </p>
        <div className="landing-status-grid">
          {EVENT_STATUSES.map((status) => (
            <StatusBadge key={status} status={status} size="lg" />
          ))}
        </div>
      </section>
    </div>
  )
}
