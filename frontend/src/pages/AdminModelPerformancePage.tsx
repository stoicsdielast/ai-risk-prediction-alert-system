import { useState } from 'react'
import { getModelPerformance } from '../api/analytics'
import { formatCount, formatMetric } from '../analytics/calculations'
import { useApiResource } from '../analytics/useApiResource'
import {
  ConfusionMatrix, ExperimentTable, FeatureImportanceChart, MetricCards, StageTable,
} from '../components/analytics/ModelPerformancePanels'
import { StatCard } from '../components/analytics/StatCard'
import { PageHeader } from '../components/layout/PageHeader'
import { DataPill } from '../components/pills/DataPill'
import { useAuth } from '../auth/useAuth'
import { formatDateTime } from '../utils/date'

const HEADLINE_STAGE = 'test'

export function AdminModelPerformancePage() {
  const { token } = useAuth()
  const resource = useApiResource(token ? (signal) => getModelPerformance(token, signal) : null, [token])
  const [chosenStage, setChosenStage] = useState<string | null>(null)
  const data = resource.data
  const v1 = data?.v1
  const stages = v1?.metrics ?? []
  const stage = stages.find((item) => item.stage === (chosenStage ?? HEADLINE_STAGE)) ?? stages[0]
  const train = v1?.partitions?.find((item) => item.stage === 'train')
  const test = v1?.partitions?.find((item) => item.stage === 'test')
  const deployed = data?.deployed_model
  const config = data?.dataset?.config

  return (
    <div className="analytics-page">
      <PageHeader eyebrow="MET administrator" title="Model performance"
        description="Saved training and evaluation results for the synthetic Fiji flood model. Read-only: nothing here retrains, promotes or changes a model." />
      <p className="notice notice--info" role="note"><DataPill value="SYNTHETIC_DATA" compact /> {data?.notice ?? 'Synthetic Data — Research Demonstration.'} Results describe a simulator, not official Fiji MET readings or validated forecast skill.</p>

      {resource.status === 'error' && (
        <div className="inline-alert" role="alert"><span>{resource.message}</span>
          <button type="button" className="button button--secondary" onClick={resource.retry}>Retry</button></div>
      )}
      {!data && resource.status === 'loading' && <p className="empty-state" role="status">Loading saved evaluation results…</p>}

      {data && (
        <>
          {!data.artifacts_dir_available && (
            <p className="notice notice--warning">Saved evaluation artifacts were not found on this server (expected under <code>RESEARCH_RUNS_DIR</code>, default <code>ml/runs</code>). Sections that depend on them are empty; no results are substituted.</p>
          )}

          <section className="prototype-panel" aria-label="Selected research model">
            <div className="prototype-panel__header"><div>
              <h2>Deployed model</h2>
              <p>V1 serves the synthetic analysis workflow. V2 and V3 remain research candidates and are not deployed.</p>
            </div></div>
            {deployed ? (
              <div className="stat-grid stat-grid--padded">
                <StatCard label="Model version" value={<span className="data-table__mono">{deployed.model_version}</span>}
                  badge={<DataPill value="AI_PREDICTION" label="Deployed · V1" compact />}
                  detail={deployed.selected_candidate?.startsWith('catboost') ? 'CatBoost gradient-boosted trees' : deployed.selected_candidate ?? undefined} />
                <StatCard label="Alert threshold" value={formatMetric(deployed.threshold, 4)} detail="Chosen on a held-out partition before test scoring" />
                <StatCard label="Input features" value={deployed.n_features} detail={deployed.selected_at ? `Selected ${formatDateTime(deployed.selected_at)}` : undefined} />
                <StatCard label="Risk tiers" value="LOW to VERY HIGH" detail={deployed.risk_tiers ?? undefined} />
              </div>
            ) : <p className="empty-state">No deployed model metadata was found.</p>}
          </section>

          <section className="prototype-panel" aria-label="Training dataset overview">
            <div className="prototype-panel__header"><div>
              <h2>Training dataset overview</h2>
              <p>Simulated hourly observations for the registered Fiji monitoring locations, split chronologically and by location.</p>
            </div></div>
            <div className="stat-grid stat-grid--padded">
              <StatCard label="Dataset" value={<span className="data-table__mono">{data.dataset?.version ?? '—'}</span>}
                detail={config ? `${config.start} to ${config.end} · ${config.frequency} · seed ${config.seed}` : 'Dataset record not imported'} />
              <StatCard label="Stored observations" value={formatCount(data.dataset?.observation_count)} detail="Hourly rows across all locations, including ineligible hours" />
              <StatCard label="Training observations" value={formatCount(train?.rows)} detail={train ? `${formatCount(train.positives)} flood-onset positives` : 'No saved partition summary'} />
              <StatCard label="Hold-out test observations" value={formatCount(test?.rows)} detail={test ? `${formatCount(test.positives)} flood-onset positives` : 'No saved partition summary'} />
            </div>
            {v1?.partitions && v1.partitions.length > 0 && (
              <div className="table-scroll"><table className="data-table" aria-label="Partition sizes">
                <thead><tr><th>Partition</th><th>Rows</th><th>Flood positives</th><th>Prevalence</th></tr></thead>
                <tbody>{v1.partitions.map((row) => (
                  <tr key={row.stage}><td>{row.stage.replaceAll('_', ' ')}</td><td>{formatCount(row.rows)}</td><td>{formatCount(row.positives)}</td>
                    <td>{row.prevalence === null ? '—' : `${(row.prevalence * 100).toFixed(2)}%`}</td></tr>
                ))}</tbody>
              </table></div>
            )}
          </section>

          <section className="prototype-panel" aria-label="V1 evaluation">
            <div className="prototype-panel__header">
              <div><h2>V1 evaluation</h2><p>Metrics for the selected V1 model only, read from its saved evaluation artifacts.</p></div>
              {stages.length > 0 && (
                <label className="select-field">Partition
                  <select value={stage?.stage} onChange={(event) => setChosenStage(event.target.value)}>
                    {stages.map((item) => <option key={item.stage} value={item.stage}>{item.description}</option>)}
                  </select>
                </label>
              )}
            </div>
            {!v1?.available || !stage ? <p className="empty-state">{v1?.reason ?? 'No saved V1 evaluation results.'}</p> : (
              <div className="analytics-section">
                <p className="evaluation-label"><strong>{stage.description}</strong> · {formatCount(stage.rows)} rows · {formatCount(stage.positives)} flood-onset positives{stage.stage === 'train' && ' · in-sample, optimistic'}</p>
                <MetricCards metric={stage} />
                <div className="analytics-columns">
                  <ConfusionMatrix metric={stage} />
                  <div><h3>All partitions</h3><StageTable metrics={stages} /></div>
                </div>
              </div>
            )}
          </section>

          <section className="prototype-panel" aria-label="Feature importance">
            <div className="prototype-panel__header"><div><h2>Feature importance</h2><p>Top features of the selected V1 model, from its saved importance values.</p></div></div>
            {v1?.available ? <FeatureImportanceChart run={v1} /> : <p className="empty-state">No saved V1 artifacts.</p>}
          </section>

          <section className="prototype-panel" aria-label="Research experiments">
            <div className="prototype-panel__header"><div>
              <h2>Training experiments: V1, V2 and V3</h2>
              <p>Hold-out test partition of each experiment's selected model.</p>
            </div></div>
            <p className="notice notice--warning">{data.comparability_note}</p>
            <ExperimentTable runs={[data.v1, data.v2, ...data.v3]} stage={HEADLINE_STAGE} />
            {data.v2.available && data.v2.comparison_vs_v1 && data.v2.comparison_vs_v1.length > 0 && (
              <div className="analytics-section">
                <h3>V2 versus V1 on identical partitions</h3>
                <p>From the V2 run's own comparison artifact: same simulated dataset and partitions.
                  {data.v2.promotion && <> Promotion status: <strong>{data.v2.promotion.promoted ? 'promoted' : 'not promoted'}</strong>; V1 remains the selected model.</>}</p>
                <div className="table-scroll"><table className="data-table" aria-label="V2 versus V1 comparison">
                  <thead><tr><th>Model</th><th>Partition</th><th>Recall</th><th>Average precision</th></tr></thead>
                  <tbody>{data.v2.comparison_vs_v1.map((row) => (
                    <tr key={`${row.model}:${row.partition}`}><td>{row.model}</td><td>{row.partition}</td><td>{formatMetric(row.recall)}</td><td>{formatMetric(row.ap)}</td></tr>
                  ))}</tbody>
                </table></div>
                {data.v2.promotion?.criteria && (
                  <ul className="criteria-list" aria-label="V2 promotion criteria">
                    {Object.entries(data.v2.promotion.criteria).map(([name, met]) => (
                      <li key={name}><DataPill value={met ? 'LOW' : 'SUPPRESSED'} label={met ? 'Met' : 'Not met'} compact /> {name.replaceAll('_', ' ')}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
