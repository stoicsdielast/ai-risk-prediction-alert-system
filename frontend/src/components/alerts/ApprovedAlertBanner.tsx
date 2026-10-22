import { Link, useLocation } from 'react-router-dom'
import { usePublicAlerts } from '../../alerts/PublicAlertContext'
import { formatDateTime } from '../../utils/date'
import { RiskPill } from '../pills/DataPill'
import { AlertProvenance } from './AlertProvenance'
import { isSimulatedAlert } from '../../alerts/provenance'

export function ApprovedAlertBanner() {
  const feed = usePublicAlerts()
  const location = useLocation()
  if (location.pathname === '/alerts') return null
  const alert = feed.data?.find((item) => item.severity === 'HIGH' || item.severity === 'VERY_HIGH')
  if (!alert) return null
  return (
    <aside className={`workspace-banner approved-alert-banner approved-alert-banner--${alert.severity.toLowerCase()}`} aria-label="Approved community alert">
      <div className="workspace-banner__content">
        <div className="workspace-banner__heading">
          <h2>{isSimulatedAlert(alert) ? 'Simulated flood alert' : 'Active flood alert'} · {alert.location.name}</h2>
          <RiskPill risk={alert.severity} compact />
        </div>
        <AlertProvenance alert={alert} />
        <p>{alert.message}</p>
        <small>{feed.error ? 'Alert feed unavailable; this information may be out of date.' : `Published ${formatDateTime(alert.approved_at!)}`} · Administrator-approved community alert</small>
      </div>
      <Link className="button button--secondary workspace-banner__action" to={`/alerts#alert-${alert.id}`}>View community alerts <span aria-hidden="true">→</span></Link>
    </aside>
  )
}
