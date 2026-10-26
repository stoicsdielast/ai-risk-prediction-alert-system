import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { inAppAlertKey, useInAppAlerts } from '../../alerts/useInAppAlerts'
import { isSimulatedAlert } from '../../alerts/provenance'
import { formatDateTime } from '../../utils/date'
import { RiskPill } from '../pills/DataPill'
import { AlertProvenance } from './AlertProvenance'
import './in-app-alerts.css'

export function InAppAlerts() {
  const { user } = useAuth()
  const scope = user ? `user-${user.id}` : 'guest'
  return <AlertInbox key={scope} scope={scope} />
}

function AlertInbox({ scope }: { scope: string }) {
  const { alerts, unread, notices, markRead, warning, feed, guest, filterLoading, filterError } = useInAppAlerts(scope)
  const tray = useRef<HTMLDetailsElement>(null)
  const location = useLocation()
  const focusedTarget = useRef<string | null>(null)
  const unreadKeys = new Set(unread.map(inAppAlertKey))

  useEffect(() => {
    const target = location.pathname === '/alerts' && /^#alert-\d+$/.test(location.hash)
      ? location.hash.slice(1) : null
    if (!target) { focusedTarget.current = null; return }
    if (focusedTarget.current === target) return
    const card = document.getElementById(target)
    if (!card) return
    card.tabIndex = -1
    card.scrollIntoView?.({ block: 'start' })
    card.focus({ preventScroll: true })
    focusedTarget.current = target
  }, [location.pathname, location.hash, feed.data])
  return (
    <section className="in-app-alerts" aria-label="In-app notifications">
      <details ref={tray} className="in-app-alerts__tray">
        <summary>
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg> In-app alerts
          <span className="in-app-alerts__count">{unread.length} unread</span>
        </summary>
        <div className="in-app-alerts__body">
          <h2>Community alert inbox</h2>
          <p>Approved high and very high risk alerts {guest ? 'for all monitored locations' : 'for your saved locations'}. Available while this site is open; updates about every 30 seconds. Mobile browsers may pause updates in the background.</p>
          <p>Read status is stored only in this browser. Desktop notifications are managed separately above.</p>
          {!guest && <p><Link to="/dashboard#saved-locations">Manage saved locations</Link></p>}
          <p>Official Fiji MET warnings take precedence.</p>
          {warning && <p role="status">{warning}</p>}
          {filterError && <p role="status">{filterError}</p>}
          {filterLoading && <p role="status">Checking saved locations…</p>}
          {feed.error && <p role="status">Alert updates unavailable. Saved feed information may be out of date. {feed.error}</p>}
          <div className="in-app-alerts__actions">
            <button type="button" className="button button--secondary" disabled={feed.refreshing} onClick={feed.refresh}>Refresh inbox</button>
            <button type="button" className="button button--secondary" disabled={!unread.length} onClick={() => markRead(alerts)}>Mark all as read</button>
          </div>
          {feed.data === null && !feed.error && <p role="status">Loading community alerts…</p>}
          {feed.data !== null && !filterLoading && !filterError && !alerts.length && <p>No active high-risk community alerts{guest ? '.' : ' for your saved locations.'}</p>}
          <ul className="in-app-alerts__list">
            {alerts.map(alert => (
              <li key={inAppAlertKey(alert)} className={unreadKeys.has(inAppAlertKey(alert)) ? 'is-unread' : undefined}>
                <div className="in-app-alerts__heading">
                  <strong>{alert.location.name}</strong><RiskPill risk={alert.severity} compact />
                  <small>{unreadKeys.has(inAppAlertKey(alert)) ? 'Unread' : 'Read'}</small>
                </div>
                <AlertProvenance alert={alert} />
                <p>{alert.message}</p>
                <small>Published {formatDateTime(alert.approved_at!)}</small>
                <Link className="button button--secondary" to={`/alerts#alert-${alert.id}`} onClick={() => {
                  markRead([alert])
                  if (tray.current) tray.current.open = false
                }}>View alert for {alert.location.name}</Link>
              </li>
            ))}
          </ul>
          <Link to="/alerts" onClick={() => { if (tray.current) tray.current.open = false }}>View all community alerts</Link>
        </div>
      </details>
      <div className="in-app-alerts__notices" aria-live="polite" aria-relevant="additions" aria-atomic="false">
        {notices.map(alert => (
          <aside key={inAppAlertKey(alert)} className="in-app-alerts__notice" aria-label={`New ${isSimulatedAlert(alert) ? 'simulated ' : ''}alert for ${alert.location.name}`}>
            <div className="in-app-alerts__heading"><strong>New alert · {alert.location.name}</strong><RiskPill risk={alert.severity} compact /></div>
            <AlertProvenance alert={alert} />
            <p>{alert.message}</p>
            <div className="in-app-alerts__actions">
              <Link className="button button--primary" to={`/alerts#alert-${alert.id}`} onClick={() => markRead([alert])}>View alert</Link>
              <button type="button" className="button button--secondary" aria-label={`Dismiss alert for ${alert.location.name}`} onClick={() => markRead([alert])}>Dismiss</button>
            </div>
          </aside>
        ))}
      </div>
    </section>
  )
}
