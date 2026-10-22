import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { chartTheme } from '../../analytics/chartTheme'
import { formatCount, formatMetric, formatPercent, verifiedConfusion } from '../../analytics/calculations'
import type { RunSummary, StageMetrics } from '../../types/analytics'
import { DataPill } from '../pills/DataPill'
import { StatCard } from './StatCard'

export function MetricCards({ metric }: { metric: StageMetrics }) {
  return (
    <div className="stat-grid stat-grid--five">
      <StatCard label="Precision" value={formatMetric(metric.precision)} detail="Share of raised alarms that were floods" />
      <StatCard label="Recall" value={formatMetric(metric.recall)} detail="Share of flood-hours detected" />
      <StatCard label="F1 score" value={formatMetric(metric.f1)} detail="Harmonic mean of precision and recall" />
      <StatCard label="PR-AUC" value={formatMetric(metric.pr_auc)} detail={`Chance level equals prevalence (${formatPercent(metric.prevalence, 2)})`} />
      <StatCard label="ROC-AUC" value={formatMetric(metric.roc_auc)} detail="Can look high under heavy class imbalance" />
    </div>
  )
}

export function ConfusionMatrix({ metric }: { metric: StageMetrics }) {
  const matrix = verifiedConfusion(metric)
  if (!matrix) {
    return <p className="empty-state">No verified confusion matrix: the saved counts are missing or do not add up to this partition.</p>
  }
  return (
    <table className="confusion-matrix" aria-label={`Confusion matrix, ${metric.description}`}>
      <caption>Counts at the saved decision threshold · {metric.description} · {formatCount(metric.rows)} rows</caption>
      <thead>
        <tr><td /><th scope="col">Predicted no flood</th><th scope="col">Predicted flood</th></tr>
      </thead>
      <tbody>
        <tr><th scope="row">Actual no flood</th><td data-cell="tn">{formatCount(matrix.tn)}</td><td data-cell="fp" className="is-error">{formatCount(matrix.fp)}</td></tr>
        <tr><th scope="row">Actual flood</th><td data-cell="fn" className="is-error">{formatCount(matrix.fn)}</td><td data-cell="tp">{formatCount(matrix.tp)}</td></tr>
      </tbody>
    </table>
  )
}

export function FeatureImportanceChart({ run }: { run: RunSummary }) {
  const data = run.feature_importance ?? []
  if (!data.length) return <p className="empty-state">No feature importance was saved for this model.</p>
  return (
    <div role="img" aria-label="Bar chart of the selected model's top feature importances">
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 26)} initialDimension={{ width: 720, height: 360 }}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={chartTheme.grid} horizontal={false} />
          <XAxis type="number" tickFormatter={(value: number) => `${value}%`} stroke={chartTheme.axis} tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="feature" width={200} stroke={chartTheme.axis} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} isAnimationActive={false} />
          <Bar dataKey="share_percent" name="Share of total importance" fill="var(--chart-1)" radius={[0, 3, 3, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-caption">{run.feature_importance_method} Importance reflects how the model splits on a feature; it is not a causal effect.</p>
    </div>
  )
}

export function StageTable({ metrics }: { metrics: StageMetrics[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>Partition</th><th>Rows</th><th>Flood positives</th><th>Precision</th><th>Recall</th><th>F1</th><th>PR-AUC</th><th>ROC-AUC</th><th>Event recall</th></tr></thead>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.stage}>
              <td>{metric.description}<small className="data-table__sub">{metric.stage}</small></td>
              <td>{formatCount(metric.rows)}</td><td>{formatCount(metric.positives)}</td>
              <td>{formatMetric(metric.precision)}</td><td>{formatMetric(metric.recall)}</td><td>{formatMetric(metric.f1)}</td>
              <td>{formatMetric(metric.pr_auc)}</td><td>{formatMetric(metric.roc_auc)}</td><td>{formatMetric(metric.event_recall)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One row per experiment at the same partition kind; datasets and sizes are shown so rows are not read as a ranking. */
export function ExperimentTable({ runs, stage }: { runs: RunSummary[]; stage: string }) {
  return (
    <div className="table-scroll">
      <table className="data-table" aria-label="Research experiment results">
        <thead>
          <tr><th>Experiment</th><th>Status</th><th>Dataset fingerprint</th><th>Selected model</th><th>Partition</th><th>Rows</th><th>Positives</th><th>Precision</th><th>Recall</th><th>F1</th><th>PR-AUC</th><th>ROC-AUC</th></tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const metric = run.metrics?.find((item) => item.stage === stage)
            if (!run.available || !metric) {
              return <tr key={run.key}><td>{run.label}</td><td>{run.role}</td><td colSpan={10} className="empty-cell">{run.reason ?? 'No saved results for this partition.'}</td></tr>
            }
            return (
              <tr key={run.key}>
                <td>{run.label}</td>
                <td>{run.role === 'deployed' ? <DataPill value="AI_PREDICTION" label="Deployed" compact /> : <DataPill value="SYNTHETIC_PREDICTION" label="Research only" compact />}</td>
                <td className="data-table__mono">{run.dataset_sha256?.slice(0, 8) ?? '—'}</td>
                <td className="data-table__mono">{run.selected_candidate}</td>
                <td>{metric.description}</td>
                <td>{formatCount(metric.rows)}</td><td>{formatCount(metric.positives)}</td>
                <td>{formatMetric(metric.precision)}</td><td>{formatMetric(metric.recall)}</td><td>{formatMetric(metric.f1)}</td>
                <td>{formatMetric(metric.pr_auc)}</td><td>{formatMetric(metric.roc_auc)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
