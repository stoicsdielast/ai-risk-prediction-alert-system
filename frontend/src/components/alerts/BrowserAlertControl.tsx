import { useBrowserAlerts } from '../../alerts/useBrowserAlerts'
import { Link } from 'react-router-dom'

export function BrowserAlertControl() {
  const alerts = useBrowserAlerts()
  return (
    <section className="prototype-panel browser-alert-control" aria-label="Browser notifications">
      <div>
        <strong>Alerts & notifications</strong>
        <p role="status">
          {alerts.permission === 'granted' && (alerts.enabled ? '✓ Browser notifications opted in for saved locations' : 'Browser permission granted; account notifications disabled')}
          {alerts.permission === 'default' && 'Enable desktop notifications for newly approved high-risk alerts.'}
          {alerts.permission === 'denied' && 'Browser notification permission was denied. You can enable it through your browser settings.'}
          {alerts.permission === 'unsupported' && 'This browser does not support desktop notifications. Website alerts remain available.'}
          {alerts.permission === 'insecure' && 'Browser alerts require HTTPS or localhost. Website alerts remain available.'}
        </p>
        <details className="source-details">
          <summary>Notification settings & delivery status</summary>
          <p>Keep this site open. Notifications may be delayed in background tabs.</p>
          <p><Link to="/dashboard#saved-locations">Manage saved locations and notification history</Link></p>
          {!alerts.deliveryEnabled && <p>Browser delivery is disabled by the operator. Your preferences and notification history are saved.</p>}
        </details>
        {alerts.error && <p role="alert">{alerts.error}</p>}
      </div>
      <div className="browser-alert-control__actions">
        {!alerts.enabled && ['default', 'granted'].includes(alerts.permission) && (
          <button className="button button--primary" onClick={() => void alerts.enable()} disabled={alerts.busy}>
            {alerts.busy ? 'Requesting permission…' : 'Enable Browser Alerts'}
          </button>
        )}
        {alerts.enabled && <button className="button button--secondary" onClick={() => void alerts.disable()} disabled={alerts.busy}>Disable Browser Alerts</button>}
        {import.meta.env.DEV && alerts.permission === 'granted' && (
          <button className="button button--secondary" onClick={alerts.test}>Test Browser Notification</button>
        )}
      </div>
    </section>
  )
}
