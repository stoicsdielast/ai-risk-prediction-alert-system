import { Link } from 'react-router-dom'
import { MetricIcon } from '../components/dashboard/MetricIcon'
import { SummaryCard } from '../components/dashboard/SummaryCard'
import { PageHeader } from '../components/layout/PageHeader'
import { DataPill, RiskPill, StatusPill } from '../components/pills/DataPill'
import { usePrototypeData } from '../prototype/usePrototypeData'
import { formatRelativeTime } from '../utils/date'

export function AdminDashboardPage() {
  const { alerts, locations, predictions } = usePrototypeData()

  const activeAlerts = alerts.filter((alert) => alert.status === 'APPROVED')
  const pendingAlerts = alerts.filter((alert) => alert.status === 'PENDING')
  const highRiskLocations = locations.filter(
    (location) =>
      location.riskLevel === 'HIGH' || location.riskLevel === 'VERY_HIGH',
  )
  const monitoredDivisions = new Set(
    locations.map((location) => location.division),
  ).size
  const recentAlerts = [...alerts]
    .sort(
      (first, second) =>
        new Date(second.createdAt).getTime() - new Date(first.createdAt).getTime(),
    )
    .slice(0, 4)
  const recentPredictions = [...predictions]
    .sort(
      (first, second) =>
        new Date(second.generatedAt).getTime() -
        new Date(first.generatedAt).getTime(),
    )
    .slice(0, 4)

  return (
    <div className="prototype-page dashboard-page">
      <PageHeader
        eyebrow="MET operations"
        title="Flood risk overview"
        description="Monitor prototype risk signals, predictions and alerts across Fiji from one operational view."
      />

      <section className="metric-grid" aria-label="Operational summary">
        <SummaryCard
          label="Monitored locations"
          value={locations.length}
          detail={`Across ${monitoredDivisions} ${
            monitoredDivisions === 1 ? 'division' : 'divisions'
          }`}
          icon={<MetricIcon name="locations" />}
          tone="indigo"
        />
        <SummaryCard
          label="Active alerts"
          value={activeAlerts.length}
          detail="Approved for public use"
          icon={<MetricIcon name="active" />}
          tone="teal"
        />
        <SummaryCard
          label="Pending alerts"
          value={pendingAlerts.length}
          detail="Awaiting MET review"
          icon={<MetricIcon name="pending" />}
          tone="amber"
        />
        <SummaryCard
          label="High-risk areas"
          value={highRiskLocations.length}
          detail="High or very high risk"
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

          {recentAlerts.length === 0 ? (
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
                      <strong>{alert.locationName}</strong>
                      <RiskPill risk={alert.severity} compact />
                    </div>
                    <p>{alert.message}</p>
                    <small>
                      {alert.id} · {formatRelativeTime(alert.createdAt)}
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
              <span>AI model output</span>
              <h2>Recent predictions</h2>
            </div>
            <Link className="panel-link" to="/weather-map">
              Open map <span aria-hidden="true">→</span>
            </Link>
          </header>

          {recentPredictions.length === 0 ? (
            <div className="prototype-empty-state">
              <h3>No predictions found</h3>
              <p>Prediction updates will appear here when data becomes available.</p>
            </div>
          ) : (
            <div className="prediction-list">
              {recentPredictions.map((prediction) => (
                <article className="prediction-item" key={prediction.id}>
                  <div className="prediction-item__heading">
                    <div>
                      <strong>{prediction.locationName}</strong>
                      <small>{prediction.horizon}</small>
                    </div>
                    <RiskPill risk={prediction.riskLevel} compact />
                  </div>
                  <div className="prediction-item__footer">
                    <DataPill
                      value="AI_PREDICTION"
                      label={`${prediction.confidencePercent}% confidence`}
                      compact
                    />
                    <time dateTime={prediction.generatedAt}>
                      {formatRelativeTime(prediction.generatedAt)}
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
