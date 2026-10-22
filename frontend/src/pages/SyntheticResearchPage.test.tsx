import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getResearchFrame, getResearchInfo, getResearchSeries, getResearchStorms,
  type ResearchFrame, type ResearchInfo, type ResearchSeries, type ResearchStorms,
} from '../api/syntheticResearch'
import { SyntheticResearchPage } from './SyntheticResearchPage'

vi.mock('../api/syntheticResearch', async () => {
  const actual = await vi.importActual<typeof import('../api/syntheticResearch')>('../api/syntheticResearch')
  return {
    ...actual,
    getResearchInfo: vi.fn(),
    getResearchFrame: vi.fn(),
    getResearchStorms: vi.fn(),
    getResearchSeries: vi.fn(),
  }
})

const mockedInfo = vi.mocked(getResearchInfo)
const mockedFrame = vi.mocked(getResearchFrame)
const mockedStorms = vi.mocked(getResearchStorms)
const mockedSeries = vi.mocked(getResearchSeries)

const INFO: ResearchInfo = {
  source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration',
  v1_serving_unchanged: true, note: 'research only',
  scenarios: [
    { scenario: 'controlled', status: 'not_published', research_only: true },
    {
      scenario: 'realistic', status: 'ready', research_only: true,
      model_version: 'synthetic-fiji-v3-realistic-catboost_tuned1__isotonic',
      selected_candidate: 'catboost_tuned1', calibration: 'isotonic', threshold: 0.0835,
      time_range: { start: '2021-01-01 00:00:00+00:00', end: '2025-06-30 23:00:00+00:00' },
      observations: 525888, events: { total: 254 },
      held_location_ids: [3, 10, 12],
    },
    { scenario: 'stress', status: 'not_published', research_only: true },
  ],
}

const FRAME: ResearchFrame = {
  source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration',
  scenario: 'realistic', model_version: 'synthetic-fiji-v3-realistic-catboost_tuned1__isotonic',
  threshold: 0.0835, timestamp: '2021-01-29T00:00:00+00:00',
  locations: [{
    source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration',
    scenario: 'realistic', model_version: 'synthetic-fiji-v3-realistic-catboost_tuned1__isotonic',
    location_id: 1, slug: 'suva', name: 'Suva', division: 'CENTRAL', latitude: -18.14, longitude: 178.44,
    timestamp: '2021-01-29T00:00:00+00:00', horizon_hours: 24, threshold: 0.0835, provisional_risk: true,
    weather: { rainfall_mm: 12.5, soil_moisture_pct: 88, river_level_m: 3.2 },
    status: 'ok', probability: 0.62, risk_category: 'VERY_HIGH',
    ground_truth: { available: true, research_view_only: true, flood_occurred: true, flood_within_24h: true, event_id: 'event-1', partition: 'test' },
  }],
}

const STORMS: ResearchStorms = {
  source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration',
  scenario: 'realistic', model_version: FRAME.model_version,
  storms: [{
    event_id: 'event-1', scenario_id: 'storm-1', location_id: 1, name: 'Suva', slug: 'suva',
    start: '2021-01-29 00:00:00+00:00', end: '2021-01-31 03:00:00+00:00',
    severity: 'extreme', duration_hours: 51, max_river_level_m: 3.16,
  }],
}

const SERIES: ResearchSeries = {
  source_type: 'synthetic', research_only: true, notice: 'Synthetic Data — Research Demonstration',
  scenario: 'realistic', location_id: 1, model_version: FRAME.model_version,
  start: '2021-01-28T18:00:00.000Z', end: '2021-01-31T15:00:00.000Z',
  series: [FRAME.locations[0]],
}

function renderPage() {
  return render(<SyntheticResearchPage />)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedInfo.mockResolvedValue(INFO)
  mockedStorms.mockResolvedValue(STORMS)
  mockedFrame.mockResolvedValue(FRAME)
  mockedSeries.mockResolvedValue(SERIES)
})

describe('SyntheticResearchPage', () => {
  it('shows the research badge, keeps unpublished scenarios disabled and renders evaluation labels', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: /Research Demonstration/ })).toBeInTheDocument()
    const select = await screen.findByLabelText('Synthetic scenario')
    await waitFor(() => expect(mockedStorms).toHaveBeenCalledWith('realistic'))
    const options = select.querySelectorAll('option')
    expect(options).toHaveLength(3)
    expect((select.querySelector('option[value="controlled"]') as HTMLOptionElement).disabled).toBe(true)
    expect((select.querySelector('option[value="stress"]') as HTMLOptionElement).disabled).toBe(true)
    expect(screen.getByText(/deployed V1 model and its configuration are unchanged/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load scenario frame' }))
    expect(await screen.findByRole('heading', { name: /Frame at/ })).toBeInTheDocument()
    expect(mockedFrame).toHaveBeenCalledWith('realistic', '2021-01-01T00:00:00Z')
    expect(screen.getByText('62.0%')).toBeInTheDocument()
    expect(screen.getByTitle('Ground truth flood active (display only)')).toHaveTextContent('Yes')
    expect(screen.getByTitle('Ground truth flood within 24h (display only)')).toHaveTextContent('Yes')
    expect(screen.getAllByText('event-1').length).toBeGreaterThanOrEqual(2)
  })

  it('replays a storm by jumping to its onset and loading the affected location timeline', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Replay storm' }))
    await waitFor(() => expect(mockedFrame).toHaveBeenCalledWith('realistic', '2021-01-29T00:00:00.000Z'))
    expect(mockedSeries).toHaveBeenCalledWith('realistic', 1, '2021-01-28T18:00:00.000Z', '2021-01-31T15:00:00.000Z')
    expect(await screen.findByRole('heading', { name: /timeline/ })).toBeInTheDocument()
  })

  it('surfaces serving errors instead of rendering a frame', async () => {
    mockedFrame.mockRejectedValue(new Error('Unexpected data source in research replay'))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Load scenario frame' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unexpected data source')
    expect(screen.queryByRole('heading', { name: /Frame at/ })).not.toBeInTheDocument()
  })
})
