import { describe, expect, it } from 'vitest'
import type { ApiLocation } from '../types/location'
import { toMapLocation } from './useMapLocations'

const navua: ApiLocation = {
  id: 1,
  slug: 'navua',
  name: 'Navua',
  division: 'CENTRAL',
  division_label: 'Central Division',
  latitude: -18.2167,
  longitude: 178.1667,
  prediction: null,
}

describe('toMapLocation', () => {
  it('maps a location with a sample prediction', () => {
    const location = toMapLocation(
      {
        ...navua,
        prediction: {
          risk_level: 'HIGH',
          flood_probability: 0.736,
          model_version: 'sample-demo-not-a-model-result',
          is_sample: true,
          predicted_at: '2026-10-13T00:00:00Z',
        },
      },
      null,
    )

    expect(location).toMatchObject({
      id: 'navua',
      division: 'Central Division',
      riskLevel: 'HIGH',
      prediction: {
        riskLevel: 'HIGH',
        floodProbabilityPercent: 74,
        isSample: true,
        predictedAt: '2026-10-13T00:00:00Z',
      },
    })
  })

  it('leaves risk empty when no prediction is available', () => {
    const location = toMapLocation(navua, null)

    expect(location.riskLevel).toBeNull()
    expect(location.prediction).toBeNull()
  })
})
