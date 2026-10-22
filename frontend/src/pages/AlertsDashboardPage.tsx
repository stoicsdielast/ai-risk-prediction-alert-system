import { isExpiredAlert, isSimulatedAlert } from '../alerts/provenance'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ALERT_STATUSES, createAlert, createDemoAlert, editAlert, reviewAlert } from '../api/alerts'
import { ApiError } from '../api/client'
import { useAdminAlerts, useAdminRequest } from '../alerts/useAlertFeed'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { AlertEditor } from '../components/alerts/AlertEditor'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { PageHeader } from '../components/layout/PageHeader'
import { DataPill, RiskPill, StatusPill } from '../components/pills/DataPill'
import type { AdminAlert, AlertAction, AlertDraft } from '../types/alert'
import type { AlertStatus } from '../types/prototype'
import { formatDateTime, formatRelativeTime } from '../utils/date'

export function AlertsDashboardPage() {
  const { token } = useAuth()
  const feed = useAdminAlerts()
  const request = useAdminRequest()
  const [view, setView] = useState<'ALL' | 'ACTIVE' | 'HISTORY'>('ALL')
  const [filter, setFilter] = useState<'ALL' | AlertStatus>('ALL')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editor, setEditor] = useState<AdminAlert | 'new' | null>(null)
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const alerts = feed.data ?? []
  const query = search.trim().toLowerCase()
  const filtered = alerts.filter(
    (alert) =>
      (filter === 'ALL' || alert.status === filter) &&
      (view === 'ALL' || (view === 'ACTIVE' ? alert.status === 'APPROVED' && !isExpiredAlert(alert) : !['PENDING', 'APPROVED'].includes(alert.status) || isExpiredAlert(alert))) &&
      `${alert.id} ${alert.location.name} ${alert.message}`.toLowerCase().includes(query),
  )
  const selected = filtered.find((alert) => alert.id === selectedId) ?? filtered[0] ?? null

  const mutate = async (operation: () => Promise<AdminAlert>, message: string) => {
    if (busy) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const updated = await request(operation)
      feed.setData((current) => [
        updated,
        ...(current ?? []).filter((alert) => alert.id !== updated.id),
      ])
      setSelectedId(updated.id)
      setEditor(null)
      setReason('')
      setSuccess(message)
      feed.refresh()
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'Unable to save this alert. Please try again.',
      )
      if (caught instanceof ApiError && (caught.status === 409 || caught.status === 404)) {
        feed.refresh()
      }
    } finally {
      setBusy(false)
    }
  }

  const save = async (draft: AlertDraft) => {
    if (!token || !editor) return
    await mutate(
      () =>
        editor === 'new'
          ? createAlert(token, draft)
          : editAlert(token, editor.id, { severity: draft.severity, message: draft.message }),
      editor === 'new' ? 'Alert draft created.' : 'Alert changes saved.',
    )
  }

  const review = (action: AlertAction) => {
    if (!token || !selected || busy) return
    if (['suppress', 'resolve', 'cancel'].includes(action) && !reason.trim()) {
      setError('Enter a reason before closing this alert.')
      return
    }
    const verb = { approve: 'Approve', reject: 'Reject', suppress: 'Suppress', acknowledge: 'Acknowledge', resolve: 'Resolve', cancel: 'Cancel' }[action]
    const outcome = { approve: 'approved', reject: 'rejected', suppress: 'suppressed', acknowledge: 'acknowledged', resolve: 'resolved', cancel: 'cancelled' }[action]
    if (
      !window.confirm(
        `${verb} alert #${selected.id} for ${selected.location.name}?${action === 'approve' ? ' It will be visible to the community.' : ''}${['suppress', 'resolve', 'cancel'].includes(action) ? ` Reason: ${reason.trim()}. The record will remain in alert history.` : ''}`,
      )
    )
      return
    void mutate(
      () => reviewAlert(token, selected.id, action, reason),
      `Alert #${selected.id} ${outcome}.`,
    )
  }

  return (
    <div className="prototype-page alerts-page">
      <PageHeader
        eyebrow="MET alert operations"
        title="Alert management"
        description="Create drafts, review recommendations and manage published community alerts."
        actions={
          <button
            className="button button--primary"
            disabled={busy}
            onClick={() => {
              setEditor('new')
              setError(null)
              setSuccess(null)
            }}
          >
            New alert
          </button>
        }
      />
      <p className="alert-workflow-note">Historical analysis alerts use a separate workspace. <Link to="/simulation#simulated-alerts">Manage simulated alerts</Link></p>
      {import.meta.env.DEV && (
        <section className="prototype-panel alert-demo-controls" aria-label="Development alert scenarios">
          <strong>Simulated alert scenarios</strong>
          <p>Creates a stored prediction and a pending alert for review. These examples do not run the trained model.</p>
          <div>
            <button className="button button--secondary" disabled={busy || !token} onClick={() => {
              if (token) void mutate(() => createDemoAlert(token, 'nausori-high'), 'Nausori demo loaded. Review its status before approval.')
            }}>Create Nausori HIGH demo</button>
            <button className="button button--secondary" disabled={busy || !token} onClick={() => {
              if (token) void mutate(() => createDemoAlert(token, 'labasa-very-high'), 'Labasa demo loaded. Review its status before approval.')
            }}>Create Labasa VERY HIGH demo</button>
          </div>
          <small>Existing pending/approved scenarios are reused. Suppress a completed demo before starting it again.</small>
        </section>
      )}
      <AlertFeedStatus {...feed} />
      {error && <Alert tone="error">{error}</Alert>}
      {success && <Alert tone="success">{success}</Alert>}
      {editor && (
        <AlertEditor
          key={editor === 'new' ? 'new' : editor.id}
          alert={editor === 'new' ? undefined : editor}
          busy={busy}
          onSave={save}
          onCancel={() => setEditor(null)}
        />
      )}

      <div className="filter-pills" role="group" aria-label="Alert views">
        {(['ALL', 'ACTIVE', 'HISTORY'] as const).map(value => <button key={value} type="button" className="filter-pill" aria-pressed={view === value} disabled={busy}
          onClick={() => { setView(value); setFilter('ALL'); setReason('') }}>{value === 'ALL' ? 'All alerts' : value === 'ACTIVE' ? 'Active alerts' : 'Alert history'}</button>)}
      </div>
      <section className="alert-toolbar" aria-label="Alert filters">
        <label className="alert-search">
          <input
            type="search"
            aria-label="Search alerts"
            placeholder="Search location, ID or message"
            value={search}
            disabled={busy}
            onChange={(event) => {
              setSearch(event.target.value)
              setReason('')
            }}
          />
        </label>
        <div className="filter-pills" aria-label="Filter by alert status">
          {(['ALL', ...ALERT_STATUSES] as const).map((status) => (
            <button
              key={status}
              type="button"
              className={`filter-pill${filter === status ? ' is-active' : ''}`}
              aria-pressed={filter === status}
              disabled={busy}
              onClick={() => {
                setFilter(status)
                setReason('')
              }}
            >
              {status === 'ALL' ? 'All' : status.charAt(0) + status.slice(1).toLowerCase()}{' '}
              <span>
                {feed.data
                  ? alerts.filter((alert) => status === 'ALL' || alert.status === status).length
                  : '–'}
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="alert-workspace-grid">
        <section className="prototype-panel alert-list-panel" aria-label="Alerts">
          <header className="prototype-panel__header">
            <h2>{view === 'ACTIVE' ? 'Active alerts' : view === 'HISTORY' ? 'Alert history' : 'Review queue'}</h2>
          </header>
          {!feed.data ? (
            <div className="prototype-empty-state">
              {feed.error ? 'The alert list is unavailable.' : 'Loading alerts…'}
            </div>
          ) : filtered.length === 0 ? (
            <div className="prototype-empty-state">
              <h3>No alerts found</h3>
              <p>Create a draft or change your filters.</p>
            </div>
          ) : (
            <div className="alert-review-list">
              {filtered.map((alert) => (
                <button
                  key={alert.id}
                  type="button"
                  disabled={busy}
                  className={`alert-review-item${selected?.id === alert.id ? ' is-selected' : ''}`}
                  aria-pressed={selected?.id === alert.id}
                  onClick={() => {
                    setSelectedId(alert.id)
                    setReason('')
                    setError(null)
                  }}
                >
                  <span className="alert-review-item__heading">
                    <span>
                      <strong>{alert.location.name}</strong>
                      <small>#{alert.id}</small>
                    </span>
                    <RiskPill risk={alert.severity} compact />
                  </span>
                  <span className="alert-review-item__message">{alert.message}</span>
                  <span className="alert-review-item__footer">
                    <StatusPill status={alert.status} />{isExpiredAlert(alert) && <DataPill value="STALE" label="Expired" compact />}
                    <time dateTime={alert.created_at}>{formatRelativeTime(alert.created_at)}</time>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
        <aside
          className="prototype-panel alert-detail-panel"
          aria-label="Selected alert details"
          aria-busy={busy}
        >
          {selected ? (
            <>
              <header className="alert-detail-panel__header">
                <div>
                  <h2>{selected.location.name}</h2>
                  <small>Alert #{selected.id}</small>
                </div>
                <div><StatusPill status={selected.status} />{isExpiredAlert(selected) && <DataPill value="STALE" label="Expired" compact />}</div>
              </header>
              <div className="alert-detail-panel__body">
                <RiskPill risk={selected.severity} />
                <section className="alert-message-card">
                  <span>Alert message</span>
                  <p>{selected.message}</p>
                </section>
                <dl className="alert-detail-grid">
                  <div>
                    <dt>Source</dt>
                    <dd>
                      {isSimulatedAlert(selected) ? 'Simulated alert — not an emergency warning' : selected.source === 'AI_RECOMMENDATION'
                        ? 'AI recommendation'
                        : 'MET official'}
                    </dd>
                  </div>
                  {(
                    [
                      ['Created', selected.created_at],
                      ['Updated', selected.updated_at],
                      ['Approved', selected.approved_at],
                      ['Rejected', selected.rejected_at],
                      ['Suppressed', selected.suppressed_at],
                      ['Expires', selected.expires_at],
                      ['Acknowledged', selected.acknowledged_at],
                      ['Closed', selected.closed_at],
                    ] as const
                  ).map(
                    ([label, date]) =>
                      date && (
                        <div key={label}>
                          <dt>{label}</dt>
                          <dd>
                            <time dateTime={date}>{formatDateTime(date)}</time>
                          </dd>
                        </div>
                      ),
                  )}
                </dl>
                {!selected.location.is_active && (
                  <Alert>This location is inactive. Its alerts cannot be approved.</Alert>
                )}
                {selected.acknowledged_by_user_id && <p>Acknowledged by administrator #{selected.acknowledged_by_user_id}</p>}
                {selected.closure_reason && <p><strong>{selected.status === 'RESOLVED' ? 'Resolution' : 'Cancellation'} reason:</strong> {selected.closure_reason} · Administrator #{selected.closed_by_user_id}</p>}
                {selected.suppression_reason && (
                  <p>
                    <strong>Suppression reason:</strong> {selected.suppression_reason}
                  </p>
                )}
              </div>
              <footer className="alert-detail-actions">
                {selected.status !== 'PENDING' && <small>Only pending alerts can be edited, approved or rejected. Other records remain available for review and history.</small>}
                {selected.status === 'APPROVED' && !isExpiredAlert(selected) && <button className="button button--secondary"
                  disabled={busy || Boolean(editor) || Boolean(selected.acknowledged_at)} onClick={() => review('acknowledge')}>
                  {selected.acknowledged_at ? 'Acknowledged' : 'Acknowledge'}</button>}
                <div>
                  <button
                    className="button button--secondary"
                    disabled={busy || selected.status !== 'PENDING'}
                    onClick={() => {
                      setEditor(selected)
                      setError(null)
                      setSuccess(null)
                    }}
                  >
                    Edit alert
                  </button>
                  <button
                    className="button button--approve"
                    disabled={
                      busy ||
                      Boolean(editor) ||
                      selected.status !== 'PENDING' ||
                      !selected.location.is_active
                    }
                    onClick={() => review('approve')}
                  >
                    Approve
                  </button>
                  <button
                    className="button button--danger-quiet"
                    disabled={busy || Boolean(editor) || selected.status !== 'PENDING'}
                    onClick={() => review('reject')}
                  >
                    Reject
                  </button>
                </div>
                {(selected.status === 'PENDING' || selected.status === 'APPROVED') && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault()
                      review('suppress')
                    }}
                  >
                    <label className="form-field">
                      <span>Action reason</span>
                      <textarea
                        required
                        maxLength={1000}
                        value={reason}
                        disabled={busy || Boolean(editor)}
                        onChange={(event) => setReason(event.target.value)}
                        rows={2}
                      />
                    </label>
                    <button
                      type="submit"
                      className="button button--secondary"
                      disabled={busy || Boolean(editor) || !reason.trim()}
                    >
                      Suppress
                    </button>
                    <div className="alert-management-actions">
                      {selected.status === 'APPROVED' && <button type="button" className="button button--primary" disabled={busy || Boolean(editor) || !reason.trim()} onClick={() => review('resolve')}>Resolve</button>}
                      <button type="button" className="button button--danger-quiet" disabled={busy || Boolean(editor) || !reason.trim()} onClick={() => review('cancel')}>Cancel alert</button>
                    </div>
                    <small>Enter a reason to resolve, cancel or suppress. These actions retain the alert and its audit history.</small>
                  </form>
                )}
              </footer>
            </>
          ) : (
            <div className="prototype-empty-state">
              <h3>Select an alert</h3>
              <p>Choose an alert to inspect its details.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
