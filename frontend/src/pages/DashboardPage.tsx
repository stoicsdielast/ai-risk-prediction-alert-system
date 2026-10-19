import { Link } from 'react-router-dom'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { usePublicAlerts } from '../alerts/useAlertFeed'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { SyntheticReplayPanel } from '../components/research/SyntheticReplayPanel'

interface DashboardLocationState {
  accessDenied?: string
}

export function DashboardPage() {
  const alerts = usePublicAlerts()
  const { user } = useAuth()
  const location = useLocation()
  const accessDenied = (location.state as DashboardLocationState | null)
    ?.accessDenied

  if (!user) return null

  return (
    <div className="page-stack">
      {accessDenied && <Alert tone="error">{accessDenied}</Alert>}

      <section className="page-heading">
        <div>
          <span className="eyebrow">Secure workspace</span>
          <h1>Bula, {user.name.split(' ')[0]}.</h1>
          <p>Your account is approved and ready for protected system access.</p>
        </div>
        <span className="status-pill status-pill--approved">
          <span /> Approved account
        </span>
      </section>

      <section className="prototype-panel community-alert-card" aria-label="Community alert summary">
        <h2>Active community alerts: {alerts.data && !alerts.error ? alerts.data.length : '–'}</h2>
        <AlertFeedStatus {...alerts} />
        <Link className="button button--primary" to="/alerts">View community alerts</Link>
      </section>

      <SyntheticReplayPanel />

      <section className="identity-grid" aria-label="Account summary">
        <article className="summary-card summary-card--primary">
          <span className="summary-card__label">Signed in as</span>
          <strong>{user.name}</strong>
          <p>{user.email}</p>
        </article>
        <article className="summary-card">
          <span className="summary-card__label">System role</span>
          <strong>{user.role === 'MET_ADMIN' ? 'MET administrator' : 'Community user'}</strong>
          <p>Verified from the live account record</p>
        </article>
        <article className="summary-card">
          <span className="summary-card__label">Authentication</span>
          <strong>Protected session</strong>
          <p>Your access token is checked on every request</p>
        </article>
      </section>

      <section className="admin-callout">
        <div className="admin-callout__mark" aria-hidden="true">W</div>
        <div>
          <span className="eyebrow">Monitoring map</span>
          <h2>Explore monitored locations across Fiji</h2>
          <p>
            Review stored weather observations, flood-risk predictions and
            approved community alerts on the interactive map.
          </p>
        </div>
        <Link className="button button--primary" to="/weather-map">
          Open weather map
        </Link>
      </section>

      <section>
        <div className="section-heading">
          <div>
            <span className="eyebrow">Current system</span>
            <h2>What this milestone demonstrates</h2>
          </div>
          <span className="roadmap-label">Backend-integrated frontend</span>
        </div>

        <div className="module-grid">
          {[
            ['Secure access', 'Registration, login and current-user checks use the live FastAPI authentication API.'],
            ['Weather map', 'Locations and risk predictions come from the live registry; weather observations come from the weather API. Sample predictions stay labelled.'],
            ['Operational alerts', 'MET administrators manage saved alerts. Approved alerts appear in the community feed.'],
          ].map(([title, description], index) => (
            <article className="module-card" key={title}>
              <span className="module-card__number">0{index + 1}</span>
              <h3>{title}</h3>
              <p>{description}</p>
              <small>Integrated</small>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
