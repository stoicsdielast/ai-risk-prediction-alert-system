import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/AuthContext'
import type { AuthContextValue } from '../../auth/AuthContext'
import { getReplayExamples, getResearchInfo, runReplay } from '../../api/predictions'
import type { ReplayExample, ResearchResult } from '../../api/predictions'
import { ResearchReplayPanel } from './ResearchReplayPanel'

vi.mock('../../api/predictions', () => ({ getReplayExamples: vi.fn(), getResearchInfo: vi.fn(), runReplay: vi.fn() }))
vi.mock('./ResearchReplayMap', () => ({ ResearchReplayMap: () => <p>Bangladesh historical research map</p> }))

const example: ReplayExample = { id: 'normal', selection: 'Held-out minimum score', station: { station_id: 'A', name: 'Example station', latitude: 23, longitude: 90 },
  feature_date: '2024-05-01', as_of: '2024-05-01T23:59:59Z', mode: 'historical_replay', country: 'Bangladesh', features: { rainfall_local_mm: 2 } }
const result: ResearchResult = { status: 'ok', research_mode: true, country: 'Bangladesh', mode: 'historical_replay', probability: .8, presentation_tier: 'VERY_HIGH', model_version: 'test-only', timestamp: example.as_of,
  generated_at: example.as_of, prediction_horizon_hours: 24, source: 'https://github.com/Srabon-bot/Bangladesh-flood-data-set', disclaimer: 'Research only', reason: null, missing_features: [] }

function renderPanel(signedIn = true) {
  const session = { token: signedIn ? 'approved-token' : null } as AuthContextValue
  return render(<AuthContext.Provider value={session}><ResearchReplayPanel /></AuthContext.Provider>)
}

describe('Research replay', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getResearchInfo).mockResolvedValue({ status: 'ok', model_version: 'test-only', selected_model: 'logistic_regression', disclaimer: 'Research only' })
    vi.mocked(getReplayExamples).mockResolvedValue({ status: 'ok', examples: [example] })
    vi.mocked(runReplay).mockResolvedValue(result)
  })

  it('labels the research boundary and loads data only when opened', async () => {
    renderPanel()
    expect(screen.getByText(/not been validated for Fiji/)).toBeInTheDocument()
    expect(getResearchInfo).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Open Bangladesh research replay' }))
    expect(await screen.findByRole('button', { name: 'Run historical replay' })).toBeEnabled()
    expect(screen.getByText(/Feature date: 2024-05-01/)).toHaveTextContent('Bangladesh')
  })

  it('requires a signed-in account to run inference', async () => {
    renderPanel(false)
    await userEvent.click(screen.getByRole('button', { name: 'Open Bangladesh research replay' }))
    expect(await screen.findByRole('button', { name: 'Run historical replay' })).toBeDisabled()
    expect(runReplay).not.toHaveBeenCalled()
  })

  it('shows only explicit internal demo alerts and asks browser permission on click', async () => {
    const requestPermission = vi.fn().mockResolvedValue('denied')
    const BrowserNotification = vi.fn()
    Object.assign(BrowserNotification, { permission: 'default', requestPermission })
    vi.stubGlobal('Notification', BrowserNotification)
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Open Bangladesh research replay' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Run historical replay' }))
    expect(await screen.findByText(/80.00% model score/)).toBeInTheDocument()
    expect(runReplay).toHaveBeenCalledWith(example, 'approved-token')
    expect(requestPermission).not.toHaveBeenCalled()
    expect(BrowserNotification).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Show internal demo alert' }))
    expect(screen.getByRole('status')).toHaveTextContent('DEMO ONLY')
    expect(BrowserNotification).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Allow browser demo alerts' }))
    expect(await screen.findByText('Browser permission was not granted.')).toBeInTheDocument()
    expect(requestPermission).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('shows unavailable inputs without fabricating a probability', async () => {
    vi.mocked(runReplay).mockResolvedValue({ ...result, status: 'data_unavailable', probability: null, presentation_tier: null, reason: 'Missing history', missing_features: ['rainfall_local_mm_lag1d'] })
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Open Bangladesh research replay' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Run historical replay' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Missing history')
    expect(screen.queryByText(/% model score/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show internal demo alert' })).not.toBeInTheDocument()
  })
})
