import type { PredictionKind } from '../types/analytics'
import type { RiskLevel } from '../types/prototype'

/** Chart colours resolve from the shared CSS tokens in index.css, so a token change restyles charts. */
export const chartTheme = {
  grid: 'var(--chart-grid)',
  axis: 'var(--chart-axis)',
  text: 'var(--text)',
  surface: 'var(--surface)',
  series: ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'],
  risk: {
    LOW: 'var(--risk-low)', MODERATE: 'var(--risk-moderate)', HIGH: 'var(--risk-high)', VERY_HIGH: 'var(--risk-very-high)',
  } satisfies Record<RiskLevel, string>,
  riskBackground: {
    LOW: 'var(--risk-low-bg)', MODERATE: 'var(--risk-moderate-bg)', HIGH: 'var(--risk-high-bg)',
    VERY_HIGH: 'var(--risk-very-high-bg)',
  } satisfies Record<RiskLevel, string>,
}

/** Line style encodes provenance so it survives greyscale printing: solid, dashed, dotted. */
export const kindDash: Record<PredictionKind, string | undefined> = {
  genuine: undefined, sample: '6 4', synthetic: '2 4',
}
