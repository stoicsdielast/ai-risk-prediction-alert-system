import { Alert } from '../Alert'
import { formatDateTime } from '../../utils/date'

interface Props {
  error: string | null
  refreshing: boolean
  updatedAt: string | null
  refresh: () => void
}

export function AlertFeedStatus({ error, refreshing, updatedAt, refresh }: Props) {
  return (
    <div className="alert-feed-status">
      {error && (
        <Alert tone="error">
          {error}
          {updatedAt && ' Displayed alerts may be out of date.'}
        </Alert>
      )}
      <div className="alert-feed-status__controls">
        <p aria-live="polite">
          {refreshing ? (
            'Refreshing alerts…'
          ) : updatedAt ? (
            <>
              Last checked <time dateTime={updatedAt}>{formatDateTime(updatedAt)}</time>. Refreshes
              every 30 seconds.
            </>
          ) : (
            'Alerts are unavailable.'
          )}
        </p>
        <button
          type="button"
          className="button button--secondary"
          disabled={refreshing}
          onClick={refresh}
        >
          Refresh alerts
        </button>
      </div>
    </div>
  )
}
