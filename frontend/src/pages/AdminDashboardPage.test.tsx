import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAdminAlerts, usePublicAlerts } from '../alerts/useAlertFeed'
import { getLocations } from '../api/locations'
import type { AdminAlert, PublicAlert } from '../types/alert'
import type { ApiLocation } from '../types/location'
import { AdminDashboardPage } from './AdminDashboardPage'

vi.mock('../api/locations', () => ({ getLocations: vi.fn() }))
vi.mock('../alerts/useAlertFeed', () => ({
  useAdminAlerts: vi.fn(),
  usePublicAlerts: vi.fn(),
}))

const mockedGetLocations = vi.mocked(getLocations)
const mockedUseAdminAlerts = vi.mocked(useAdminAlerts)
const mockedUsePublicAlerts = vi.mocked(usePublicAlerts)

interface Feed<T> {
  data: T[] | null
  setData: () => void
  error: string | null
  refreshing: boolean
  updatedAt: string | null
  refresh: () => void
}

function feed<T>(overrides: Partial<Feed<T>> = {}): Feed<T> {
  return {
    data: [],
    setData: () => {},
    error: null,
    refreshing: false,
    updatedAt: '2026-10-20T00:00:00Z',
    refresh: () => {},
    ...overrides,
  }
}

function location(overrides: Partial<ApiLocation> = {}): ApiLocation {
  return {
    id: 1,
    slug: 'suva',
    name: 'Suva',
    division: 'CENTRAL',
    division_label: 'Central Division',
    latitude: -18.14,
    longitude: 178.44,
    prediction: null,
    ...overrides,
  }
}

function adminAlert(overrides: Partial<AdminAlert> = {}): AdminAlert {
  return {
    id: 41,
    location_id: 1,
    location: { id: 1, name: 'Suva', is_active: true },
    prediction_id: null,
    severity: 'HIGH',
    status: 'PENDING',
    source: 'MET_OFFICIAL',
    message: 'TEST ONLY: Move to higher ground.',
    created_at: '2026-10-14T00:00:00Z',
    approved_at: null,
    updated_at: null,
    rejected_at: null,
    suppressed_at: null,
    suppression_reason: null,
    ...overrides,
  }
}

const LOCATIONS: ApiLocation[] = [
  location({
    prediction: {
      risk_level: 'VERY_HIGH',
      flood_probability: 0.91,
      model_version: 'sample-demo-not-a-model-result',
      is_sample: true,
      predicted_at: '2026-10-19T22:00:00Z',
    },
  }),
  location({
    id: 2,
    slug: 'nadi',
    name: 'Nadi',
    division: 'WESTERN',
    division_label: 'Western Division',
    prediction: {
      risk_level: 'LOW',
      flood_probability: 0.12,
      model_version: 'sample-demo-not-a-model-result',
      is_sample: true,
      predicted_at: '2026-10-19T23:00:00Z',
    },
  }),
  location({
    id: 3,
    slug: 'labasa',
    name: 'Labasa',
    division: 'NORTHERN',
    division_label: 'Northern Division',
  }),
]

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminDashboardPage />
    </MemoryRouter>,
  )
}

describe('AdminDashboardPage', () => {
  beforeEach(() => {
    mockedGetLocations.mockReset()
    mockedUseAdminAlerts.mockReset()
    mockedUsePublicAlerts.mockReset()
    mockedUseAdminAlerts.mockReturnValue(feed<AdminAlert>())
    mockedUsePublicAlerts.mockReturnValue(feed<PublicAlert>())
  })

  it('derives registry metrics and recent predictions from the live location feed', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()

    const metrics = await screen.findByRole('region', { name: 'Operational summary' })
    const cards = within(metrics).getAllByRole('article')
    const locationsCard = cards.find((card) => card.textContent?.includes('Monitored locations'))
    expect(locationsCard).toHaveTextContent('3')
    expect(locationsCard).toHaveTextContent('Across 3 divisions')
    const highRiskCard = cards.find((card) => card.textContent?.includes('High-risk areas'))
    expect(highRiskCard).toHaveTextContent('1')

    expect(await screen.findByText('91% probability')).toBeInTheDocument()
    expect(screen.getByText('12% probability')).toBeInTheDocument()
    // Sorted by predicted_at, newest first.
    const items = screen.getAllByRole('article').filter((node) =>
      node.classList.contains('prediction-item'),
    )
    expect(items[0]).toHaveTextContent('Nadi')
    expect(items[1]).toHaveTextContent('Suva')
  })

  it('counts high-risk areas only where a prediction says so', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    const metrics = await screen.findByRole('region', { name: 'Operational summary' })
    const highRiskCard = within(metrics)
      .getAllByRole('article')
      .find((card) => card.textContent?.includes('High-risk areas'))
    expect(highRiskCard).toHaveTextContent('1')
  })

  it('shows alert counts from the live feeds', async () => {
    mockedUseAdminAlerts.mockReturnValue(
      feed<AdminAlert>({ data: [adminAlert(), adminAlert({ id: 42, status: 'APPROVED' })] }),
    )
    mockedUsePublicAlerts.mockReturnValue(
      feed<PublicAlert>({
        data: [adminAlert({ id: 43, status: 'APPROVED' }) as unknown as PublicAlert],
      }),
    )
    mockedGetLocations.mockResolvedValue([])

    renderPage()

    const metrics = await screen.findByRole('region', { name: 'Operational summary' })
    const cards = within(metrics).getAllByRole('article')
    expect(
      cards.find((card) => card.textContent?.includes('Active alerts')),
    ).toHaveTextContent('1')
    expect(
      cards.find((card) => card.textContent?.includes('Pending alerts')),
    ).toHaveTextContent('1')
  })

  it('shows a loading state for registry metrics until locations arrive', () => {
    mockedGetLocations.mockReturnValue(new Promise(() => {}))

    renderPage()

    const metrics = screen.getByRole('region', { name: 'Operational summary' })
    expect(within(metrics).getByText('Loading location registry…')).toBeInTheDocument()
    expect(screen.getByText('Loading predictions…')).toBeInTheDocument()
  })

  it('surfaces location-feed errors without inventing numbers', async () => {
    mockedGetLocations.mockRejectedValue(new Error('registry down'))

    renderPage()

    expect(
      await screen.findByText(/Monitored-location metrics are unavailable/),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Predictions are unavailable because the location registry could not be loaded.'),
    ).toBeInTheDocument()
  })
})
