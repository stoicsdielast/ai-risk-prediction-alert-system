import { useMemo, useState } from 'react'
import { getPredictionTrend } from '../../api/analytics'
import {
  KIND_LABELS, MAX_CHART_LOCATIONS, buildChartData, countByRisk, countHighRisk, formatPercent, latestPoint,
} from '../../analytics/calculations'
import { useApiResource } from '../../analytics/useApiResource'
import type { PredictionKind, TrendSource } from '../../types/analytics'
import type { ApiLocation } from '../../types/location'
import { formatDateTime } from '../../utils/date'
import { DataPill, RiskPill } from '../pills/DataPill'
import { StatCard } from './StatCard'
import { TrendChart } from './TrendChart'

interface Props {
  token: string
  source: TrendSource
  days: number
  locations: ApiLocation[]
  /** Locations that actually have stored predictions in range, used as the starting selection. */
  suggestedLocationIds: number[]
}

const PAGE = 25

function KindPill({ kind }: { kind: PredictionKind }) {
  if (kind === 'genuine') return <DataPill value="AI_PREDICTION" label="Genuine" compact />
  if (kind === 'sample') return <DataPill value="SAMPLE_RISK" label="Sample" compact />
  return <DataPill value="SYNTHETIC_PREDICTION" compact />
}

