import { Link, useLocation } from 'react-router-dom'
import { usePublicAlerts } from '../../alerts/PublicAlertContext'
import { formatDateTime } from '../../utils/date'
import { RiskPill } from '../pills/DataPill'

export function ApprovedAlertBanner() {
  const feed = usePublicAlerts()
  const location = useLocation()
  if (location.pathname === '/alerts') return null
  const alert = feed.data?.find((item) => item.severity === 'HIGH' || item.severity === 'VERY_HIGH')
  if (!alert) return null
  return (
    <aside className={`prototype-panel approved-alert-banner approved-alert-banner--${alert.severity.toLowerCase()}`} aria-label="Approved community alert">
      <div><RiskPill risk={alert.severity} /> <strong>{alert.location.name}</strong></div>
      {alert.is_demo && <strong>DEMO ONLY — simulated prediction</strong>}
      <p>{alert.message}</p>
      <small>{feed.error ? 'Alert feed unavailable; this information may be out of date.' : `Published ${formatDateTime(alert.approved_at!)}`}</small>
      <Link to={`/alerts#alert-${alert.id}`}>View all approved community alerts</Link>
    </aside>
  )
}
