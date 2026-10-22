import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PublicAlertContext } from '../alerts/PublicAlertContext'
import { ApiError } from '../api/client'
import { getLocations } from '../api/locations'
import { getLatestWeather } from '../api/weather'
import type { ApiLocation, ApiPrediction } from '../types/location'
import type { MapLocation } from '../types/location'
import type { ApiLatestWeather } from '../types/weather'
import { WeatherMapPage } from './WeatherMapPage'

vi.mock('../api/locations', () => ({ getLocations: vi.fn() }))
vi.mock('../api/weather', () => ({ getLatestWeather: vi.fn() }))

// Leaflet needs real layout, which jsdom does not provide. The page logic is
// what is under test here, so render markers as a plain list.
vi.mock('../components/map/WeatherMap', () => ({
  WeatherMap: ({ locations }: { locations: MapLocation[] }) => (
    <ul aria-label="Map markers">
      {locations.map((location) => (
        <li key={location.id}>{location.name}</li>
      ))}
    </ul>
  ),
}))

const mockedGetLocations = vi.mocked(getLocations)
const mockedGetLatestWeather = vi.mocked(getLatestWeather)

function noWeather(locationId: number): ApiLatestWeather {
  return {
    location_id: locationId,
    status: 'no_data',
    source_type: 'synthetic',
    notice: null,
    observation: null,
  }
}

function samplePrediction(overrides: Partial<ApiPrediction> = {}): ApiPrediction {
  return {
    risk_level: 'VERY_HIGH',
    flood_probability: 0.91,
    model_version: 'sample-demo-not-a-model-result',
    is_sample: true,
    predicted_at: '2026-10-13T00:00:00Z',
    ...overrides,
  }
}

const LOCATIONS: ApiLocation[] = [
  {
    id: 1,
    slug: 'nadi',
    name: 'Nadi',
    division: 'WESTERN',
    division_label: 'Western Division',
    latitude: -17.7765,
    longitude: 177.4356,
    prediction: samplePrediction(),
  },
  {
    id: 2,
    slug: 'navua',
    name: 'Navua',
    division: 'CENTRAL',
    division_label: 'Central Division',
    latitude: -18.2167,
    longitude: 178.1667,
    prediction: null,
  },
  {
    id: 3,
    slug: 'labasa',
    name: 'Labasa',
    division: 'NORTHERN',
    division_label: 'Northern Division',
    latitude: -16.4306,
    longitude: 179.371,
    prediction: samplePrediction({
      risk_level: 'LOW',
      flood_probability: 0.14,
    }),
  },
]

function renderPage(feedOverrides: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <PublicAlertContext.Provider
        value={{
          data: [],
          setData: () => {},
          error: null,
          refreshing: false,
          updatedAt: '2026-10-20T00:00:00Z',
          refresh: () => {},
          ...feedOverrides,
        }}
      >
        <WeatherMapPage />
      </PublicAlertContext.Provider>
    </MemoryRouter>,
  )
}

function markers() {
  return within(screen.getByRole('list', { name: 'Map markers' }))
    .queryAllByRole('listitem')
    .map((item) => item.textContent)
}

