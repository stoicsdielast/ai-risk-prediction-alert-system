import type {
  ModelPerformance, PredictionOverview, PredictionTrend, RunSummary, StageMetrics, TrendPoint,
} from '../types/analytics'
import type { ApiLocation } from '../types/location'

export const NOW = '2026-10-20T12:00:00Z'

export const location = (id: number, name: string): ApiLocation => ({
  id, slug: name.toLowerCase(), name, division: 'CENTRAL', division_label: 'Central',
  latitude: -18, longitude: 178, prediction: null,
})
export const LOCATIONS = [location(1, 'Nausori'), location(2, 'Labasa'), location(3, 'Suva')]

export const point = (over: Partial<TrendPoint> = {}): TrendPoint => ({
  id: 1, location_id: 1, location: 'Nausori', timestamp: '2026-10-20T06:00:00Z', probability: 0.62,
  risk_level: 'HIGH', model_version: 'synthetic-fiji-v1-catboost__none', kind: 'genuine', horizon_hours: 24, ...over,
})

export function trend(over: Partial<PredictionTrend> = {}): PredictionTrend {
  const points = over.points ?? [point()]
  return {
    source: 'operational', source_type: 'operational', window_days: 7, window_start: '2026-10-13T12:00:00Z',
    window_end: NOW, horizon_hours: 24, anchor_kind: 'current time', locations: [{ id: 1, name: 'Nausori' }],
    points, truncated: false, max_points: 5000,
    data_span: { earliest: '2026-10-14T00:00:00Z', latest: '2026-10-20T06:00:00Z', stored_predictions: points.length, available_days: 7 },
    freshness: { latest_at: '2026-10-20T06:00:00Z', age_hours: 6, stale: false, stale_after_hours: 24 },
    risk_band_thresholds: null, notice: null, ...over,
  }
}

const risk = (low = 0, moderate = 0, high = 0, veryHigh = 0) => ({ LOW: low, MODERATE: moderate, HIGH: high, VERY_HIGH: veryHigh })
const windowSummary = (ids: number[], by = risk()) => ({
  predictions: Object.values(by).reduce((a, b) => a + b, 0), by_risk: by, high_risk: by.HIGH + by.VERY_HIGH,
  locations_with_predictions: ids.length, location_ids: ids,
})

export function overview(over: Partial<PredictionOverview> = {}): PredictionOverview {
  return {
    generated_at: NOW, window_days: 7, window_start: '2026-10-13T12:00:00Z', monitored_locations: 12,
    operational: {
      kinds: {
        genuine: { total: 0, by_risk: risk(), window: windowSummary([]),
          freshness: { latest_at: null, age_hours: null, stale: null, stale_after_hours: 24 } },
        sample: { total: 9, by_risk: risk(2, 2, 4, 1), window: windowSummary([1, 2], risk(1, 0, 2, 1)),
          freshness: { latest_at: '2026-10-20T06:00:00Z', age_hours: 6, stale: false, stale_after_hours: 24 } },
      },
      model_versions: [{ model_version: 'sample-demo-not-a-model-result', kind: 'sample', predictions: 9,
        first_at: '2026-10-14T00:00:00Z', last_at: '2026-10-20T06:00:00Z', alert_workflow_demo: false }],
    },
    synthetic: {
      source_type: 'synthetic', total: 1, by_risk: risk(0, 0, 0, 1), earliest_observed_at: '2021-01-25T01:00:00Z',
      latest_observed_at: '2021-01-25T01:00:00Z', window_anchor: '2021-01-25T01:00:00Z',
      window_anchor_kind: 'latest synthetic record', window: windowSummary([3], risk(0, 0, 0, 1)),
      model_versions: [{ model_version: 'synthetic-fiji-v1-catboost__none', dataset_version: 'synthetic-fiji-v1', predictions: 1 }],
      notice: 'Synthetic Data — Research Demonstration.',
    },
    ...over,
  }
}

export const stage = (name: string, over: Partial<StageMetrics> = {}): StageMetrics => ({
  stage: name, description: name === 'test' ? 'Chronological hold-out test (diagnostic)' : name, rows: 100, positives: 10,
  confusion: { tn: 80, fp: 10, fn: 6, tp: 4 }, precision: 0.5, recall: 0.4, f1: 0.444, pr_auc: 0.3, roc_auc: 0.9, brier: 0.05,
  prevalence: 0.1, event_recall: null, median_warning_lead_hours: null, threshold: 0.44, ...over,
})

export const run = (key: string, over: Partial<RunSummary> = {}): RunSummary => ({
  key, label: `Run ${key}`, role: key === 'v1' ? 'deployed' : 'research only', available: true,
  selected_candidate: 'cat', dataset_sha256: 'abcdef1234567890',
  partitions: [{ stage: 'train', rows: 400, positives: 40, prevalence: 0.1 }, { stage: 'test', rows: 100, positives: 10, prevalence: 0.1 }],
  metrics: [stage('train', { rows: 400, positives: 40, confusion: { tn: 300, fp: 60, fn: 4, tp: 36 } }), stage('test')],
  feature_importance: [{ feature: 'month_sin', share_percent: 60 }, { feature: 'rainfall_mm', share_percent: 40 }],
  feature_importance_method: 'Share of importance.', ...over,
})

export function performance(over: Partial<ModelPerformance> = {}): ModelPerformance {
  return {
    source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration.',
    comparability_note: 'Metrics must not be ranked against each other.', artifacts_dir_available: true,
    deployed_model: { model_version: 'synthetic-fiji-v1-catboost__none', selected_candidate: 'catboost__none', threshold: 0.4447,
      n_features: 56, risk_tiers: 'Provisional bands', selected_at: '2026-10-01T00:00:00Z', model_sha256: 'x' },
    dataset: { version: 'synthetic-fiji-v1', observation_count: 525888, imported_at: null,
      config: { start: '2021-01-01', end: '2025-12-31', frequency: '1h', seed: 314 }, notice: null },
    v1: run('v1'),
    v2: run('v2', { promotion: { promoted: false, criteria: { selection_ap_at_least_v1: false, selection_feasible: true } },
      comparison_vs_v1: [{ model: 'v1 CatBoost', partition: 'selection', recall: 0.88, ap: 0.74 }] }),
    v3: ['controlled', 'realistic', 'stress'].map((name) => run(`v3-${name}`, { scenario: name, dataset_sha256: `${name}0000000` })),
    ...over,
  }
}
