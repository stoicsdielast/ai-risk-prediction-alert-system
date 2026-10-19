import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getLatestWeather } from '../../api/weather'
import type { PublicAlert } from '../../types/alert'
import type { MapLocation } from '../../types/location'
import type { ApiLatestWeather, ApiWeatherObservation } from '../../types/weather'
import { LocationDetailCard } from './LocationDetailCard'

vi.mock('../../api/weather', () => ({ getLatestWeather: vi.fn() }))

const mockedGetLatestWeather = vi.mocked(getLatestWeather)

const nadi: MapLocation = {
  id: 'nadi',
  apiId: 1,
  name: 'Nadi',
  division: 'Western Division',
  latitude: -17.7765,
  longitude: 177.4356,
  riskLevel: 'VERY_HIGH',
  prediction: {
    riskLevel: 'VERY_HIGH',
    floodProbabilityPercent: 91,
    provenance: 'sample',
    modelVersion: 'sample-demo-not-a-model-result',
    // Fresh relative to the real clock so staleness tests stay deterministic.
    predictedAt: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  },
}

function observation(
  overrides: Partial<ApiWeatherObservation> = {},
): ApiWeatherObservation {
  return {
    id: 10,
    location_id: 1,
    observed_at: '2026-10-19T22:00:00Z',
    received_at: '2026-10-19T22:01:00Z',
    source: 'synthetic-fiji-v1-weather',
    source_type: 'synthetic',
    rainfall_mm: 12.5,
    rainfall_period_minutes: 60,
    temperature_c: 26.4,
    humidity_pct: 91,
    pressure_hpa: null,
    wind_speed_mps: 8.2,
    wind_direction_deg: 110,
    river_level_m: 3.7,
    river_discharge_m3s: null,
    soil_moisture_pct: null,
    upstream_rainfall_mm: null,
    upstream_rainfall_period_minutes: null,
    coastal_tide_m: null,
    gauge_datum: 'synthetic-fiji-v1-simulated-datum',
    missing_fields: ['pressure_hpa'],
    stale: false,
    age_seconds: 600,
    notice: 'Synthetic research demonstration only; not Fiji MET readings or a real forecast.',
    ...overrides,
  }
}

function latest(
  observationRow: ApiWeatherObservation | null,
  status: ApiLatestWeather['status'] = observationRow ? 'fresh' : 'no_data',
): ApiLatestWeather {
  return {
    location_id: 1,
    status,
    source_type: 'synthetic',
    notice: null,
    observation: observationRow,
  }
}

function sampleAlert(overrides: Partial<PublicAlert> = {}): PublicAlert {
  return {
    id: 51,
    location_id: 1,
    location: { id: 1, name: 'Nadi' },
    prediction_id: null,
    severity: 'HIGH',
    status: 'APPROVED',
    source: 'MET_OFFICIAL',
    message: 'TEST ONLY: Move to higher ground.',
    created_at: '2026-10-19T20:00:00Z',
    approved_at: '2026-10-19T20:30:00Z',
    ...overrides,
  }
}

