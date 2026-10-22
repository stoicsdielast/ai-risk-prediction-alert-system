import { useState } from 'react'
import type { SyntheticAlert } from '../../api/synthetic'
import { formatDateTime } from '../../utils/date'
import { StatusPill } from '../pills/DataPill'

export type SyntheticAction = 'approve' | 'acknowledge' | 'resolve' | 'cancel'

export function SyntheticAlertCard({ alert, admin, enabled, busy, onAction }: {
  alert: SyntheticAlert; admin: boolean; enabled: boolean; busy: boolean
  onAction: (id: number, action: SyntheticAction, reason?: string) => Promise<void>
}) {
  const [reason, setReason] = useState('')
  const open = ['PENDING', 'APPROVED'].includes(alert.status)
  return <article id={`synthetic-alert-${alert.id}`} className="synthetic-alert">
    <div className="workspace-banner__heading">
      <h3>{alert.location_name} · {alert.is_test ? 'Test alert' : 'Simulated alert'} #{alert.id}</h3>
      <StatusPill status={alert.status} />
    </div>
    <span className="alert-source-label">Synthetic data · Not an emergency warning</span>
    <p>{alert.message}</p>
    <small>Historical timestamp: {formatDateTime(alert.timestamp)} · {alert.risk_category.replace('_', ' ')} · {(alert.probability * 100).toFixed(1)}%</small>
    {alert.acknowledged_at && <p>Acknowledged {formatDateTime(alert.acknowledged_at)} by administrator #{alert.acknowledged_by}</p>}
    {alert.closed_at && <p>{alert.status === 'RESOLVED' ? 'Resolved' : 'Cancelled'} {formatDateTime(alert.closed_at)} by administrator #{alert.closed_by}. Reason: {alert.closure_reason}</p>}
    {admin && open && <div className="synthetic-alert__management">
      <div className="alert-management-actions">
        {alert.status === 'PENDING' && <button className="button button--secondary" disabled={busy || !enabled} onClick={() => void onAction(alert.id, 'approve')}>Approve</button>}
        {alert.status === 'PENDING' && !enabled && <small>Approval is disabled by the operator. Cancellation remains available.</small>}
        {alert.status === 'APPROVED' && <button className="button button--secondary" disabled={busy || Boolean(alert.acknowledged_at)} onClick={() => void onAction(alert.id, 'acknowledge')}>{alert.acknowledged_at ? 'Acknowledged' : 'Acknowledge'}</button>}
      </div>
      <label className="form-field"><span>Action reason for alert #{alert.id}</span>
        <textarea rows={2} maxLength={1000} value={reason} disabled={busy} onChange={event => setReason(event.target.value)} />
      </label>
      <div className="alert-management-actions">
        {alert.status === 'APPROVED' && <button className="button button--primary" disabled={busy || !reason.trim()} onClick={() => void onAction(alert.id, 'resolve', reason)}>Resolve</button>}
        <button className="button button--danger-quiet" disabled={busy || !reason.trim()} onClick={() => void onAction(alert.id, 'cancel', reason)}>Cancel alert</button>
      </div>
      <small>Enter a reason to resolve or cancel. History is retained.</small>
    </div>}
  </article>
}
