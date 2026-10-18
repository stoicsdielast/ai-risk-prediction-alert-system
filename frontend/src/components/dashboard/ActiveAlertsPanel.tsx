import { Link } from 'react-router-dom'
import type { ActiveAlertsState } from '../../alerts/useActiveAlerts'
import type { AlertSource, ApiAlert } from '../../types/alert'
import { formatDateTime, formatRelativeTime } from '../../utils/date'
import { RiskPill } from '../pills/DataPill'

const MAX_ALERTS_SHOWN = 5

const SOURCE_LABELS: Record<AlertSource, string> = {
  MET_OFFICIAL: 'Issued by Fiji MET',
  AI_RECOMMENDATION: 'AI-assisted, reviewed by Fiji MET',
}

interface ActiveAlertsPanelProps {
  activeAlerts: ActiveAlertsState
  savedSlugs: ReadonlySet<string>
}

/** Alerts in the user's priority areas come first, then the newest. */
function sortForUser(alerts: ApiAlert[], savedSlugs: ReadonlySet<string>) {
  return alerts
    .map((alert, index) => ({ alert, index, isPriority: savedSlugs.has(alert.location.slug) }))
    .sort((first, second) =>
      first.isPriority === second.isPriority
        ? first.index - second.index
        : first.isPriority
          ? -1
          : 1,
    )
}

export function ActiveAlertsPanel({ activeAlerts, savedSlugs }: ActiveAlertsPanelProps) {
  const { status, error, alerts, retry } = activeAlerts
  const shown = sortForUser(alerts, savedSlugs).slice(0, MAX_ALERTS_SHOWN)

  return (
    <section aria-labelledby="active-alerts-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Approved for the public</span>
          <h2 id="active-alerts-title">Active flood alerts</h2>
        </div>
        {status === 'ready' && alerts.length > MAX_ALERTS_SHOWN && (
          <span className="roadmap-label">
            Showing {MAX_ALERTS_SHOWN} of {alerts.length}
          </span>
        )}
      </div>

      {status === 'loading' && (
        <p className="priority-areas-empty" role="status">
          Loading active alerts…
        </p>
      )}

      {status === 'error' && (
        <div className="priority-status" role="alert">
          <span>{error}</span>
          <button type="button" className="map-clear-button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && alerts.length === 0 && (
        <p className="priority-areas-empty">
          There are no active flood alerts right now. Keep following official Fiji
          Meteorological Service updates.
        </p>
      )}

      {shown.length > 0 && (
        <ul className="community-alert-list">
          {shown.map(({ alert, isPriority }) => {
            const issuedAt = alert.approved_at ?? alert.created_at

            return (
              <li
                key={alert.id}
                className={`community-alert${isPriority ? ' is-priority' : ''}`}
              >
                <div className="community-alert__heading">
                  <RiskPill risk={alert.severity} compact />
                  <strong>{alert.location.name}</strong>
                  <span>{alert.location.division_label}</span>
                  {isPriority && (
                    <span className="community-alert__priority">
                      <span aria-hidden="true">★</span> Your priority area
                    </span>
                  )}
                </div>
                <p>{alert.message}</p>
                <small>
                  {SOURCE_LABELS[alert.source]} ·{' '}
                  <time dateTime={issuedAt} title={formatDateTime(issuedAt)}>
                    {formatRelativeTime(issuedAt)}
                  </time>
                </small>
              </li>
            )
          })}
        </ul>
      )}

      {status === 'ready' && (
        <p className="community-alert-footnote">
          Always follow official Fiji Meteorological Service warnings and emergency
          instructions. <Link to="/weather-map">See flood risk on the map</Link>
        </p>
      )}
    </section>
  )
}
