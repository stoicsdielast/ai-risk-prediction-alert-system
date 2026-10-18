import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getActiveAlerts } from '../api/alerts'
import { ApiError } from '../api/client'
import {
  getPriorityLocations,
  removePriorityLocation,
} from '../api/priorityLocations'
import type { AuthContextValue } from '../auth/AuthContext'
import { useAuth } from '../auth/useAuth'
import type { ApiAlert } from '../types/alert'
import type { ApiLocation } from '../types/location'
import { DashboardPage } from './DashboardPage'

vi.mock('../api/alerts', () => ({ getActiveAlerts: vi.fn() }))
vi.mock('../api/priorityLocations', () => ({
  getPriorityLocations: vi.fn(),
  savePriorityLocation: vi.fn(),
  removePriorityLocation: vi.fn(),
}))
vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))

const mockedGetActiveAlerts = vi.mocked(getActiveAlerts)
const mockedGetPriorityLocations = vi.mocked(getPriorityLocations)
const mockedRemovePriorityLocation = vi.mocked(removePriorityLocation)

const NADI: ApiLocation = {
  slug: 'nadi',
  name: 'Nadi',
  division: 'WESTERN',
  division_label: 'Western Division',
  latitude: -17.7765,
  longitude: 177.4356,
  prediction: {
    risk_level: 'VERY_HIGH',
    flood_probability: 0.91,
    model_version: 'sample-demo-not-a-model-result',
    is_sample: true,
    predicted_at: '2026-10-13T00:00:00Z',
  },
}

const LABASA: ApiLocation = {
  slug: 'labasa',
  name: 'Labasa',
  division: 'NORTHERN',
  division_label: 'Northern Division',
  latitude: -16.4306,
  longitude: 179.371,
  prediction: null,
}

function alertFor(location: ApiLocation, overrides: Partial<ApiAlert> = {}): ApiAlert {
  return {
    id: location.slug.length,
    location_id: location.slug.length,
    location,
    prediction_id: null,
    prediction: null,
    severity: 'HIGH',
    status: 'APPROVED',
    source: 'MET_OFFICIAL',
    message: `TEST ONLY — flood alert for ${location.name}.`,
    created_at: '2026-10-13T00:00:00Z',
    approved_at: '2026-10-13T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

function card(label: string) {
  return screen.getByText(label, { selector: '.metric-card__label' }).closest('article')!
}

describe('DashboardPage', () => {
  beforeEach(() => {
    mockedGetActiveAlerts.mockReset()
    mockedGetPriorityLocations.mockReset()
    mockedRemovePriorityLocation.mockReset()
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 7,
        name: 'Test Community User',
        email: 'community@example.com',
        role: 'COMMUNITY',
        status: 'APPROVED',
      },
      token: 'test-token',
      isLoading: false,
      sessionError: null,
      login: vi.fn(),
      logout: vi.fn(),
      retrySession: vi.fn(),
    } satisfies AuthContextValue)
  })

  it('no longer shows the prototype milestone cards', async () => {
    mockedGetActiveAlerts.mockResolvedValue([])
    mockedGetPriorityLocations.mockResolvedValue([])

    renderPage()
    await screen.findByText(/no active flood alerts right now/)

    expect(screen.queryByText('What this milestone demonstrates')).not.toBeInTheDocument()
    expect(screen.queryByText('Prototype weather view')).not.toBeInTheDocument()
  })

  it('summarises alerts and priority areas', async () => {
    mockedGetActiveAlerts.mockResolvedValue([alertFor(LABASA), alertFor(NADI)])
    mockedGetPriorityLocations.mockResolvedValue([NADI])

    renderPage()
    await screen.findByText(/flood alert for Nadi/)

    expect(within(card('Active alerts')).getByText('2')).toBeInTheDocument()
    expect(within(card('Alerts in your areas')).getByText('1')).toBeInTheDocument()
    expect(within(card('Priority areas')).getByText('1')).toBeInTheDocument()
    const highRisk = card('High-risk priority areas')
    expect(within(highRisk).getByText('1')).toBeInTheDocument()
    expect(within(highRisk).getByText(/includes labelled sample risks/)).toBeInTheDocument()
  })

  it('lists alerts in priority areas first and marks them', async () => {
    mockedGetActiveAlerts.mockResolvedValue([alertFor(LABASA), alertFor(NADI)])
    mockedGetPriorityLocations.mockResolvedValue([NADI])

    renderPage()
    await screen.findByText(/flood alert for Nadi/)

    const alerts = within(screen.getByRole('region', { name: 'Active flood alerts' }))
      .getAllByRole('listitem')
    expect(alerts.map((item) => item.querySelector('strong')?.textContent)).toEqual([
      'Nadi',
      'Labasa',
    ])
    expect(alerts[0]).toHaveTextContent('Your priority area')
    expect(alerts[1]).not.toHaveTextContent('Your priority area')
  })

  it('shows dashes and an error with retry when alerts cannot load', async () => {
    const user = userEvent.setup()
    mockedGetActiveAlerts
      .mockRejectedValueOnce(new ApiError(0, 'Cannot reach the server.'))
      .mockResolvedValueOnce([])
    mockedGetPriorityLocations.mockResolvedValue([])

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server.')
    expect(within(card('Active alerts')).getByText('–')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/no active flood alerts right now/)).toBeInTheDocument()
  })

  it('updates the summary when a priority area is removed', async () => {
    const user = userEvent.setup()
    mockedGetActiveAlerts.mockResolvedValue([alertFor(NADI)])
    mockedGetPriorityLocations.mockResolvedValue([NADI])
    mockedRemovePriorityLocation.mockResolvedValue(undefined)

    renderPage()
    await user.click(
      await screen.findByRole('button', { name: 'Remove Nadi from priority areas' }),
    )

    expect(await within(card('Priority areas')).findByText('0')).toBeInTheDocument()
    expect(within(card('Alerts in your areas')).getByText('0')).toBeInTheDocument()
    expect(screen.queryByText('Your priority area')).not.toBeInTheDocument()
  })
})
