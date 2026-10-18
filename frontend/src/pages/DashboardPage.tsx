import { Link } from 'react-router-dom'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useActiveAlerts } from '../alerts/useActiveAlerts'
import { Alert } from '../components/Alert'
import { ActiveAlertsPanel } from '../components/dashboard/ActiveAlertsPanel'
import { MetricIcon } from '../components/dashboard/MetricIcon'
import { PriorityAreasPanel } from '../components/dashboard/PriorityAreasPanel'
import { SummaryCard } from '../components/dashboard/SummaryCard'
import { usePriorityLocations } from '../locations/usePriorityLocations'

interface DashboardLocationState {
  accessDenied?: string
}

function countOrDash(isKnown: boolean, count: number) {
  return isKnown ? count : '–'
}

export function DashboardPage() {
  const { user } = useAuth()
  const location = useLocation()
  const accessDenied = (location.state as DashboardLocationState | null)
    ?.accessDenied
  const activeAlerts = useActiveAlerts()
  const priority = usePriorityLocations()

  if (!user) return null

  const alertsKnown = activeAlerts.status === 'ready' && priority.status === 'ready'
  const priorityAlertCount = activeAlerts.alerts.filter((alert) =>
    priority.savedSlugs.has(alert.location.slug),
  ).length
  const highRiskAreas = priority.locations.filter(
    (area) =>
      area.prediction?.risk_level === 'HIGH' || area.prediction?.risk_level === 'VERY_HIGH',
  )

  return (
    <div className="page-stack">
      {accessDenied && <Alert tone="error">{accessDenied}</Alert>}

      <section className="page-heading">
        <div>
          <span className="eyebrow">Secure workspace</span>
          <h1>Bula, {user.name.split(' ')[0]}.</h1>
          <p>Here are the latest flood alerts and the areas you are keeping an eye on.</p>
        </div>
        <span className="status-pill status-pill--approved">
          <span /> Approved account
        </span>
      </section>

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

      <section className="metric-grid" aria-label="Your flood-risk overview">
        <SummaryCard
          label="Active alerts"
          value={countOrDash(activeAlerts.status === 'ready', activeAlerts.alerts.length)}
          detail={
            activeAlerts.status === 'error'
              ? 'Alerts are unavailable right now'
              : 'Approved by Fiji MET for the public'
          }
          icon={<MetricIcon name="active" />}
          tone="teal"
        />
        <SummaryCard
          label="Alerts in your areas"
          value={countOrDash(alertsKnown, priorityAlertCount)}
          detail={
            priority.status === 'ready' && priority.locations.length === 0
              ? 'Save priority areas to track their alerts'
              : 'Active alerts in your priority areas'
          }
          icon={<MetricIcon name="risk" />}
          tone={priorityAlertCount > 0 ? 'red' : 'indigo'}
        />
        <SummaryCard
          label="Priority areas"
          value={countOrDash(priority.status === 'ready', priority.locations.length)}
          detail={
            priority.status === 'error'
              ? 'Priority areas are unavailable right now'
              : 'Locations saved on your account'
          }
          icon={<MetricIcon name="priority" />}
          tone="indigo"
        />
        <SummaryCard
          label="High-risk priority areas"
          value={countOrDash(priority.status === 'ready', highRiskAreas.length)}
          detail={
            highRiskAreas.some((area) => area.prediction?.is_sample)
              ? 'High or very high · includes labelled sample risks'
              : 'High or very high predicted flood risk'
          }
          icon={<MetricIcon name="locations" />}
          tone={highRiskAreas.length > 0 ? 'amber' : 'indigo'}
        />
      </section>

      <ActiveAlertsPanel activeAlerts={activeAlerts} savedSlugs={priority.savedSlugs} />

      <PriorityAreasPanel priority={priority} />

      <section className="admin-callout">
        <div className="admin-callout__mark" aria-hidden="true">W</div>
        <div>
          <span className="eyebrow">Weather &amp; flood-risk map</span>
          <h2>Check flood risk across Fiji</h2>
          <p>
            See the latest flood-risk predictions for monitored locations and save the
            places that matter to you as priority areas.
          </p>
        </div>
        <Link className="button button--primary" to="/weather-map">
          Open weather map
        </Link>
      </section>
    </div>
  )
}
