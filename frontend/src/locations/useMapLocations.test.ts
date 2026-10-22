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
    const location = toMapLocation({
      ...navua,
      prediction: {
        risk_level: 'HIGH',
        flood_probability: 0.736,
        model_version: 'sample-demo-not-a-model-result',
        is_sample: true,
        predicted_at: '2026-10-13T00:00:00Z',
      },
    })

    expect(location).toMatchObject({
      id: 'navua',
      apiId: 1,
      division: 'Central Division',
      riskLevel: 'HIGH',
      prediction: {
        riskLevel: 'HIGH',
        floodProbabilityPercent: 74,
        provenance: 'sample',
        modelVersion: 'sample-demo-not-a-model-result',
        predictedAt: '2026-10-13T00:00:00Z',
      },
    })
  })

  it('maps a stored model prediction as model provenance', () => {
    const location = toMapLocation({
      ...navua,
      prediction: {
        risk_level: 'HIGH',
        flood_probability: 0.736,
        model_version: 'synthetic-fiji-v1-catboost__none',
        is_sample: false,
        predicted_at: '2026-10-20T00:00:00Z',
      },
    })

    expect(location.prediction).toMatchObject({
      provenance: 'model',
      modelVersion: 'synthetic-fiji-v1-catboost__none',
    })
  })

  it('leaves risk empty when no prediction is available', () => {
    const location = toMapLocation(navua)

    expect(location.riskLevel).toBeNull()
    expect(location.prediction).toBeNull()
  })
})