export function PredictionTrendPanel({ token, source, days, locations, suggestedLocationIds }: Props) {
  // null means "no explicit choice yet": fall back to locations that have data. Reset when the source changes.
  const [choice, setChoice] = useState<{ source: TrendSource; ids: number[] } | null>(null)
  const [visible, setVisible] = useState(PAGE)
  const selected = useMemo(() => {
    const ids = choice && choice.source === source ? choice.ids : suggestedLocationIds
    return ids.filter((id) => locations.some((location) => location.id === id)).slice(0, MAX_CHART_LOCATIONS)
  }, [choice, source, suggestedLocationIds, locations])
  const key = selected.join(',')
  const trend = useApiResource(
    selected.length ? (signal) => getPredictionTrend(token, source, days, selected, signal) : null,
    [token, source, days, key],
  )
  const data = trend.data
  const { rows, series } = useMemo(() => buildChartData(data?.points ?? [], selected), [data, selected])
  const points = useMemo(() => data?.points ?? [], [data])
  const newestFirst = useMemo(() => [...points].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)), [points])
  const latest = latestPoint(points)
  const risk = countByRisk(points)
  const hasSample = points.some((point) => point.kind === 'sample')

  function toggle(id: number, checked: boolean) {
    const next = checked ? [...selected, id] : selected.filter((value) => value !== id)
    setChoice({ source, ids: next })
    setVisible(PAGE)
  }

  return (
    <section className="prototype-panel analytics-trend" aria-label="Prediction trends">
      <div className="prototype-panel__header">
        <div>
          <h2>Flood-risk probability over time</h2>
          <p>
            {source === 'synthetic' ? 'Synthetic research predictions (simulated time). ' : 'Stored operational predictions. '}
            Probability of flood onset within the next 24 hours; not a calibrated confidence score.
          </p>
        </div>
      </div>

      <fieldset className="location-picker">
        <legend>Monitored locations <span>({selected.length} of {MAX_CHART_LOCATIONS} max selected)</span></legend>
        <div className="location-picker__grid">
          {locations.map((location) => {
            const checked = selected.includes(location.id)
            return (
              <label key={location.id} className={checked ? 'is-checked' : undefined}>
                <input type="checkbox" checked={checked} disabled={!checked && selected.length >= MAX_CHART_LOCATIONS}
                  onChange={(event) => toggle(location.id, event.target.checked)} />
                {location.name}
                {suggestedLocationIds.includes(location.id) && <small> · has data</small>}
              </label>
            )
          })}
        </div>
      </fieldset>

      <div className="analytics-trend__body">
        {!selected.length && <p className="empty-state">Select at least one monitored location to plot its stored predictions.</p>}
        {selected.length > 0 && trend.status === 'error' && (
          <div className="inline-alert" role="alert">
            <span>{trend.message}</span>
            <button type="button" className="button button--secondary" onClick={trend.retry}>Retry</button>
          </div>
        )}
        {selected.length > 0 && !data && trend.status === 'loading' && <p className="empty-state" role="status">Loading stored predictions…</p>}

        {data && (
          <>
            <div className="notice-stack">
              {data.freshness?.stale && (
                <p className="notice notice--warning"><DataPill value="STALE" compact /> The latest stored prediction is {Math.round(data.freshness.age_hours ?? 0)} hours old (stale after {data.freshness.stale_after_hours} h). Values shown are historical, not current conditions.</p>
              )}
              {hasSample && <p className="notice notice--info"><DataPill value="SAMPLE_RISK" compact /> Sample points are seeded workflow fixtures, not model results, and claim no forecast horizon.</p>}
              {data.source === 'synthetic' && data.notice && <p className="notice notice--info"><DataPill value="SYNTHETIC_PREDICTION" compact /> {data.notice} The time window ends at the latest synthetic record ({data.window_end ? formatDateTime(data.window_end) : 'none'}), not today.</p>}
              {points.length > 0 && points.length < 3 && <p className="notice notice--info">Sparse history: only {points.length} stored prediction{points.length === 1 ? '' : 's'} in this range. Lines connect consecutive stored values and do not imply readings in between.</p>}
              {data.truncated && <p className="notice notice--warning">Showing the first {data.max_points.toLocaleString('en-FJ')} stored predictions in range; narrow the range or locations to see the rest.</p>}
              {trend.status === 'error' && <p className="notice notice--warning">Could not refresh: {trend.message} Showing the last loaded data.</p>}
            </div>

            {points.length === 0 ? (
              <p className="empty-state" role="status">
                No stored predictions for the selected locations in this range.
                {data.data_span.stored_predictions > 0
                  ? ` ${data.data_span.stored_predictions} stored outside it (earliest ${formatDateTime(data.data_span.earliest!)}, latest ${formatDateTime(data.data_span.latest!)}).`
                  : ' None are stored for these locations yet. No values are generated to fill the chart.'}
              </p>
            ) : (
              <>
                <div className="stat-grid stat-grid--compact">
                  <StatCard label="Predictions in range" value={points.length} detail={`${data.locations.length} location${data.locations.length === 1 ? '' : 's'} selected`} />
                  <StatCard label="High-risk" value={countHighRisk(points)} detail={`HIGH or VERY HIGH · low ${risk.LOW}, moderate ${risk.MODERATE}`} />
                  <StatCard label="Latest in range" value={latest ? formatPercent(latest.probability) : '—'}
                    detail={latest ? `${latest.location} · ${formatDateTime(latest.timestamp)}` : undefined}
                    badge={latest ? <RiskPill risk={latest.risk_level} compact /> : undefined} />
                </div>
                <TrendChart rows={rows} series={series} windowStart={data.window_start} windowEnd={data.window_end}
                  bands={data.risk_band_thresholds} days={days} />
                {data.risk_band_thresholds && (
                  <p className="chart-caption">Shaded bands are the V1 research risk tiers derived from the deployed threshold ({formatPercent(data.risk_band_thresholds.high_from, 2)}); model {data.risk_band_thresholds.model_version}.</p>
                )}
                <div className="table-scroll">
                  <table className="data-table">
                    <thead><tr><th>Predicted at</th><th>Location</th><th>Probability</th><th>Risk</th><th>Source</th><th>Model version</th><th>Horizon</th></tr></thead>
                    <tbody>
                      {newestFirst.slice(0, visible).map((point) => (
                        <tr key={`${point.kind}:${point.id}`}>
                          <td>{formatDateTime(point.timestamp)}</td>
                          <td>{point.location}</td>
                          <td>{formatPercent(point.probability)}</td>
                          <td><RiskPill risk={point.risk_level} compact /></td>
                          <td><KindPill kind={point.kind} /><span className="sr-only">{KIND_LABELS[point.kind]}</span></td>
                          <td className="data-table__mono">{point.model_version}</td>
                          <td>{point.horizon_hours ? `${point.horizon_hours} h` : 'n/a'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {visible < newestFirst.length && (
                  <button type="button" className="button button--secondary" onClick={() => setVisible(visible + PAGE)}>
                    Show more ({newestFirst.length - visible} remaining)
                  </button>
                )}
              </>
            )}
          </>
        )}
      </div>
    </section>
  )
}
