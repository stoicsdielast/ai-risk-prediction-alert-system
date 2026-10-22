import { afterEach, expect, it, vi } from 'vitest'
import { getLatestWeather } from './weather'

afterEach(() => vi.unstubAllGlobals())

const SAMPLE = {
  location_id: 2,
  status: 'fresh',
  source_type: 'synthetic',
  notice: 'Synthetic research demonstration only; not Fiji MET readings or a real forecast.',
  observation: {
    id: 10,
    location_id: 2,
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
    gauge_datum: null,
    missing_fields: ['pressure_hpa'],
    stale: false,
    age_seconds: 600,
    notice: null,
  },
}

it('requests the synthetic dataset by default', async () => {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(SAMPLE), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  vi.stubGlobal('fetch', fetchMock)

  const result = await getLatestWeather(2)

  expect(String(fetchMock.mock.calls[0][0])).toContain(
    '/api/weather/latest?location_id=2&dataset=synthetic',
  )
  expect(result.observation?.rainfall_mm).toBe(12.5)
})

it('supports the genuine dataset when explicitly requested', async () => {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ ...SAMPLE, source_type: 'genuine', observation: null, status: 'no_data' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await getLatestWeather(2, 'genuine')

  expect(String(fetchMock.mock.calls[0][0])).toContain('dataset=genuine')
})
