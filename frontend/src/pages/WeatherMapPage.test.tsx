import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { getLocations } from '../api/locations'
import {
  getPriorityLocations,
  removePriorityLocation,
  savePriorityLocation,
} from '../api/priorityLocations'
import type { AuthContextValue } from '../auth/AuthContext'
import { useAuth } from '../auth/useAuth'
import { PrototypeDataProvider } from '../prototype/PrototypeDataProvider'
import type { User } from '../types/auth'
import type { ApiLocation, ApiPrediction } from '../types/location'
import type { MapLocation } from '../types/location'
import { WeatherMapPage } from './WeatherMapPage'

vi.mock('../api/locations', () => ({ getLocations: vi.fn() }))
vi.mock('../api/priorityLocations', () => ({
  getPriorityLocations: vi.fn(),
  savePriorityLocation: vi.fn(),
  removePriorityLocation: vi.fn(),
}))
vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))

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
const mockedGetPriorityLocations = vi.mocked(getPriorityLocations)
const mockedSavePriorityLocation = vi.mocked(savePriorityLocation)
const mockedRemovePriorityLocation = vi.mocked(removePriorityLocation)
const mockedUseAuth = vi.mocked(useAuth)

const COMMUNITY_USER: User = {
  id: 7,
  name: 'Test Community User',
  email: 'community@example.com',
  role: 'COMMUNITY',
  status: 'APPROVED',
}

function signIn(user: User | null) {
  mockedUseAuth.mockReturnValue({
    user,
    token: user ? 'test-token' : null,
    isLoading: false,
    sessionError: null,
    login: vi.fn(),
    logout: vi.fn(),
    retrySession: vi.fn(),
  } satisfies AuthContextValue)
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
    slug: 'nadi',
    name: 'Nadi',
    division: 'WESTERN',
    division_label: 'Western Division',
    latitude: -17.7765,
    longitude: 177.4356,
    prediction: samplePrediction(),
  },
  {
    slug: 'navua',
    name: 'Navua',
    division: 'CENTRAL',
    division_label: 'Central Division',
    latitude: -18.2167,
    longitude: 178.1667,
    prediction: null,
  },
  {
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

function renderPage() {
  return render(
    <PrototypeDataProvider>
      <WeatherMapPage />
    </PrototypeDataProvider>,
  )
}

function markers() {
  return within(screen.getByRole('list', { name: 'Map markers' }))
    .getAllByRole('listitem')
    .map((item) => item.textContent)
}

describe('WeatherMapPage', () => {
  beforeEach(() => {
    mockedGetLocations.mockReset()
    mockedGetPriorityLocations.mockReset()
    mockedSavePriorityLocation.mockReset()
    mockedRemovePriorityLocation.mockReset()
    signIn(null)
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
    expect(within(details).getByRole('heading', { name: 'Nadi' })).toBeInTheDocument()
    expect(within(details).getByText('Sample risk')).toBeInTheDocument()
    expect(within(details).getByText('Very high flood risk')).toBeInTheDocument()
    expect(within(details).getByText('91% flood probability')).toBeInTheDocument()
    expect(
      within(details).getByText(/Labelled sample for testing/),
    ).toBeInTheDocument()
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

  describe('priority areas', () => {
    it('offers no save controls to visitors who are not signed in', async () => {
      mockedGetLocations.mockResolvedValue(LOCATIONS)

      renderPage()
      await screen.findByText('3 locations shown')

      expect(
        screen.queryByRole('button', { name: /priority area/ }),
      ).not.toBeInTheDocument()
      expect(mockedGetPriorityLocations).not.toHaveBeenCalled()
    })

    it('lets a signed-in user save the selected location', async () => {
      const user = userEvent.setup()
      signIn(COMMUNITY_USER)
      mockedGetLocations.mockResolvedValue(LOCATIONS)
      mockedGetPriorityLocations.mockResolvedValue([])
      mockedSavePriorityLocation.mockResolvedValue(LOCATIONS[0])

      renderPage()
      await screen.findByText('3 locations shown')
      const details = screen.getByRole('complementary')
      await user.click(
        await within(details).findByRole('button', { name: 'Save as priority area' }),
      )

      expect(mockedSavePriorityLocation).toHaveBeenCalledWith('test-token', 'nadi')
      expect(
        await within(details).findByRole('button', { name: 'Saved as priority area' }),
      ).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByRole('button', { name: /My priority areas/ })).toHaveTextContent('1')
    })

    it('marks saved locations and filters to them', async () => {
      const user = userEvent.setup()
      signIn(COMMUNITY_USER)
      mockedGetLocations.mockResolvedValue(LOCATIONS)
      mockedGetPriorityLocations.mockResolvedValue([LOCATIONS[2]])

      renderPage()
      await screen.findByText('3 locations shown')

      expect(
        await screen.findByRole('button', { name: /Labasa.*Priority area/ }),
      ).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /My priority areas/ }))
      expect(markers()).toEqual(['Labasa'])

      await user.click(screen.getByRole('button', { name: 'Clear filters' }))
      expect(markers()).toHaveLength(3)
    })

    it('removes a saved location', async () => {
      const user = userEvent.setup()
      signIn(COMMUNITY_USER)
      mockedGetLocations.mockResolvedValue(LOCATIONS)
      mockedGetPriorityLocations.mockResolvedValue([LOCATIONS[0]])
      mockedRemovePriorityLocation.mockResolvedValue(undefined)

      renderPage()
      await screen.findByText('3 locations shown')
      const details = screen.getByRole('complementary')
      await user.click(
        await within(details).findByRole('button', { name: 'Saved as priority area' }),
      )

      expect(mockedRemovePriorityLocation).toHaveBeenCalledWith('test-token', 'nadi')
      expect(
        await within(details).findByRole('button', { name: 'Save as priority area' }),
      ).toHaveAttribute('aria-pressed', 'false')
    })

    it('shows an error when saving fails and keeps the location unsaved', async () => {
      const user = userEvent.setup()
      signIn(COMMUNITY_USER)
      mockedGetLocations.mockResolvedValue(LOCATIONS)
      mockedGetPriorityLocations.mockResolvedValue([])
      mockedSavePriorityLocation.mockRejectedValue(new ApiError(500, 'Unable to update priority locations'))

      renderPage()
      await screen.findByText('3 locations shown')
      const details = screen.getByRole('complementary')
      await user.click(
        await within(details).findByRole('button', { name: 'Save as priority area' }),
      )

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Unable to update priority locations',
      )
      expect(
        within(details).getByRole('button', { name: 'Save as priority area' }),
      ).toBeEnabled()
    })

    it('keeps the map usable when priority areas cannot be loaded', async () => {
      const user = userEvent.setup()
      signIn(COMMUNITY_USER)
      mockedGetLocations.mockResolvedValue(LOCATIONS)
      mockedGetPriorityLocations
        .mockRejectedValueOnce(new Error('boom'))
        .mockResolvedValueOnce([])

      renderPage()

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Unable to load your priority areas. Please try again.',
      )
      expect(markers()).toHaveLength(3)

      await user.click(screen.getByRole('button', { name: 'Try again' }))
      expect(
        await screen.findByRole('button', { name: 'Save as priority area' }),
      ).toBeInTheDocument()
    })
  })
})
