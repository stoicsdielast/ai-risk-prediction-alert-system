import type {
  Confusion, PredictionKind, PredictionOverview, RiskBandThresholds, StageMetrics, TrendPoint, TrendSource,
} from '../types/analytics'
import type { RiskLevel } from '../types/prototype'

export const RISK_LEVELS: RiskLevel[] = ['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH']
export const RANGE_OPTIONS: readonly { days: number; label: string }[] = [
  { days: 1, label: '24 hours' },
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
]
export const MAX_CHART_LOCATIONS = 6

/**
 * Enables every range up to and including the first one that covers all stored history.
 * Larger ranges would show exactly the same points, so they are disabled rather than implying
 * more data exists. With no stored data nothing can be filtered, so every range stays enabled.
 */
export function rangeAvailability(availableDays: number | null) {
  const firstCovering = availableDays === null
    ? null
    : RANGE_OPTIONS.find((option) => option.days >= availableDays)?.days ?? null
  return RANGE_OPTIONS.map((option) => ({
    ...option,
    enabled: firstCovering === null || option.days <= firstCovering,
    reason: firstCovering !== null && option.days > firstCovering
      ? `All stored predictions already fit within ${firstCovering === 1 ? '24 hours' : `${firstCovering} days`}`
      : undefined,
  }))
}

export interface ChartSeries {
  key: string
  locationId: number
  location: string
  kind: PredictionKind
}

export type ChartRow = { time: number } & Record<string, number | string | null | TrendPoint>

export function seriesKey(locationId: number, kind: PredictionKind) {
  return `loc${locationId}:${kind}`
}

/**
 * Pivots stored points into one chart row per timestamp. Values are copied verbatim from stored
 * predictions: nothing is interpolated, smoothed or filled, so gaps stay gaps.
 */
export function buildChartData(points: TrendPoint[], locationIds: number[]) {
  const wanted = new Set(locationIds)
  const series = new Map<string, ChartSeries>()
  const rows = new Map<number, ChartRow>()
  for (const point of points) {
    if (!wanted.has(point.location_id)) continue
    const time = Date.parse(point.timestamp)
    if (Number.isNaN(time) || !Number.isFinite(point.probability)) continue
    const key = seriesKey(point.location_id, point.kind)
    if (!series.has(key)) series.set(key, { key, locationId: point.location_id, location: point.location, kind: point.kind })
    const row = rows.get(time) ?? ({ time } as ChartRow)
    row[key] = point.probability
    row[`${key}:point`] = point
    rows.set(time, row)
  }
  return {
    series: [...series.values()].sort((a, b) => a.location.localeCompare(b.location) || a.kind.localeCompare(b.kind)),
    rows: [...rows.values()].sort((a, b) => a.time - b.time),
  }
}

export function countByRisk(points: TrendPoint[]): Record<RiskLevel, number> {
  const counts: Record<RiskLevel, number> = { LOW: 0, MODERATE: 0, HIGH: 0, VERY_HIGH: 0 }
  for (const point of points) if (point.risk_level in counts) counts[point.risk_level] += 1
  return counts
}

export const countHighRisk = (points: TrendPoint[]) =>
  points.filter((point) => point.risk_level === 'HIGH' || point.risk_level === 'VERY_HIGH').length

export function latestPoint(points: TrendPoint[]) {
  let latest: TrendPoint | null = null
  for (const point of points) {
    if (latest === null || Date.parse(point.timestamp) > Date.parse(latest.timestamp)) latest = point
  }
  return latest
}

/** Band edges (probability) for synthetic V1 research tiers, or null when no threshold is known. */
export function riskBands(thresholds: RiskBandThresholds | null) {
  if (!thresholds) return null
  return [
    { level: 'LOW' as const, from: 0, to: thresholds.moderate_from },
    { level: 'MODERATE' as const, from: thresholds.moderate_from, to: thresholds.high_from },
    { level: 'HIGH' as const, from: thresholds.high_from, to: thresholds.very_high_from },
    { level: 'VERY_HIGH' as const, from: thresholds.very_high_from, to: 1 },
  ]
}

export const formatPercent = (probability: number | null | undefined, digits = 1) =>
  probability === null || probability === undefined || !Number.isFinite(probability)
    ? '—' : `${(probability * 100).toFixed(digits)}%`

export const formatMetric = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(digits)

export const formatCount = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value.toLocaleString('en-FJ')

/** A matrix is displayed only when its cells reproduce the artifact's own row and positive counts. */
export function verifiedConfusion(metric: Pick<StageMetrics, 'confusion' | 'rows' | 'positives'>): Confusion | null {
  const c = metric.confusion
  if (!c) return null
  const cells = [c.tn, c.fp, c.fn, c.tp]
  if (cells.some((cell) => !Number.isInteger(cell) || cell < 0)) return null
  if (c.tn + c.fp + c.fn + c.tp !== metric.rows || c.fn + c.tp !== metric.positives) return null
  return c
}

export const KIND_LABELS: Record<PredictionKind, string> = {
  genuine: 'Genuine model output',
  sample: 'Sample fixture (not a model result)',
  synthetic: 'Synthetic research',
}

/**
 * Whole days of history stored for a source, taken from the overview (null when nothing is stored).
 * Operational history runs to the present; synthetic history is simulated time and ends at its latest record.
 */
export function storedSpanDays(overview: PredictionOverview | null, source: TrendSource, now = Date.now()) {
  if (!overview) return null
  const day = 86_400_000
  if (source === 'synthetic') {
    const { earliest_observed_at: first, latest_observed_at: last } = overview.synthetic
    if (!first || !last) return null
    return Math.max(Math.ceil((Date.parse(last) - Date.parse(first)) / day), 1)
  }
  const starts = overview.operational.model_versions.map((v) => (v.first_at ? Date.parse(v.first_at) : NaN)).filter(Number.isFinite)
  if (!starts.length) return null
  return Math.max(Math.ceil((now - Math.min(...starts)) / day), 1)
}

/** Union of locations with predictions in the window across the operational kinds (genuine + sample). */
export function operationalLocationIds(overview: PredictionOverview) {
  const { genuine, sample } = overview.operational.kinds
  return [...new Set([...genuine.window.location_ids, ...sample.window.location_ids])].sort((a, b) => a - b)
}
