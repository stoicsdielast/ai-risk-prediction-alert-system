import { describe, expect, it } from 'vitest'
import type { ApiLocation } from '../types/location'
import { toMapLocation } from './useMapLocations'

const navua: ApiLocation = {
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
          confidence_percent: 84,
          label: 'High lowland flood potential',
          summary: 'Summary',
          source: 'SAMPLE',
          is_sample: true,
          generated_at: '2026-10-13T00:00:00Z',
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
        confidencePercent: 84,
        label: 'High lowland flood potential',
        isSample: true,
      },
    })
  })

  it('leaves risk empty when no prediction is available', () => {
    const location = toMapLocation(navua, null)

    expect(location.riskLevel).toBeNull()
    expect(location.prediction).toBeNull()
  })
})
