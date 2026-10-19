import { useMemo } from 'react'
import { useLocations } from './useLocations'
import type { ApiLocation, MapLocation } from '../types/location'

export function toMapLocation(location: ApiLocation): MapLocation {
  const { prediction } = location

  return {
    id: location.slug,
    apiId: location.id,
    name: location.name,
    division: location.division_label,
    latitude: location.latitude,
    longitude: location.longitude,
    riskLevel: prediction?.risk_level ?? null,
    prediction: prediction && {
      riskLevel: prediction.risk_level,
      floodProbabilityPercent: Math.round(prediction.flood_probability * 100),
      isSample: prediction.is_sample,
      predictedAt: prediction.predicted_at,
    },
  }
}

export function useMapLocations() {
  const { status, error, locations, retry } = useLocations()
  const mappedLocations = useMemo(
    () => locations.map(toMapLocation),
    [locations],
  )

  return {
    status,
    error,
    locations: mappedLocations,
    retry,
  }
}
