import { useMemo, useState } from 'react'
import { Alert } from '../components/Alert'
import { PageHeader } from '../components/layout/PageHeader'
import { DataPill, RiskPill, StatusPill } from '../components/pills/DataPill'
import { usePrototypeData } from '../prototype/usePrototypeData'
import type { AlertRecord, AlertStatus } from '../types/prototype'
import { formatDateTime, formatRelativeTime } from '../utils/date'

type AlertFilter = 'ALL' | AlertStatus

const FILTERS: Array<{ value: AlertFilter; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'SUPPRESSED', label: 'Suppressed' },
]

const ACTION_COPY: Record<
  Extract<AlertStatus, 'APPROVED' | 'REJECTED' | 'SUPPRESSED'>,
  { present: string; progress: string; past: string }
> = {
  APPROVED: { present: 'Approve', progress: 'Approving…', past: 'approved' },
  REJECTED: { present: 'Reject', progress: 'Rejecting…', past: 'rejected' },
  SUPPRESSED: { present: 'Suppress', progress: 'Suppressing…', past: 'suppressed' },
}

function alertSourceValue(alert: AlertRecord) {
  return alert.source === 'AI_RECOMMENDATION'
    ? ('AI_PREDICTION' as const)
    : ('OFFICIAL_WARNING' as const)
}