describe('WeatherMapPage', () => {
  beforeEach(() => {
    mockedGetLocations.mockReset()
    mockedGetLatestWeather.mockReset()
    mockedGetLatestWeather.mockImplementation(async (locationId) =>
      noWeather(locationId),
    )
  })

  it('shows a loading state and disables filters until locations arrive', () => {
    mockedGetLocations.mockReturnValue(new Promise(() => {}))

    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent('Loading monitored locations…')
    expect(screen.getByRole('searchbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: /All risks/ })).toBeDisabled()
  })

  it('shows the error and retries when asked', async () => {
    const user = userEvent.setup()
    mockedGetLocations
      .mockRejectedValueOnce(
        new ApiError(0, 'Cannot reach the server. Check that the backend is running and try again.'),
      )
      .mockResolvedValueOnce(LOCATIONS)

    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Locations could not be loaded')
    expect(alert).toHaveTextContent('Cannot reach the server')

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('3 locations shown')).toBeInTheDocument()
    expect(mockedGetLocations).toHaveBeenCalledTimes(2)
  })

  it('shows a fallback message for unexpected errors', async () => {
    mockedGetLocations.mockRejectedValue(new Error('boom'))

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load monitored locations. Please try again.',
    )
  })

  it('renders a marker for every location', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()

    expect(await screen.findByText('3 locations shown')).toBeInTheDocument()
    expect(markers()).toEqual(['Nadi', 'Navua', 'Labasa'])
  })

  it('selects the highest risk location and labels its risk as a sample', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    const details = screen.getByRole('complementary')
    expect(await within(details).findByRole('heading', { name: 'Nadi' })).toBeInTheDocument()
    expect(within(details).getByText('Sample risk')).toBeInTheDocument()
    expect(within(details).getByText('Very high flood risk')).toBeInTheDocument()
    expect(within(details).getByText('91% flood probability')).toBeInTheDocument()
    expect(
      within(details).getByText(/Labelled sample for testing/),
    ).toBeInTheDocument()
  })

  it('fetches the stored weather feed for the selected location', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    const details = screen.getByRole('complementary')
    expect(await within(details).findByText('No observation has been stored for this location yet. Stored demo weather appears here once it has been ingested.')).toBeInTheDocument()
    expect(mockedGetLatestWeather).toHaveBeenCalledWith(1, 'synthetic', expect.any(AbortSignal))
  })

  it('shows "No prediction available" for a location without a prediction', async () => {
    const user = userEvent.setup()
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await user.click(await screen.findByRole('button', { name: /Navua/ }))

    const details = screen.getByRole('complementary')
    expect(within(details).getByRole('heading', { name: 'Navua' })).toBeInTheDocument()
    expect(within(details).getByText('No prediction available')).toBeInTheDocument()
    expect(within(details).queryByText('Sample risk')).not.toBeInTheDocument()
  })

  it('states that no approved alert is active when the public feed is empty', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    const details = screen.getByRole('complementary')
    expect(
      await within(details).findByText('No approved community alert is active for this location.'),
    ).toBeInTheDocument()
    expect(within(details).queryByText('Official public warning')).not.toBeInTheDocument()
  })

  it('filters by risk level, including locations with no prediction', async () => {
    const user = userEvent.setup()
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    await user.click(screen.getByRole('button', { name: /^No prediction/ }))
    expect(markers()).toEqual(['Navua'])

    await user.click(screen.getByRole('button', { name: /^Low/ }))
    expect(markers()).toEqual(['Labasa'])

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(markers()).toHaveLength(3)
  })

  it('searches by name and division', async () => {
    const user = userEvent.setup()
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    await user.type(screen.getByRole('searchbox'), 'northern')
    expect(markers()).toEqual(['Labasa'])
  })

  it('explains when there are no monitored locations at all', async () => {
    mockedGetLocations.mockResolvedValue([])

    renderPage()

    expect(await screen.findByText('No monitored locations yet')).toBeInTheDocument()
    expect(screen.queryByText('Loading monitored locations…')).not.toBeInTheDocument()
  })

  it('groups the visible location list under division headings in canonical order', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    const list = screen.getByLabelText('Visible monitored locations')
    expect(
      within(list)
        .getAllByRole('heading', { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(['Central Division', 'Western Division', 'Northern Division'])
  })

  it('filters by division and combines with the risk filter', async () => {
    const user = userEvent.setup()
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    await user.click(screen.getByRole('button', { name: /^Western/ }))
    expect(markers()).toEqual(['Nadi'])

    // Low risk exists only in the Northern Division, so the filters combine to
    // an empty result.
    await user.click(screen.getByRole('button', { name: /^Low/ }))
    expect(markers()).toEqual([])

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(markers()).toHaveLength(3)
  })

  it('shows an alerts-feed error banner when approved alerts cannot be loaded', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage({ error: 'Cannot reach the alerts feed.' })

    expect(
      await screen.findByText(/Approved alerts shown here may be out of date/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Cannot reach the alerts feed\./),
    ).toBeInTheDocument()
  })

  it('labels a prediction older than 24 hours as stale', async () => {
    mockedGetLocations.mockResolvedValue(LOCATIONS)

    renderPage()
    await screen.findByText('3 locations shown')

    const details = screen.getByRole('complementary')
    expect(await within(details).findByText('Stale')).toBeInTheDocument()
    expect(
      within(details).getByText(/more than 24 hours old/),
    ).toBeInTheDocument()
  })

  it('does not label a fresh prediction as stale', async () => {
    mockedGetLocations.mockResolvedValue(
      LOCATIONS.map((location) =>
        location.slug === 'nadi'
          ? {
              ...location,
              prediction: samplePrediction({
                predicted_at: new Date().toISOString(),
              }),
            }
          : location,
      ),
    )

    renderPage()
    await screen.findByText('3 locations shown')

    const details = screen.getByRole('complementary')
    expect(within(details).queryByText('Stale')).not.toBeInTheDocument()
    expect(
      within(details).queryByText(/more than 24 hours old/),
    ).not.toBeInTheDocument()
  })
})
