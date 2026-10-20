import { useMemo, useState } from 'react'
import { getPredictionOverview } from '../api/analytics'
import { RANGE_OPTIONS, operationalLocationIds, rangeAvailability, storedSpanDays } from '../analytics/calculations'
import { useApiResource } from '../analytics/useApiResource'
import { PredictionOverviewPanel } from '../components/analytics/PredictionOverviewPanel'
import { PredictionTrendPanel } from '../components/analytics/PredictionTrendPanel'
import { PageHeader } from '../components/layout/PageHeader'
import { useAuth } from '../auth/useAuth'
import { useLocations } from '../locations/useLocations'
import type { TrendSource } from '../types/analytics'

export function AdminAnalyticsPage() {
  const { token } = useAuth()
  const [source, setSource] = useState<TrendSource>('operational')
  const [requestedDays, setRequestedDays] = useState<number>(7)
  const locations = useLocations()
  const overview = useApiResource(token ? (signal) => getPredictionOverview(token, requestedDays, signal) : null, [token, requestedDays])
  const ranges = rangeAvailability(storedSpanDays(overview.data, source))
  const enabledDays = ranges.filter((range) => range.enabled).map((range) => range.days)
  // A previously chosen range that stops being meaningful for this source falls back to the widest useful one.
  const days = enabledDays.includes(requestedDays) ? requestedDays : Math.max(...enabledDays)
  const rangeLabel = RANGE_OPTIONS.find((option) => option.days === days)?.label ?? `${days} days`
  const suggested = useMemo(() => {
    if (!overview.data) return []
    return source === 'synthetic' ? overview.data.synthetic.window.location_ids : operationalLocationIds(overview.data)
  }, [overview.data, source])

  return (
    <div className="analytics-page">
      <PageHeader eyebrow="MET administrator" title="Prediction analytics"
        description="Trends and summaries of stored flood-risk predictions. Every figure comes from stored records; nothing is generated for display."
        actions={
          <div className="analytics-controls">
            <div className="filter-pills" role="group" aria-label="Prediction source">
              <button type="button" className="filter-pill" aria-pressed={source === 'operational'} onClick={() => setSource('operational')}>Genuine and sample</button>
              <button type="button" className="filter-pill" aria-pressed={source === 'synthetic'} onClick={() => setSource('synthetic')}>Synthetic research</button>
            </div>
            <div className="filter-pills" role="group" aria-label="Time range">
              {ranges.map((range) => (
                <button key={range.days} type="button" className="filter-pill" aria-pressed={days === range.days}
                  disabled={!range.enabled} title={range.reason} onClick={() => setRequestedDays(range.days)}>{range.label}</button>
              ))}
            </div>
          </div>
        } />

      {overview.status === 'error' && (
        <div className="inline-alert" role="alert">
          <span>{overview.message}</span>
          <button type="button" className="button button--secondary" onClick={overview.retry}>Retry</button>
        </div>
      )}
      {!overview.data && overview.status === 'loading' && <p className="empty-state" role="status">Loading analytics…</p>}
      {overview.data && <PredictionOverviewPanel overview={overview.data} rangeLabel={rangeLabel} />}

      {token && locations.status === 'ready' && overview.data && (
        <PredictionTrendPanel token={token} source={source} days={days} locations={locations.locations} suggestedLocationIds={suggested} />
      )}
      {locations.status === 'error' && (
        <div className="inline-alert" role="alert"><span>{locations.error}</span>
          <button type="button" className="button button--secondary" onClick={locations.retry}>Retry</button></div>
      )}
    </div>
  )
}