describe('LocationDetailCard', () => {
  beforeEach(() => {
    mockedGetLatestWeather.mockReset()
    mockedGetLatestWeather.mockImplementation(async () => latest(null))
  })

  it('shows an empty state when no location is selected', () => {
    render(<LocationDetailCard location={null} />)

    expect(screen.getByRole('heading', { name: 'No location selected' })).toBeInTheDocument()
    expect(mockedGetLatestWeather).not.toHaveBeenCalled()
  })

  it('renders stored synthetic measurements and labels the source', async () => {
    mockedGetLatestWeather.mockResolvedValue(latest(observation()))

    render(<LocationDetailCard location={nadi} />)

    const details = screen.getByRole('complementary')
    expect(await within(details).findByText('Synthetic demo data')).toBeInTheDocument()
    expect(within(details).getByText('26.4°C')).toBeInTheDocument()
    expect(within(details).getByText('12.5 mm')).toBeInTheDocument()
    expect(within(details).getByText('Per 60-minute interval')).toBeInTheDocument()
    expect(within(details).getByText('91%')).toBeInTheDocument()
    expect(within(details).getByText('8.2 m/s')).toBeInTheDocument()
    expect(within(details).getByText('3.7 m')).toBeInTheDocument()
    expect(within(details).getByText('synthetic-fiji-v1-simulated-datum')).toBeInTheDocument()
    // Null channels are omitted rather than shown as zeros.
    expect(within(details).queryByText('Pressure')).not.toBeInTheDocument()
    expect(
      within(details).getByText(/Synthetic research demonstration only/),
    ).toBeInTheDocument()
    expect(mockedGetLatestWeather).toHaveBeenCalledWith(1, 'synthetic', expect.any(AbortSignal))
  })

  it('explains when no observation has been stored', async () => {
    render(<LocationDetailCard location={nadi} />)

    expect(
      await screen.findByText(/No observation has been stored for this location yet/),
    ).toBeInTheDocument()
  })

  it('surfaces weather-feed errors and retries on demand', async () => {
    const user = userEvent.setup()
    mockedGetLatestWeather
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(latest(observation()))

    render(<LocationDetailCard location={nadi} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Weather observations are unavailable.')
    expect(alert).toHaveTextContent('Unable to load weather observations. Please try again.')

    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('26.4°C')).toBeInTheDocument()
    expect(mockedGetLatestWeather).toHaveBeenCalledTimes(2)
  })

  it('marks stale observations', async () => {
    mockedGetLatestWeather.mockResolvedValue(
      latest(observation({ stale: true }), 'stale'),
    )

    render(<LocationDetailCard location={nadi} />)

    expect(await screen.findByText('Stale')).toBeInTheDocument()
  })

  it('handles an observation without any measurement values', async () => {
    mockedGetLatestWeather.mockResolvedValue(
      latest(
        observation({
          rainfall_mm: null,
          rainfall_period_minutes: null,
          temperature_c: null,
          humidity_pct: null,
          wind_speed_mps: null,
          wind_direction_deg: null,
          river_level_m: null,
        }),
      ),
    )

    render(<LocationDetailCard location={nadi} />)

    expect(
      await screen.findByText('This observation was stored without measurement values.'),
    ).toBeInTheDocument()
  })

  it('lists approved public alerts for the location', () => {
    render(<LocationDetailCard location={nadi} activeAlerts={[sampleAlert()]} />)

    const alertsPanel = screen.getByLabelText('Approved public alerts')
    expect(within(alertsPanel).getByText('Approved alert')).toBeInTheDocument()
    expect(within(alertsPanel).getByText('TEST ONLY: Move to higher ground.')).toBeInTheDocument()
    expect(within(alertsPanel).getByText('MET official')).toBeInTheDocument()
    expect(within(alertsPanel).getByText('High')).toBeInTheDocument()
    expect(within(alertsPanel).getByText(/take precedence/)).toBeInTheDocument()
  })

  it('states when no approved alert is active', () => {
    render(<LocationDetailCard location={nadi} activeAlerts={[]} />)

    expect(
      screen.getByText('No approved community alert is active for this location.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Official public warning')).not.toBeInTheDocument()
  })

  it('marks a prediction older than 24 hours as stale', () => {
    const stalePrediction: MapLocation = {
      ...nadi,
      prediction: {
        ...nadi.prediction!,
        predictedAt: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(),
      },
    }

    render(<LocationDetailCard location={stalePrediction} />)

    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText(/more than 24 hours old/)).toBeInTheDocument()
  })

  it('shows the model version for a stored model prediction', () => {
    const modelPrediction: MapLocation = {
      ...nadi,
      prediction: {
        ...nadi.prediction!,
        provenance: 'model',
        modelVersion: 'synthetic-fiji-v1-catboost__none',
      },
    }

    render(<LocationDetailCard location={modelPrediction} />)

    expect(screen.getByText('AI prediction')).toBeInTheDocument()
    expect(
      screen.getByText(
        /Model synthetic-fiji-v1-catboost__none · decision-support estimate/,
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Sample risk')).not.toBeInTheDocument()
  })

  it('labels synthetic research predictions distinctly from samples', () => {
    const syntheticPrediction: MapLocation = {
      ...nadi,
      prediction: {
        ...nadi.prediction!,
        provenance: 'synthetic',
        modelVersion: 'synthetic-fiji-v1-catboost__none',
      },
    }

    render(<LocationDetailCard location={syntheticPrediction} />)

    expect(screen.getByText('Synthetic research')).toBeInTheDocument()
    expect(
      screen.getByText(/Synthetic research simulation/),
    ).toBeInTheDocument()
    expect(screen.queryByText('Sample risk')).not.toBeInTheDocument()
  })
})
