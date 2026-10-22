import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { usePublicAlerts } from '../../alerts/PublicAlertContext'
import { sampleAlert } from '../../test/alertApiFixture'
import { ApprovedAlertBanner } from './ApprovedAlertBanner'

vi.mock('../../alerts/PublicAlertContext', () => ({ usePublicAlerts: vi.fn() }))

beforeEach(() => {
  vi.mocked(usePublicAlerts).mockReturnValue({
    data: [sampleAlert({ status: 'APPROVED' })], setData: vi.fn(), error: null,
    refreshing: false, updatedAt: null, refresh: vi.fn(),
  })
})

function renderBanner(path = '/admin/dashboard') {
  return render(<MemoryRouter initialEntries={[path]}>
    <ApprovedAlertBanner />
    <Routes><Route path="/alerts" element={<h1>Community alert feed</h1>} /><Route path="*" element={null} /></Routes>
  </MemoryRouter>)
}

it('keeps an issued alert distinct from simulations and links to its public record', async () => {
  renderBanner()
  expect(screen.getByRole('heading', { name: 'Active flood alert · Suva' })).toBeInTheDocument()
  expect(screen.getByText('High')).toBeInTheDocument()
  expect(screen.queryByText(/Not an emergency warning/)).not.toBeInTheDocument()
  const link = screen.getByRole('link', { name: /View community alerts/ })
  expect(link).toHaveAttribute('href', '/alerts#alert-41')
  await userEvent.click(link)
  expect(screen.getByRole('heading', { name: 'Community alert feed' })).toBeInTheDocument()
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})

it.each(['demo', 'sample prediction'])('labels an alert from %s metadata as simulated', (source) => {
  const alert = sampleAlert({
    status: 'APPROVED', is_demo: source === 'demo', severity: 'VERY_HIGH',
    prediction: source === 'sample prediction' ? {
      id: 1, risk_level: 'VERY_HIGH', flood_probability: 0.9, confidence_percent: 90,
      model_version: 'sample', is_sample: true, predicted_at: '2026-10-14T00:00:00Z',
    } : null,
  })
  vi.mocked(usePublicAlerts).mockReturnValue({ data: [alert], error: null, refreshing: false, updatedAt: null, refresh: vi.fn(), setData: vi.fn() })
  renderBanner()
  expect(screen.getByRole('heading', { name: 'Simulated flood alert · Suva' })).toBeInTheDocument()
  expect(screen.getByText(/Not an emergency warning/)).toBeInTheDocument()
  expect(screen.getByText('Very high')).toBeInTheDocument()
})

it('retains the stale-feed warning when a previous alert is still displayed', () => {
  vi.mocked(usePublicAlerts).mockReturnValue({
    data: [sampleAlert({ status: 'APPROVED' })], setData: vi.fn(), error: 'Offline',
    refreshing: false, updatedAt: null, refresh: vi.fn(),
  })
  renderBanner()
  expect(screen.getByText(/this information may be out of date/)).toBeInTheDocument()
})
