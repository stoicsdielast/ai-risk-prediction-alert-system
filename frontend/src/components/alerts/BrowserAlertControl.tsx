import { useBrowserAlerts } from '../../alerts/useBrowserAlerts'

export function BrowserAlertControl() {
  const alerts = useBrowserAlerts()
  return (
    <section className="prototype-panel browser-alert-control" aria-label="Browser notifications">
      <div>
        <strong>Notifications</strong>
        <p role="status">
          {alerts.permission === 'granted' && '✓ Browser alerts enabled'}
          {alerts.permission === 'default' && 'Enable desktop notifications for newly approved high-risk alerts.'}
          {alerts.permission === 'denied' && 'Browser notification permission was denied. You can enable it through your browser settings.'}
          {alerts.permission === 'unsupported' && 'This browser does not support desktop notifications. Website alerts remain available.'}
          {alerts.permission === 'insecure' && 'Browser alerts require HTTPS or localhost. Website alerts remain available.'}
        </p>
        <small>University prototype · Keep this site open. Notifications may be delayed in background tabs.</small>
        {alerts.error && <p role="alert">{alerts.error}</p>}
      </div>
      <div className="browser-alert-control__actions">
        {alerts.permission === 'default' && (
          <button className="button button--primary" onClick={() => void alerts.enable()} disabled={alerts.busy}>
            {alerts.busy ? 'Requesting permission…' : 'Enable Browser Alerts'}
          </button>
        )}
        {import.meta.env.DEV && alerts.permission === 'granted' && (
          <button className="button button--secondary" onClick={alerts.test}>Test Browser Notification</button>
        )}
      </div>
    </section>
  )
}
