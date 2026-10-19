import { apiRequest } from './client'
import type { RiskLevel } from '../types/prototype'

export const SYNTHETIC_NOTICE = 'Synthetic Data — Research Demonstration'

export type ResearchScenarioName = 'controlled' | 'realistic' | 'stress'

export interface ResearchScenarioInfo {
  scenario: ResearchScenarioName
  status: 'ready' | 'not_published'
  research_only: true
  model_version?: string
  selected_candidate?: string
  calibration?: string
  threshold?: number
  n_features?: number
  time_range?: { start: string; end: string }
  observations?: number
  events?: { total: number; by_severity?: Record<string, number> }
  partitions?: Record<string, { min: string; max: string }>
  held_location_ids?: number[]
  bootstrap_intervals?: Record<string, unknown>
  ground_truth_policy?: string
}

export interface ResearchInfo {
  source_type: 'synthetic'
  research_only: true
  notice: string
  scenarios: ResearchScenarioInfo[]
  v1_serving_unchanged: boolean
  note: string
}

export interface ResearchGroundTruth {
  available: boolean
  research_view_only: true
  flood_occurred?: boolean
  flood_within_24h?: boolean
  event_id?: string | null
  partition?: string | null
}

export interface ResearchLocation {
  source_type: 'synthetic'
  research_only: true
  notice: string
  scenario: ResearchScenarioName
  model_version: string
  location_id: number
  slug: string
  name: string
  division: string
  latitude: number
  longitude: number
  timestamp: string
  horizon_hours: number
  threshold: number
  provisional_risk: true
  weather: Record<string, number | null>
  status: 'ok' | 'insufficient_history'
  probability: number | null
  risk_category: RiskLevel | null
  ground_truth: ResearchGroundTruth
}

export interface ResearchFrame {
  source_type: 'synthetic'
  research_only: true
  notice: string
  scenario: ResearchScenarioName
  model_version: string
  threshold: number
  timestamp: string
  locations: ResearchLocation[]
}

export interface ResearchStorm {
  event_id: string
  scenario_id: string | null
  location_id: number
  name: string
  slug: string
  start: string
  end: string
  severity: string
  duration_hours: number
  max_river_level_m: number
}

export interface ResearchStorms {
  source_type: 'synthetic'
  research_only: true
  notice: string
  scenario: ResearchScenarioName
  model_version: string
  storms: ResearchStorm[]
}

export interface ResearchSeries {
  source_type: 'synthetic'
  research_only: true
  notice: string
  scenario: ResearchScenarioName
  location_id: number
  model_version: string
  start: string
  end: string
  series: ResearchLocation[]
}

function assertResearch<T extends { source_type: string; research_only: boolean }>(payload: T): T {
  if (payload.source_type !== 'synthetic' || !payload.research_only) {
    throw new Error('Unexpected data source in research replay')
  }
  return payload
}

export const getResearchInfo = async () =>
  assertResearch(await apiRequest<ResearchInfo>('/api/synthetic/research/info'))

export const getResearchFrame = async (scenario: ResearchScenarioName, timestamp: string) =>
  assertResearch(await apiRequest<ResearchFrame>(
    `/api/synthetic/research/frame?scenario=${scenario}&timestamp=${encodeURIComponent(timestamp)}`,
  ))

export const getResearchStorms = async (scenario: ResearchScenarioName) =>
  assertResearch(await apiRequest<ResearchStorms>(
    `/api/synthetic/research/storms?scenario=${scenario}`,
  ))

export const getResearchSeries = async (
  scenario: ResearchScenarioName,
  locationId: number,
  start: string,
  end: string,
) =>
  assertResearch(await apiRequest<ResearchSeries>(
    `/api/synthetic/research/series?scenario=${scenario}&location_id=${locationId}` +
    `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
  ))
