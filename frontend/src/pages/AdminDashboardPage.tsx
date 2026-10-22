import { Link } from 'react-router-dom'
import { useAdminAlerts, usePublicAlerts } from '../alerts/useAlertFeed'
import { Alert } from '../components/Alert'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { SummaryCard } from '../components/dashboard/SummaryCard'
import { PageHeader } from '../components/layout/PageHeader'
import { DataPill, RiskPill, StatusPill } from '../components/pills/DataPill'
import { useLocations } from '../locations/useLocations'
import type { ApiLocation } from '../types/location'
import { formatRelativeTime } from '../utils/date'
import { SyntheticReplayPanel } from '../components/research/SyntheticReplayPanel'

function MetricIcon({ name }: { name: 'locations' | 'active' | 'pending' | 'risk' }) {
  if (name === 'locations') {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="10" r="2" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    )
  }

  if (name === 'active') {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }

  if (name === 'pending') {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8" />
        <path
          d="M12 7.5V12l3 2"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m12 3 9 16H3L12 3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M12 9v4.5M12 17h.01"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function AdminDashboardPage() {
  const { status: locationsStatus, locations, error: locationsError } = useLocations()
  const feed = useAdminAlerts()
  const publicFeed = usePublicAlerts()
  const alerts = feed.data ?? []
  const locationsReady = locationsStatus === 'ready'

  const activeAlerts = publicFeed.data ?? []
  const pendingAlerts = alerts.filter((alert) => alert.status === 'PENDING')
  const highRiskLocations = locations.filter(
    (location) =>
      location.prediction &&
      (location.prediction.risk_level === 'HIGH' ||
        location.prediction.risk_level === 'VERY_HIGH'),
  )
  const monitoredDivisions = new Set(
    locations.map((location) => location.division),
  ).size
  const recentAlerts = [...alerts]
    .sort(
      (first, second) =>
        new Date(second.created_at).getTime() - new Date(first.created_at).getTime(),
    )
    .slice(0, 4)
  const recentPredictions = [...locations]
    .filter((location): location is ApiLocation & { prediction: NonNullable<ApiLocation['prediction']> } =>
      location.prediction !== null)
    .sort(
      (first, second) =>
        new Date(second.prediction.predicted_at).getTime() -
        new Date(first.prediction.predicted_at).getTime(),
    )
    .slice(0, 4)

  return (
    <div className="prototype-page dashboard-page">
      <PageHeader
        eyebrow="MET operations"
        title="Flood risk overview"
        description="Review live alert activity, stored observations and latest predictions from the backend."
      />

      <AlertFeedStatus
        {...feed}
        refresh={() => { feed.refresh(); publicFeed.refresh() }}
      />
      {publicFeed.error && (
        <Alert tone="error">Active alert count is unavailable. {publicFeed.error}</Alert>
      )}
      {locationsError && (
        <Alert tone="error">
          Monitored-location metrics are unavailable. {locationsError}
        </Alert>
      )}

      <SyntheticReplayPanel />

      <section className="metric-grid" aria-label="Operational summary">
        <SummaryCard
          label="Monitored locations"
          value={locationsReady ? locations.length : '–'}
          detail={
            locationsReady
              ? `Across ${monitoredDivisions} ${
                  monitoredDivisions === 1 ? 'division' : 'divisions'
                }`
              : 'Loading location registry…'
          }
          icon={<MetricIcon name="locations" />}
          tone="indigo"
        />
        <SummaryCard
          label="Active alerts"
          value={publicFeed.data && !publicFeed.error ? activeAlerts.length : '–'}
          detail="Approved for public use"
          icon={<MetricIcon name="active" />}
          tone="teal"
        />
        <SummaryCard
          label="Pending alerts"
          value={feed.data && !feed.error ? pendingAlerts.length : '–'}
          detail="Awaiting MET review"
          icon={<MetricIcon name="pending" />}
          tone="amber"
        />
        <SummaryCard
          label="High-risk areas"
          value={locationsReady ? highRiskLocations.length : '–'}
          detail="High or very high latest risk"
          icon={<MetricIcon name="risk" />}
          tone="red"
        />
      </section>

      <section className="dashboard-grid" aria-label="Latest operational activity">
        <article className="prototype-panel recent-alerts-panel">
          <header className="prototype-panel__header">
            <div>
              <span>Alert activity</span>
              <h2>Recent alerts</h2>
            </div>
            <Link className="panel-link" to="/admin/alerts">
              Manage alerts <span aria-hidden="true">→</span>
            </Link>
          </header>

          {!feed.data ? (
            <div className="prototype-empty-state">
              {feed.error ? 'Alert activity is unavailable.' : 'Loading alert activity…'}
            </div>
          ) : recentAlerts.length === 0 ? (
            <div className="prototype-empty-state">
              <h3>No alerts found</h3>
              <p>New alerts will appear here when data becomes available.</p>
            </div>
          ) : (
            <div className="activity-list">
              {recentAlerts.map((alert) => (
                <article className="activity-item" key={alert.id}>
                  <div className="activity-item__content">
                    <div className="activity-item__heading">
                      <strong>{alert.location.name}</strong>
                      <RiskPill risk={alert.severity} compact />
                    </div>
                    <p>{alert.message}</p>
                    <small>
                      #{alert.id} · {formatRelativeTime(alert.created_at)}
                    </small>
                  </div>
                  <StatusPill status={alert.status} />
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="prototype-panel recent-predictions-panel">
          <header className="prototype-panel__header">
            <div>
              <span>Latest model output</span>
              <h2>Recent predictions</h2>
            </div>
            <Link className="panel-link" to="/weather-map">
              Open map <span aria-hidden="true">→</span>
            </Link>
          </header>

          {!locationsReady ? (
            <div className="prototype-empty-state">
              {locationsError
                ? 'Predictions are unavailable because the location registry could not be loaded.'
                : 'Loading predictions…'}
            </div>
          ) : recentPredictions.length === 0 ? (
            <div className="prototype-empty-state">
              <h3>No predictions found</h3>
              <p>Prediction updates will appear here when data becomes available.</p>
            </div>
          ) : (
            <div className="prediction-list">
              {recentPredictions.map((location) => (
                <article className="prediction-item" key={location.id}>
                  <div className="prediction-item__heading">
                    <div>
                      <strong>{location.name}</strong>
                      <small>{location.division_label}</small>
                    </div>
                    <RiskPill risk={location.prediction.risk_level} compact />
                  </div>
                  <div className="prediction-item__footer">
                    <DataPill
                      value={location.prediction.is_sample ? 'SAMPLE_RISK' : 'AI_PREDICTION'}
                      label={`${Math.round(location.prediction.flood_probability * 100)}% probability`}
                      compact
                    />
                    <time dateTime={location.prediction.predicted_at}>
                      {formatRelativeTime(location.prediction.predicted_at)}
                    </time>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="quick-action-panel">
        <div className="quick-action-panel__icon" aria-hidden="true">
          <MetricIcon name="active" />
        </div>
        <div>
          <span>Quick action</span>
          <h2>Review operational alerts</h2>
          <p>
            Check AI recommendations and decide what is ready for public release.
          </p>
        </div>
        <Link className="button button--primary" to="/admin/alerts">
          Open alert management
        </Link>
      </section>
    </div>
  )
}
