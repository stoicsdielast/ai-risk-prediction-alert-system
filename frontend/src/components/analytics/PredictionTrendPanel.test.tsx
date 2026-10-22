import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../api/analytics'
import { LOCATIONS, location, point, trend } from '../../test/analyticsFixture'
import { PredictionTrendPanel } from './PredictionTrendPanel'

vi.mock('../../api/analytics')
const getTrend = vi.mocked(api.getPredictionTrend)

function renderPanel(over: Partial<Parameters<typeof PredictionTrendPanel>[0]> = {}) {
  return render(<PredictionTrendPanel token="t" source="operational" days={7} locations={LOCATIONS} suggestedLocationIds={[1]} {...over} />)
}

beforeEach(() => { vi.resetAllMocks() })

describe('PredictionTrendPanel', () => {
  it('plots stored points with risk colours, provenance, model version and horizon', async () => {
    getTrend.mockResolvedValue(trend({ points: [
      point({ id: 1, probability: 0.62, risk_level: 'HIGH' }),
      point({ id: 2, timestamp: '2026-10-20T08:00:00Z', probability: 0.9, risk_level: 'VERY_HIGH', kind: 'sample',
        horizon_hours: null, model_version: 'sample-demo-not-a-model-result' }),
    ] }))
    renderPanel()
    expect(await screen.findByRole('img', { name: /line chart/i })).toBeInTheDocument()
    const dots = await screen.findAllByTestId('trend-dot')
    expect(dots.map((dot) => dot.getAttribute('data-risk')).sort()).toEqual(['HIGH', 'VERY_HIGH'])
    expect(getTrend).toHaveBeenCalledWith('t', 'operational', 7, [1], expect.any(AbortSignal))
    const table = screen.getByRole('table')
    expect(within(table).getByText('sample-demo-not-a-model-result')).toBeInTheDocument()
    expect(within(table).getByText('24 h')).toBeInTheDocument()
    expect(within(table).getByText('n/a')).toBeInTheDocument()
    expect(within(table).getByText('Genuine')).toBeInTheDocument()
    expect(screen.getByText(/seeded workflow fixtures, not model results/i)).toBeInTheDocument()
  })

  it('never fabricates values when nothing is stored in range', async () => {
    getTrend.mockResolvedValue(trend({ points: [], data_span: { earliest: null, latest: null, stored_predictions: 0, available_days: null } }))
    renderPanel()
    expect(await screen.findByText(/No values are generated to fill the chart/i)).toBeInTheDocument()
    expect(screen.queryByTestId('trend-dot')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /line chart/i })).not.toBeInTheDocument()
  })

  it('explains data that exists outside the selected range', async () => {
    getTrend.mockResolvedValue(trend({ points: [], data_span: { earliest: '2026-09-01T00:00:00Z', latest: '2026-09-02T00:00:00Z', stored_predictions: 4, available_days: 50 } }))
    renderPanel()
    expect(await screen.findByText(/4 stored outside it/i)).toBeInTheDocument()
  })

  it('warns about stale and sparse history', async () => {
    getTrend.mockResolvedValue(trend({ freshness: { latest_at: '2026-10-18T00:00:00Z', age_hours: 60, stale: true, stale_after_hours: 24 } }))
    renderPanel()
    expect(await screen.findByText(/latest stored prediction is 60 hours old/i)).toBeInTheDocument()
    expect(screen.getByText(/Sparse history: only 1 stored prediction/i)).toBeInTheDocument()
  })

  it('labels synthetic research data and shows V1 risk bands without claiming it is current', async () => {
    getTrend.mockResolvedValue(trend({
      source: 'synthetic', source_type: 'synthetic', anchor_kind: 'latest synthetic record (simulated time)',
      window_end: '2021-01-25T01:00:00Z', notice: 'Synthetic Data — Research Demonstration.',
      risk_band_thresholds: { moderate_from: 0.2, high_from: 0.4, very_high_from: 0.6, model_version: 'v1' },
      points: [point({ kind: 'synthetic', risk_level: 'VERY_HIGH', probability: 0.95 })],
    }))
    renderPanel({ source: 'synthetic' })
    expect(await screen.findByText(/Research Demonstration/)).toBeInTheDocument()
    expect(screen.getByText(/not today/i)).toBeInTheDocument()
    expect(screen.getByText(/Shaded bands are the V1 research risk tiers/i)).toBeInTheDocument()
    expect(getTrend).toHaveBeenCalledWith('t', 'synthetic', 7, [1], expect.any(AbortSignal))
  })

  it('refetches when locations are toggled and caps the selection', async () => {
    getTrend.mockResolvedValue(trend())
    const user = userEvent.setup()
    renderPanel()
    await screen.findByRole('img', { name: /line chart/i })
    await user.click(screen.getByRole('checkbox', { name: /Labasa/ }))
    await waitFor(() => expect(getTrend).toHaveBeenLastCalledWith('t', 'operational', 7, [1, 2], expect.any(AbortSignal)))
    await user.click(screen.getByRole('checkbox', { name: /Nausori/ }))
    await waitFor(() => expect(getTrend).toHaveBeenLastCalledWith('t', 'operational', 7, [2], expect.any(AbortSignal)))
  })

  it('disables further locations at the chart limit', async () => {
    getTrend.mockResolvedValue(trend())
    const many = Array.from({ length: 8 }, (_, index) => location(index + 1, `Place ${index + 1}`))
    renderPanel({ locations: many, suggestedLocationIds: [1, 2, 3, 4, 5, 6] })
    await screen.findByRole('img', { name: /line chart/i })
    expect(screen.getByRole('checkbox', { name: /Place 7/ })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: /^Place 1\b/, checked: true })).toBeEnabled()
  })

  it('does not query or plot anything when no location is selected', async () => {
    renderPanel({ suggestedLocationIds: [] })
    expect(await screen.findByText(/Select at least one monitored location/i)).toBeInTheDocument()
    expect(getTrend).not.toHaveBeenCalled()
  })

  it('shows an error with retry, then recovers', async () => {
    getTrend.mockRejectedValueOnce(new Error('Server unavailable')).mockResolvedValueOnce(trend())
    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByRole('alert')).toHaveTextContent('Server unavailable')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('img', { name: /line chart/i })).toBeInTheDocument()
  })

  it('notes truncation and paginates the table', async () => {
    const points = Array.from({ length: 30 }, (_, index) => point({ id: index + 1, timestamp: `2026-10-20T${String(index % 24).padStart(2, '0')}:00:00Z` }))
    getTrend.mockResolvedValue(trend({ points, truncated: true, max_points: 30 }))
    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText(/Showing the first 30 stored predictions/i)).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(26)
    await user.click(screen.getByRole('button', { name: /Show more \(5 remaining\)/ }))
    expect(screen.getAllByRole('row')).toHaveLength(31)
  })
})