export function AlertsDashboardPage() {
  const { alerts, updateAlertStatus } = usePrototypeData()
  const [filter, setFilter] = useState<AlertFilter>('ALL')
  const [search, setSearch] = useState('')
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(
    alerts[0]?.id ?? null,
  )
  const [actionStatus, setActionStatus] = useState<AlertStatus | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const filteredAlerts = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return alerts.filter((alert) => {
      const matchesStatus = filter === 'ALL' || alert.status === filter
      const matchesSearch =
        normalizedSearch.length === 0 ||
        alert.locationName.toLowerCase().includes(normalizedSearch) ||
        alert.id.toLowerCase().includes(normalizedSearch) ||
        alert.message.toLowerCase().includes(normalizedSearch)

      return matchesStatus && matchesSearch
    })
  }, [alerts, filter, search])

  const selectedAlert =
    filteredAlerts.find((alert) => alert.id === selectedAlertId) ??
    filteredAlerts[0] ??
    null

  const filterCount = (value: AlertFilter) =>
    value === 'ALL'
      ? alerts.length
      : alerts.filter((alert) => alert.status === value).length

  const selectAlert = (alertId: string) => {
    setSelectedAlertId(alertId)
    setSuccess(null)
    setError(null)
  }

  const changeAlertStatus = async (
    targetStatus: Extract<AlertStatus, 'APPROVED' | 'REJECTED' | 'SUPPRESSED'>,
  ) => {
    if (!selectedAlert || actionStatus) return

    const copy = ACTION_COPY[targetStatus]
    const confirmed = window.confirm(
      `${copy.present} ${selectedAlert.id} for ${selectedAlert.locationName}?\n\n` +
        'This prototype action updates local demo data only and resets when the page reloads.',
    )
    if (!confirmed) return

    setActionStatus(targetStatus)
    setSuccess(null)
    setError(null)

    try {
      const updatedAlert = await updateAlertStatus(selectedAlert.id, targetStatus)
      setSuccess(
        `${updatedAlert.id} was ${copy.past}. This demo-only change is not saved to the backend.`,
      )
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'Unable to update this alert. Please try again.',
      )
    } finally {
      setActionStatus(null)
    }
  }

  const resetFilters = () => {
    setFilter('ALL')
    setSearch('')
  }

  return (
    <div className="prototype-page alerts-page">
      <PageHeader
        eyebrow="MET alert operations"
        title="Alert management"
        description="Review AI recommendations and manage which flood alerts are ready for public use."
      />

      <div className="prototype-notice" role="note">
        <span aria-hidden="true">i</span>
        <p>
          <strong>Prototype workflow:</strong> alert actions update this browser session
          only. No alert-management API or database persistence is connected yet.
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {success && <Alert tone="success">{success}</Alert>}

      <section className="alert-toolbar" aria-label="Alert filters">
        <label className="alert-search">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
            <path
              d="m16 16 4 4"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
          <input
            type="search"
            aria-label="Search alerts"
            value={search}
            placeholder="Search location, ID or message"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <div className="filter-pills" aria-label="Filter by alert status">
          {FILTERS.map((item) => (
            <button
              className={`filter-pill${filter === item.value ? ' is-active' : ''}`}
              type="button"
              key={item.value}
              aria-pressed={filter === item.value}
              onClick={() => setFilter(item.value)}
            >
              {item.label} <span>{filterCount(item.value)}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="alert-workspace-grid">
        <section className="prototype-panel alert-list-panel" aria-label="Alerts">
          <header className="prototype-panel__header">
            <div>
              <span>Review queue</span>
              <h2>
                Alerts <small>{filteredAlerts.length}</small>
              </h2>
            </div>
          </header>

          {filteredAlerts.length === 0 ? (
            <div className="prototype-empty-state alert-list-empty">
              <span aria-hidden="true">⌕</span>
              <h3>No alerts found</h3>
              <p>Try a different status or search term.</p>
              <button className="button button--secondary" type="button" onClick={resetFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <div className="alert-review-list">
              {filteredAlerts.map((alert) => (
                <button
                  className={`alert-review-item${
                    selectedAlert?.id === alert.id ? ' is-selected' : ''
                  }`}
                  type="button"
                  key={alert.id}
                  aria-pressed={selectedAlert?.id === alert.id}
                  onClick={() => selectAlert(alert.id)}
                >
                  <span className="alert-review-item__heading">
                    <span>
                      <strong>{alert.locationName}</strong>
                      <small>{alert.id}</small>
                    </span>
                    <RiskPill risk={alert.severity} compact />
                  </span>
                  <span className="alert-review-item__message">{alert.message}</span>
                  <span className="alert-review-item__footer">
                    <StatusPill status={alert.status} />
                    <time dateTime={alert.createdAt}>
                      {formatRelativeTime(alert.createdAt)}
                    </time>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <aside
          className="prototype-panel alert-detail-panel"
          aria-label="Selected alert details"
          aria-busy={actionStatus !== null}
        >
          {selectedAlert ? (
            <>
              <header className="alert-detail-panel__header">
                <div>
                  <span>Alert detail</span>
                  <h2>{selectedAlert.locationName}</h2>
                  <small>{selectedAlert.id}</small>
                </div>
                <StatusPill status={selectedAlert.status} />
              </header>

              <div className="alert-detail-panel__body">
                <div className="alert-detail-pills">
                  <RiskPill risk={selectedAlert.severity} />
                  <DataPill value={alertSourceValue(selectedAlert)} />
                </div>

                <section className="alert-message-card">
                  <span>Alert message</span>
                  <p>{selectedAlert.message}</p>
                </section>

                <dl className="alert-detail-grid">
                  <div>
                    <dt>Location</dt>
                    <dd>{selectedAlert.locationName}</dd>
                  </div>
                  <div>
                    <dt>Severity</dt>
                    <dd>{selectedAlert.severity.replace('_', ' ')}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>
                      <time dateTime={selectedAlert.createdAt}>
                        {formatDateTime(selectedAlert.createdAt)}
                      </time>
                    </dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>
                      {selectedAlert.source === 'AI_RECOMMENDATION'
                        ? 'AI recommendation'
                        : 'MET official'}
                    </dd>
                  </div>
                </dl>
              </div>

              <footer className="alert-detail-actions">
                <p>Choose an operational review action for this demo alert.</p>
                <div>
                  <button
                    className="button button--approve"
                    type="button"
                    disabled={selectedAlert.status !== 'PENDING' || actionStatus !== null}
                    onClick={() => changeAlertStatus('APPROVED')}
                  >
                    {actionStatus === 'APPROVED'
                      ? ACTION_COPY.APPROVED.progress
                      : ACTION_COPY.APPROVED.present}
                  </button>
                  <button
                    className="button button--danger-quiet"
                    type="button"
                    disabled={selectedAlert.status !== 'PENDING' || actionStatus !== null}
                    onClick={() => changeAlertStatus('REJECTED')}
                  >
                    {actionStatus === 'REJECTED'
                      ? ACTION_COPY.REJECTED.progress
                      : ACTION_COPY.REJECTED.present}
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={
                      selectedAlert.status === 'REJECTED' ||
                      selectedAlert.status === 'SUPPRESSED' ||
                      actionStatus !== null
                    }
                    onClick={() => changeAlertStatus('SUPPRESSED')}
                  >
                    {actionStatus === 'SUPPRESSED'
                      ? ACTION_COPY.SUPPRESSED.progress
                      : ACTION_COPY.SUPPRESSED.present}
                  </button>
                </div>
              </footer>
            </>
          ) : (
            <div className="prototype-empty-state alert-detail-empty">
              <h3>Select an alert</h3>
              <p>Choose an item from the review queue to inspect its details.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
