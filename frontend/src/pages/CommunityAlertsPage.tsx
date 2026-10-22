import { usePublicAlerts } from '../alerts/useAlertFeed'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { PageHeader } from '../components/layout/PageHeader'
import { RiskPill } from '../components/pills/DataPill'
import { formatDateTime } from '../utils/date'
import { AlertProvenance } from '../components/alerts/AlertProvenance'

export function CommunityAlertsPage() {
  const feed = usePublicAlerts()
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Community information"
        title="Alerts & notifications"
        description="Administrator-approved community alerts. Simulated alerts are labelled. Official Fiji MET warnings are issued separately and take precedence."
      />
      <AlertFeedStatus {...feed} />
      {feed.data?.length === 0 && (
        <section className="prototype-panel prototype-empty-state">
          <h2>No active alerts</h2>
          <p>There are currently no published alerts for monitored locations.</p>
        </section>
      )}
      <div className="community-alert-list">
        {feed.data?.map((alert) => (
          <article className={`prototype-panel community-alert-card community-alert-card--${alert.severity.toLowerCase()}`} key={alert.id} id={`alert-${alert.id}`}>
            <header>
              <h2>{alert.location.name}</h2>
              <RiskPill risk={alert.severity} />
            </header>
            <AlertProvenance alert={alert} />
            <p className="community-alert-message">{alert.message}</p>
            <dl className="alert-detail-grid">
              <div>
                <dt>Created</dt>
                <dd>
                  <time dateTime={alert.created_at}>{formatDateTime(alert.created_at)}</time>
                </dd>
              </div>
              {alert.approved_at && (
                <div>
                  <dt>Published</dt>
                  <dd>
                    <time dateTime={alert.approved_at}>{formatDateTime(alert.approved_at)}</time>
                  </dd>
                </div>
              )}
            </dl>
          </article>
        ))}
      </div>
    </div>
  )
}
