import { useState } from 'react'
import { ALERT_STATUSES, createAlert, editAlert, reviewAlert } from '../api/alerts'
import { ApiError } from '../api/client'
import { useAdminAlerts, useAdminRequest } from '../alerts/useAlertFeed'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { AlertEditor } from '../components/alerts/AlertEditor'
import { AlertFeedStatus } from '../components/alerts/AlertFeedStatus'
import { PageHeader } from '../components/layout/PageHeader'
import { RiskPill, StatusPill } from '../components/pills/DataPill'
import type { AdminAlert, AlertAction, AlertDraft } from '../types/alert'
import type { AlertStatus } from '../types/prototype'
import { formatDateTime, formatRelativeTime } from '../utils/date'

export function AlertsDashboardPage() {
  const { token } = useAuth()
  const feed = useAdminAlerts()
  const request = useAdminRequest()
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
    if (action === 'suppress' && !reason.trim()) {
      setError('Enter a reason before suppressing this alert.')
      return
    }
    const verb = { approve: 'Approve', reject: 'Reject', suppress: 'Suppress' }[action]
    if (
      !window.confirm(
        `${verb} alert #${selected.id} for ${selected.location.name}?${action === 'approve' ? ' It will be visible to the community.' : ''}`,
      )
    )
      return
    void mutate(
      () => reviewAlert(token, selected.id, action, reason),
      `Alert #${selected.id} ${action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'suppressed'}.`,
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
            <h2>Review queue</h2>
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
                    <StatusPill status={alert.status} />
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
                <StatusPill status={selected.status} />
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
                      {selected.source === 'AI_RECOMMENDATION'
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
                {selected.suppression_reason && (
                  <p>
                    <strong>Suppression reason:</strong> {selected.suppression_reason}
                  </p>
                )}
              </div>
              <footer className="alert-detail-actions">
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
                      <span>Suppression reason</span>
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
