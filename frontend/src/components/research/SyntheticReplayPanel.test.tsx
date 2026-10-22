import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/synthetic'
import type { SyntheticAlert, SyntheticFrame } from '../../api/synthetic'
import { SyntheticReplay } from './SyntheticReplay'

vi.mock('../../api/synthetic')
vi.mock('../map/WeatherMap', () => ({ WeatherMap: () => <div>Map</div> }))
const session = { user: { role: 'MET_ADMIN' }, token: 'admin-token' }
vi.mock('../../auth/useAuth', () => ({ useAuth: () => session }))
const frame: SyntheticFrame = { source_type: 'synthetic', timestamp: '2025-01-15T12:00:00Z', locations: [
  { source_type: 'synthetic', location_id: 1, slug: 'suva', name: 'Suva', division: 'Central', latitude: -18.14, longitude: 178.44,
    timestamp: '2025-01-15T12:00:00Z', horizon_hours: 24, model_version: 'test-model', probability: .1,
    risk_category: 'LOW', status: 'ok', simulated_flood_active: false, weather: {} },
  { source_type: 'synthetic', location_id: 2, slug: 'nausori', name: 'Nausori', division: 'Central', latitude: -18.03, longitude: 178.53,
    timestamp: '2025-01-15T12:00:00Z', horizon_hours: 24, model_version: 'test-model', probability: .8,
    risk_category: 'HIGH', status: 'ok', simulated_flood_active: false, weather: {} },
] }
const alert = (changes: Partial<SyntheticAlert> = {}): SyntheticAlert => ({
  id: 1, source_type: 'synthetic', status: 'PENDING', location_id: 1, location_name: 'Suva', model_version: 'test-model',
  probability: .1, risk_category: 'LOW', timestamp: frame.timestamp, message: 'Isolated test alert only', is_test: true, ...changes,
})
beforeEach(() => {
  vi.resetAllMocks()
  session.user.role = 'MET_ADMIN'
  vi.mocked(api.getSyntheticInfo).mockResolvedValue({ source_type: 'synthetic', status: 'ready', observations: 2, alerts_enabled: true, config: null })
  vi.mocked(api.getSyntheticFrame).mockResolvedValue(frame)
  vi.mocked(api.getSyntheticAlerts).mockResolvedValue([])
})
afterEach(() => vi.restoreAllMocks())
const renderReplay = () => render(<MemoryRouter><SyntheticReplay /></MemoryRouter>)
async function load() {
  renderReplay()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Load historical analysis' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: 'Load historical analysis' }))
  await screen.findByRole('button', { name: 'Create test alert' })
}

it('allows a low-risk test without changing its forecast and explains duplicate prevention', async () => {
  vi.mocked(api.createSyntheticAlert).mockImplementation(async () => {
    vi.mocked(api.getSyntheticAlerts).mockResolvedValue([alert()])
    return alert()
  })
  await load()
  await userEvent.click(screen.getByRole('button', { name: 'Create test alert' }))
  expect(api.createSyntheticAlert).toHaveBeenCalledWith(1, frame.timestamp, 'admin-token', true)
  expect(await screen.findByText(/Test alert #1 saved for review/)).toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Create test alert' })
  expect(button).toBeDisabled()
  expect(button).toHaveAccessibleDescription(/Alert #1 already exists/)
  expect(within(screen.getByRole('table')).getByText('Low')).toBeInTheDocument()
})

it('creates an eligible high-risk simulation without a low-risk test override', async () => {
  vi.mocked(api.createSyntheticAlert).mockResolvedValue(alert({ id: 2, location_id: 2, is_test: false }))
  await load()
  await userEvent.click(screen.getByRole('button', { name: 'Create simulated alert' }))
  expect(api.createSyntheticAlert).toHaveBeenCalledWith(2, frame.timestamp, 'admin-token', false)
  expect(await screen.findByText(/Simulated alert #2 saved for review/)).toBeInTheDocument()
})

it('explains the operator gate on each disabled creation action', async () => {
  vi.mocked(api.getSyntheticInfo).mockResolvedValue({ source_type: 'synthetic', status: 'ready', observations: 2, alerts_enabled: false, config: null })
  await load()
  for (const name of ['Create test alert', 'Create simulated alert']) {
    expect(screen.getByRole('button', { name })).toBeDisabled()
    expect(screen.getByRole('button', { name })).toHaveAccessibleDescription(/disabled by the operator/)
  }
})

it('explains missing output and does not offer a test override', async () => {
  vi.mocked(api.getSyntheticFrame).mockResolvedValue({ ...frame, locations: [{ ...frame.locations[0], probability: null, risk_category: null, status: 'insufficient_history' }] })
  await load()
  expect(screen.getByRole('button', { name: 'Create test alert' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Create test alert' })).toHaveAccessibleDescription(/complete eligible forecast/)
})

it('hides creation from community users and shows request failures', async () => {
  session.user.role = 'COMMUNITY'
  renderReplay()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Load historical analysis' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: 'Load historical analysis' }))
  await screen.findByRole('table')
  expect(screen.queryByRole('button', { name: 'Create test alert' })).not.toBeInTheDocument()
  expect(screen.getByText(/Sign in as a MET administrator/)).toBeInTheDocument()
})

it('shows creation errors without claiming success', async () => {
  vi.mocked(api.createSyntheticAlert).mockRejectedValue(new Error('Operator policy changed'))
  await load()
  await userEvent.click(screen.getByRole('button', { name: 'Create test alert' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Operator policy changed')
  expect(screen.queryByText(/saved for review/)).not.toBeInTheDocument()
})

it('confirms cancellation, requires a reason and moves the retained record into history', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  vi.mocked(api.getSyntheticAlerts).mockResolvedValue([alert()])
  vi.mocked(api.manageSyntheticAlert).mockImplementation(async () => {
    const closed = alert({ status: 'CANCELLED', closure_reason: 'Incorrect scenario', closed_by: 7, closed_at: '2026-10-22T02:00:00Z' })
    vi.mocked(api.getSyntheticAlerts).mockResolvedValue([closed]); return closed
  })
  await load()
  const cancel = screen.getByRole('button', { name: 'Cancel alert' })
  expect(cancel).toBeDisabled()
  await userEvent.type(screen.getByRole('textbox', { name: 'Action reason for alert #1' }), 'Incorrect scenario')
  await userEvent.click(cancel)
  expect(api.manageSyntheticAlert).not.toHaveBeenCalled()
  vi.mocked(window.confirm).mockReturnValue(true)
  await userEvent.click(cancel)
  expect(api.manageSyntheticAlert).toHaveBeenCalledWith(1, 'admin-token', 'cancel', 'Incorrect scenario')
  await screen.findByText(/Simulated alert #1 cancelled/)
  expect(screen.queryByRole('button', { name: 'Cancel alert' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Alert history' }))
  expect(await screen.findByText(/Reason: Incorrect scenario/)).toBeInTheDocument()
  expect(screen.getByText('Cancelled', { exact: true })).toBeInTheDocument()
})
