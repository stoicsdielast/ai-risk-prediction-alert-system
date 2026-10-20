import { RISK_LEVELS, formatCount, operationalLocationIds } from '../../analytics/calculations'
import type { PredictionOverview } from '../../types/analytics'
import { formatDateTime, formatRelativeTime } from '../../utils/date'
import { DataPill, RiskPill } from '../pills/DataPill'
import { StatCard } from './StatCard'

export function PredictionOverviewPanel({ overview, rangeLabel }: { overview: PredictionOverview; rangeLabel: string }) {
  const { genuine, sample } = overview.operational.kinds
  const synthetic = overview.synthetic
  const operationalTotal = genuine.total + sample.total
  const recentLocations = operationalLocationIds(overview).length
  const highRisk = genuine.window.high_risk + sample.window.high_risk
  const latest = genuine.freshness.latest_at
  return (
    <section aria-label="Prediction analytics overview" className="analytics-section">
      <div className="stat-grid">
        <StatCard label="Stored predictions" value={formatCount(operationalTotal)}
          detail={`${formatCount(genuine.total)} genuine · ${formatCount(sample.total)} sample. Synthetic research: ${formatCount(synthetic.total)} (separate store).`} />
        <StatCard label="Latest genuine prediction"
          value={latest ? formatRelativeTime(latest) : 'None stored'}
          badge={genuine.freshness.stale ? <DataPill value="STALE" label={`Stale · over ${genuine.freshness.stale_after_hours} h old`} /> : undefined}
          detail={latest ? formatDateTime(latest)
            : sample.freshness.latest_at ? `Latest sample fixture: ${formatDateTime(sample.freshness.latest_at)}` : 'No stored predictions'} />
        <StatCard label={`Locations with predictions (${rangeLabel})`} value={`${recentLocations} of ${overview.monitored_locations}`}
          detail="Active monitored locations with at least one stored genuine or sample prediction in range." />
        <StatCard label={`High-risk predictions (${rangeLabel})`} value={formatCount(highRisk)}
          detail={`HIGH or VERY HIGH · ${formatCount(genuine.window.high_risk)} genuine, ${formatCount(sample.window.high_risk)} sample, ${formatCount(synthetic.window.high_risk)} synthetic`} />
      </div>

      <div className="analytics-columns">
        <div className="prototype-panel">
          <div className="prototype-panel__header">
            <div><h2>Stored predictions by risk category</h2><p>All stored records; categories are as stored, never recomputed.</p></div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Risk</th><th>Genuine</th><th>Sample</th><th>Synthetic research</th></tr></thead>
              <tbody>
                {RISK_LEVELS.map((level) => (
                  <tr key={level}>
                    <td><RiskPill risk={level} compact /></td>
                    <td>{formatCount(genuine.by_risk[level])}</td>
                    <td>{formatCount(sample.by_risk[level])}</td>
                    <td>{formatCount(synthetic.by_risk[level])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="prototype-panel">
          <div className="prototype-panel__header">
            <div><h2>Data freshness and model provenance</h2><p>Every stored prediction group and the model that produced it.</p></div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Source</th><th>Model version</th><th>Records</th><th>Latest</th></tr></thead>
              <tbody>
                {overview.operational.model_versions.map((row) => (
                  <tr key={`${row.kind}:${row.model_version}`}>
                    <td>{row.kind === 'genuine' ? <DataPill value="AI_PREDICTION" label="Genuine" compact />
                      : <DataPill value="SAMPLE_RISK" label={row.alert_workflow_demo ? 'Sample · alert demo' : 'Sample'} compact />}</td>
                    <td className="data-table__mono">{row.model_version}</td>
                    <td>{formatCount(row.predictions)}</td>
                    <td>{row.last_at ? formatDateTime(row.last_at) : '—'}</td>
                  </tr>
                ))}
                {synthetic.model_versions.map((row) => (
                  <tr key={`syn:${row.model_version}:${row.dataset_version}`}>
                    <td><DataPill value="SYNTHETIC_PREDICTION" compact /></td>
                    <td className="data-table__mono">{row.model_version}</td>
                    <td>{formatCount(row.predictions)}</td>
                    <td>{synthetic.latest_observed_at ? `${formatDateTime(synthetic.latest_observed_at)} (simulated)` : '—'}</td>
                  </tr>
                ))}
                {!overview.operational.model_versions.length && !synthetic.model_versions.length && (
                  <tr><td colSpan={4} className="empty-cell">No predictions are stored yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}
