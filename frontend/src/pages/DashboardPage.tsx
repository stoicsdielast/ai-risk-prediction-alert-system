import { Link } from 'react-router-dom'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { usePublicAlerts } from '../alerts/useAlertFeed'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { SyntheticReplayPanel } from '../components/research/SyntheticReplayPanel'
import { SavedLocationsPanel } from '../components/alerts/SavedLocationsPanel'
import { isSimulatedAlert } from '../alerts/provenance'

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
    <div className="prototype-page community-dashboard">
      {accessDenied && <Alert tone="error">{accessDenied}</Alert>}

      <section className="page-heading">
        <div>
          <span className="eyebrow">Community monitoring</span>
          <h1>Flood risk dashboard</h1>
          <p>Bula, {user.name.split(' ')[0]}. Review community alerts, weather analysis and your saved locations.</p>
        </div>
        <span className="status-pill status-pill--approved">
          <span /> Approved account
        </span>
      </section>

      <section className="prototype-panel community-alert-card" aria-label="Community alert summary">
        <h2>Active community alerts: {alerts.data && !alerts.error ? alerts.data.length : '–'}</h2>
        {alerts.data?.some(isSimulatedAlert) && <p>Includes simulated alerts, which are labelled in the community feed.</p>}
        <AlertFeedStatus {...alerts} />
        <Link className="button button--primary" to="/alerts">View community alerts</Link>
      </section>

      <SavedLocationsPanel />
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
          <p>Your approved platform role</p>
        </article>
        <article className="summary-card">
          <span className="summary-card__label">Authentication</span>
          <strong>Protected session</strong>
          <p>Your account access is verified</p>
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
            <span className="eyebrow">Monitoring tools</span>
            <h2>Weather monitoring & community alerts</h2>
          </div>
        </div>

        <div className="module-grid">
          {[
            ['Flood mapping', 'Explore monitored locations, stored weather records and flood risk predictions. Data sources and sample predictions are labelled.'],
            ['Historical analysis', 'Examine generated historical weather and model estimates across Fiji. Synthetic records are identified in the analysis.'],
            ['Alerts & notifications', 'Follow administrator-approved community alerts and manage notifications for saved locations. Simulated alerts are clearly identified.'],
          ].map(([title, description], index) => (
            <article className="module-card" key={title}>
              <span className="module-card__number">0{index + 1}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
