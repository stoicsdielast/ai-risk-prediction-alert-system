import {
  CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { chartTheme, kindDash } from '../../analytics/chartTheme'
import {
  KIND_LABELS, formatPercent, riskBands, type ChartRow, type ChartSeries,
} from '../../analytics/calculations'
import type { RiskBandThresholds, TrendPoint } from '../../types/analytics'
import { formatDateTime } from '../../utils/date'

interface TrendChartProps {
  rows: ChartRow[]
  series: ChartSeries[]
  windowStart: string | null
  windowEnd: string | null
  bands: RiskBandThresholds | null
  /** Short window labels show clock times; longer windows show dates. */
  days: number
}

const tick = (days: number) => (value: number) =>
  new Intl.DateTimeFormat('en-FJ', days <= 1
    ? { hour: '2-digit', minute: '2-digit', timeZone: 'Pacific/Fiji' }
    : { day: 'numeric', month: 'short', timeZone: 'Pacific/Fiji' }).format(new Date(value))

interface TooltipEntry { dataKey?: string | number; payload?: ChartRow }

function TrendTooltip({ active, payload }: { active?: boolean; payload?: TooltipEntry[] }) {
  if (!active || !payload?.length) return null
  const points = payload
    .map((entry) => entry.payload?.[`${String(entry.dataKey)}:point`] as TrendPoint | undefined)
    .filter((point): point is TrendPoint => Boolean(point))
  if (!points.length) return null
  return (
    <div className="chart-tooltip" role="presentation">
      <strong>{formatDateTime(points[0].timestamp)}</strong>
      {points.map((point) => (
        <div key={point.id} className="chart-tooltip__entry">
          <span>{point.location} · {KIND_LABELS[point.kind]}</span>
          <span>{formatPercent(point.probability)} · {point.risk_level.replace('_', ' ')}</span>
          <small>
            Model {point.model_version} · horizon {point.horizon_hours ? `${point.horizon_hours} h` : 'not applicable'}
          </small>
        </div>
      ))}
    </div>
  )
}

export function TrendChart({ rows, series, windowStart, windowEnd, bands, days }: TrendChartProps) {
  const start = windowStart ? Date.parse(windowStart) : NaN
  const end = windowEnd ? Date.parse(windowEnd) : NaN
  const domain: [number | string, number | string] = Number.isFinite(start) && Number.isFinite(end)
    ? [start, end] : ['dataMin', 'dataMax']
  const shaded = riskBands(bands)
  const locationOrder = [...new Set(series.map((item) => item.locationId))]
  return (
    <div className="trend-chart" role="img" aria-label="Line chart of stored flood-risk probability over time">
      <ResponsiveContainer width="100%" height={340} initialDimension={{ width: 720, height: 340 }}>
        <ComposedChart data={rows} margin={{ top: 12, right: 20, bottom: 4, left: 0 }}>
          {shaded?.map((band) => (
            <ReferenceArea key={band.level} y1={band.from} y2={band.to} ifOverflow="hidden"
              fill={chartTheme.riskBackground[band.level]} fillOpacity={0.9} stroke="none" />
          ))}
          <CartesianGrid stroke={chartTheme.grid} vertical={false} />
          <XAxis dataKey="time" type="number" scale="time" domain={domain} tickFormatter={tick(days)}
            stroke={chartTheme.axis} tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
            stroke={chartTheme.axis} tick={{ fontSize: 12 }} width={48} />
          <Tooltip content={<TrendTooltip />} isAnimationActive={false} />
          {series.map((item) => {
            const colour = chartTheme.series[locationOrder.indexOf(item.locationId) % chartTheme.series.length]
            return (
              <Line key={item.key} dataKey={item.key} name={`${item.location} · ${KIND_LABELS[item.kind]}`}
                type="linear" stroke={colour} strokeWidth={2} strokeDasharray={kindDash[item.kind]}
                connectNulls isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; payload?: ChartRow; index?: number }) => {
                  const point = props.payload?.[`${item.key}:point`] as TrendPoint | undefined
                  if (!point || props.cx === undefined || props.cy === undefined) return <g key={`empty-${props.index}`} />
                  return <circle key={point.id} data-testid="trend-dot" data-risk={point.risk_level}
                    cx={props.cx} cy={props.cy} r={5} fill={chartTheme.risk[point.risk_level]}
                    stroke={chartTheme.surface} strokeWidth={1.5} />
                }}
                activeDot={{ r: 7 }} />
            )
          })}
        </ComposedChart>
      </ResponsiveContainer>
      <ul className="trend-chart__legend" aria-label="Chart legend">
        {series.map((item) => (
          <li key={item.key}>
            <svg width="28" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="28" y2="4" stroke={chartTheme.series[locationOrder.indexOf(item.locationId) % chartTheme.series.length]}
                strokeWidth="2" strokeDasharray={kindDash[item.kind]} />
            </svg>
            {item.location} · {KIND_LABELS[item.kind]}
          </li>
        ))}
      </ul>
    </div>
  )
}
