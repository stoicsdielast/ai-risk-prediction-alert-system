import type { RiskLevel } from './prototype'

/** genuine = stored model output; sample = seeded workflow fixture; synthetic = simulator research output. */
export type PredictionKind = 'genuine' | 'sample' | 'synthetic'
export type TrendSource = 'operational' | 'synthetic'

export interface Freshness {
  latest_at: string | null
  age_hours: number | null
  stale: boolean | null
  stale_after_hours: number
}

export interface RiskCounts extends Record<RiskLevel, number> {}

export interface WindowSummary {
  predictions: number
  by_risk: RiskCounts
  high_risk: number
  locations_with_predictions: number
  location_ids: number[]
}

export interface OperationalKindSummary {
  total: number
  by_risk: RiskCounts
  window: WindowSummary
  freshness: Freshness
}

export interface OperationalVersion {
  model_version: string
  kind: 'genuine' | 'sample'
  predictions: number
  first_at: string | null
  last_at: string | null
  alert_workflow_demo: boolean
}

export interface SyntheticSummary {
  source_type: 'synthetic'
  total: number
  by_risk: RiskCounts
  earliest_observed_at: string | null
  latest_observed_at: string | null
  window_anchor: string | null
  window_anchor_kind: string
  window: WindowSummary
  model_versions: { model_version: string; dataset_version: string; predictions: number }[]
  notice: string
}

export interface PredictionOverview {
  generated_at: string
  window_days: number
  window_start: string
  monitored_locations: number
  operational: {
    kinds: { genuine: OperationalKindSummary; sample: OperationalKindSummary }
    model_versions: OperationalVersion[]
  }
  synthetic: SyntheticSummary
}

export interface TrendPoint {
  id: number
  location_id: number
  location: string
  timestamp: string
  probability: number
  risk_level: RiskLevel
  model_version: string
  kind: PredictionKind
  /** null for sample rows: they are workflow fixtures and claim no forecast horizon. */
  horizon_hours: number | null
  dataset_version?: string
}

export interface RiskBandThresholds {
  moderate_from: number
  high_from: number
  very_high_from: number
  model_version: string | null
}

export interface PredictionTrend {
  source: TrendSource
  source_type: 'operational' | 'synthetic'
  window_days: number
  window_start: string | null
  window_end: string | null
  horizon_hours: number
  anchor_kind: string
  locations: { id: number; name: string }[]
  points: TrendPoint[]
  truncated: boolean
  max_points: number
  data_span: { earliest: string | null; latest: string | null; stored_predictions: number; available_days: number | null }
  freshness: Freshness | null
  risk_band_thresholds: RiskBandThresholds | null
  notice: string | null
}

export interface Confusion { tn: number; fp: number; fn: number; tp: number }

export interface StageMetrics {
  stage: string
  description: string
  rows: number
  positives: number
  confusion: Confusion | null
  precision: number | null
  recall: number | null
  f1: number | null
  pr_auc: number | null
  roc_auc: number | null
  brier: number | null
  prevalence: number | null
  event_recall: number | null
  median_warning_lead_hours: number | null
  threshold: number | null
}

export interface PartitionRow { stage: string; rows: number; positives: number; prevalence: number | null }

export interface RunSummary {
  key: string
  label: string
  role: string
  available: boolean
  reason?: string
  scenario?: string
  selected_candidate?: string
  threshold?: number | null
  partitions?: PartitionRow[]
  metrics?: StageMetrics[]
  feature_importance?: { feature: string; share_percent: number }[]
  feature_importance_method?: string
  dataset_sha256?: string | null
  promotion?: { promoted: boolean | null; criteria: Record<string, boolean> | null } | null
  comparison_vs_v1?: { model: string; partition: string; recall: number | null; ap: number | null }[]
}

export interface ModelPerformance {
  source_type: 'synthetic'
  research_only: true
  notice: string
  comparability_note: string
  artifacts_dir_available: boolean
  deployed_model: {
    model_version: string | null
    selected_candidate: string | null
    threshold: number | null
    n_features: number
    risk_tiers: string | null
    selected_at: string | null
    model_sha256: string | null
  } | null
  dataset: {
    version: string
    observation_count: number
    imported_at: string | null
    config: Record<string, string | number> | null
    notice: string | null
  } | null
  v1: RunSummary
  v2: RunSummary
  v3: RunSummary[]
}
