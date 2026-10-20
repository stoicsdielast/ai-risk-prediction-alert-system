import { describe, expect, it } from 'vitest'
import type { TrendPoint } from '../types/analytics'
import {
  buildChartData, countByRisk, countHighRisk, formatMetric, formatPercent, latestPoint, rangeAvailability,
  riskBands, seriesKey, verifiedConfusion,
} from './calculations'

const point = (over: Partial<TrendPoint> = {}): TrendPoint => ({
  id: 1, location_id: 1, location: 'Nausori', timestamp: '2026-10-20T00:00:00Z', probability: 0.5,
  risk_level: 'HIGH', model_version: 'm', kind: 'genuine', horizon_hours: 24, ...over,
})

describe('rangeAvailability', () => {
  it('disables ranges that would show nothing beyond the stored history', () => {
    const ranges = rangeAvailability(5)
    expect(ranges.map((r) => [r.days, r.enabled])).toEqual([[1, true], [7, true], [30, false]])
    expect(ranges[2].reason).toMatch(/7 days/)
  })
  it('keeps only the smallest range when everything fits in a day', () => {
    expect(rangeAvailability(1).map((r) => r.enabled)).toEqual([true, false, false])
  })
  it('enables the largest range when history exceeds 30 days', () => {
    expect(rangeAvailability(90).every((r) => r.enabled)).toBe(true)
  })
  it('leaves every range enabled when there is no data to filter', () => {
    expect(rangeAvailability(null).every((r) => r.enabled)).toBe(true)
  })
})

describe('buildChartData', () => {
  it('copies stored probabilities without interpolating gaps', () => {
    const { rows, series } = buildChartData([
      point({ id: 1, timestamp: '2026-10-20T00:00:00Z', probability: 0.2 }),
      point({ id: 2, timestamp: '2026-10-20T06:00:00Z', probability: 0.9 }),
      point({ id: 3, location_id: 2, location: 'Labasa', timestamp: '2026-10-20T03:00:00Z', probability: 0.4 }),
    ], [1, 2])
    expect(series.map((s) => s.location)).toEqual(['Labasa', 'Nausori'])
    expect(rows.map((r) => r.time)).toEqual([...rows.map((r) => r.time)].sort((a, b) => a - b))
    const middle = rows[1]
    expect(middle[seriesKey(2, 'genuine')]).toBe(0.4)
    expect(middle[seriesKey(1, 'genuine')]).toBeUndefined()
    expect(rows).toHaveLength(3)
  })
  it('keeps genuine, sample and synthetic values for one location in separate series', () => {
    const { series } = buildChartData([
      point({ kind: 'genuine' }), point({ id: 2, kind: 'sample' }), point({ id: 3, kind: 'synthetic' }),
    ], [1])
    expect(series.map((s) => s.kind)).toEqual(['genuine', 'sample', 'synthetic'])
  })
  it('drops unselected locations, invalid timestamps and non-finite probabilities', () => {
    const { rows, series } = buildChartData([
      point({ location_id: 9 }), point({ id: 2, timestamp: 'not-a-date' }), point({ id: 3, probability: NaN }),
    ], [1])
    expect(rows).toEqual([])
    expect(series).toEqual([])
  })
  it('returns empty data for no points', () => {
    expect(buildChartData([], [1])).toEqual({ series: [], rows: [] })
  })
})

describe('risk calculations', () => {
  const points = [
    point({ risk_level: 'LOW' }), point({ id: 2, risk_level: 'HIGH' }),
    point({ id: 3, risk_level: 'VERY_HIGH' }), point({ id: 4, risk_level: 'HIGH' }),
  ]
  it('counts every category including empty ones', () => {
    expect(countByRisk(points)).toEqual({ LOW: 1, MODERATE: 0, HIGH: 2, VERY_HIGH: 1 })
    expect(countByRisk([])).toEqual({ LOW: 0, MODERATE: 0, HIGH: 0, VERY_HIGH: 0 })
  })
  it('counts only HIGH and VERY_HIGH as high-risk', () => expect(countHighRisk(points)).toBe(3))
  it('finds the latest point regardless of input order', () => {
    const found = latestPoint([
      point({ id: 1, timestamp: '2026-10-20T05:00:00Z' }), point({ id: 2, timestamp: '2026-10-21T05:00:00Z' }),
      point({ id: 3, timestamp: '2026-10-19T05:00:00Z' }),
    ])
    expect(found?.id).toBe(2)
    expect(latestPoint([])).toBeNull()
  })
})

describe('riskBands', () => {
  it('derives contiguous bands covering 0 to 1 from V1 thresholds', () => {
    const bands = riskBands({ moderate_from: 0.2, high_from: 0.4, very_high_from: 0.6, model_version: 'v1' })!
    expect(bands.map((b) => b.level)).toEqual(['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH'])
    expect(bands[0].from).toBe(0)
    expect(bands.at(-1)!.to).toBe(1)
    bands.slice(1).forEach((band, index) => expect(band.from).toBe(bands[index].to))
  })
  it('returns null when no threshold is known rather than guessing bands', () => expect(riskBands(null)).toBeNull())
})

describe('formatting', () => {
  it('shows a dash for missing or non-finite values, never zero', () => {
    expect(formatMetric(null)).toBe('—')
    expect(formatMetric(undefined)).toBe('—')
    expect(formatMetric(NaN)).toBe('—')
    expect(formatPercent(null)).toBe('—')
    expect(formatMetric(0.34421)).toBe('0.344')
    expect(formatPercent(0.4447)).toBe('44.5%')
    expect(formatMetric(0)).toBe('0.000')
  })
})

describe('verifiedConfusion', () => {
  const base = { rows: 100, positives: 10 }
  it('accepts a matrix whose cells reproduce the artifact counts', () => {
    const confusion = { tn: 80, fp: 10, fn: 6, tp: 4 }
    expect(verifiedConfusion({ ...base, confusion })).toEqual(confusion)
  })
  it('rejects matrices that disagree with row or positive counts', () => {
    expect(verifiedConfusion({ ...base, confusion: { tn: 80, fp: 10, fn: 6, tp: 5 } })).toBeNull()
    expect(verifiedConfusion({ ...base, confusion: { tn: 80, fp: 8, fn: 2, tp: 10 } })).toBeNull() // rows sum to 100 but positives are 12, not 10
  })
  it('rejects missing, negative or fractional cells', () => {
    expect(verifiedConfusion({ ...base, confusion: null })).toBeNull()
    expect(verifiedConfusion({ ...base, confusion: { tn: 90, fp: 0, fn: -1, tp: 11 } })).toBeNull()
    expect(verifiedConfusion({ ...base, confusion: { tn: 80.5, fp: 9.5, fn: 6, tp: 4 } })).toBeNull()
  })
})
