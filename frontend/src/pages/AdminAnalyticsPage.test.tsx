import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/analytics'
import { getLocations } from '../api/locations'
import { LOCATIONS, overview, trend } from '../test/analyticsFixture'
import { AdminAnalyticsPage } from './AdminAnalyticsPage'

vi.mock('../api/analytics')
vi.mock('../api/locations', () => ({ getLocations: vi.fn() }))
vi.mock('../auth/useAuth', () => ({ useAuth: () => ({ token: 'admin-token', user: { id: 1, role: 'MET_ADMIN' } }) }))

const getOverview = vi.mocked(api.getPredictionOverview)
const getTrend = vi.mocked(api.getPredictionTrend)

function renderPage() {
  return render(<MemoryRouter><AdminAnalyticsPage /></MemoryRouter>)
}
const range = (name: string) => screen.getByRole('button', { name })

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getLocations).mockResolvedValue(LOCATIONS)
  getOverview.mockResolvedValue(overview())
  getTrend.mockResolvedValue(trend())
})

describe('AdminAnalyticsPage', () => {
  it('loads overview and trend for locations that actually have stored predictions', async () => {
    renderPage()
    expect(await screen.findByRole('img', { name: /line chart/i })).toBeInTheDocument()
    expect(getOverview).toHaveBeenCalledWith('admin-token', 7, expect.any(AbortSignal))
    expect(getTrend).toHaveBeenCalledWith('admin-token', 'operational', 7, [1, 2], expect.any(AbortSignal))
    expect(screen.getByRole('heading', { name: 'Prediction analytics' })).toBeInTheDocument()
  })

  it('disables time ranges that exceed the stored history instead of implying more data', async () => {
    renderPage()
    await screen.findByRole('img', { name: /line chart/i })
    // fixture history started 2026-10-14, so 24 hours and 7 days are meaningful but 30 days adds nothing
    expect(range('24 hours')).toBeEnabled()
    expect(range('7 days')).toBeEnabled()
    expect(range('7 days')).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches to synthetic research data using its own span and selection', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('img', { name: /line chart/i })
    await user.click(range('Synthetic research'))
    await waitFor(() => expect(getTrend).toHaveBeenLastCalledWith('admin-token', 'synthetic', 1, [3], expect.any(AbortSignal)))
    // one synthetic record spans under a day, so longer ranges are disabled
    expect(range('24 hours')).toBeEnabled()
    expect(range('7 days')).toBeDisabled()
    expect(range('30 days')).toBeDisabled()
    expect(range('7 days')).toHaveAttribute('title', expect.stringMatching(/already fit within 24 hours/))
  })

  it('shows an empty overview honestly when no predictions are stored', async () => {
    const empty = overview()
    empty.operational.model_versions = []
    empty.operational.kinds.sample = { ...empty.operational.kinds.sample, total: 0, window: { ...empty.operational.kinds.sample.window, location_ids: [], locations_with_predictions: 0, high_risk: 0, predictions: 0 },
      freshness: { latest_at: null, age_hours: null, stale: null, stale_after_hours: 24 } }
    empty.synthetic = { ...empty.synthetic, total: 0, model_versions: [], earliest_observed_at: null, latest_observed_at: null }
    getOverview.mockResolvedValue(empty)
    getTrend.mockResolvedValue(trend({ points: [] }))
    renderPage()
    expect(await screen.findByText('No predictions are stored yet.')).toBeInTheDocument()
    expect(await screen.findByText(/Select at least one monitored location/i)).toBeInTheDocument()
    expect(getTrend).not.toHaveBeenCalled()
  })

  it('shows an overview error with retry', async () => {
    getOverview.mockRejectedValueOnce(new Error('Insufficient permissions')).mockResolvedValueOnce(overview())
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient permissions')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('img', { name: /line chart/i })).toBeInTheDocument()
  })
})
