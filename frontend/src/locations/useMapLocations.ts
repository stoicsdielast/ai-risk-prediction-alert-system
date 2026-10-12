import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { getLocations } from '../api/locations'
import { usePrototypeData } from '../prototype/usePrototypeData'
import type { ApiLocation, MapLocation } from '../types/location'
import type { WeatherLocation } from '../types/prototype'

export type MapLocationsStatus = 'loading' | 'error' | 'ready'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; locations: ApiLocation[] }

export function toMapLocation(
  location: ApiLocation,
  conditions: WeatherLocation | null,
): MapLocation {
  const { prediction } = location

  return {
    id: location.slug,
    name: location.name,
    division: location.division_label,
    latitude: location.latitude,
    longitude: location.longitude,
    riskLevel: prediction?.risk_level ?? null,
    prediction: prediction && {
      riskLevel: prediction.risk_level,
      confidencePercent: prediction.confidence_percent,
      label: prediction.label,
      summary: prediction.summary,
      isSample: prediction.is_sample,
      generatedAt: prediction.generated_at,
    },
    conditions,
  }
}

export function useMapLocations() {
  const { locations: prototypeLocations } = usePrototypeData()
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })

    getLocations(controller.signal)
      .then((locations) => setState({ status: 'ready', locations }))
      .catch((caughtError: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          message:
            caughtError instanceof ApiError
              ? caughtError.message
              : 'Unable to load monitored locations. Please try again.',
        })
      })

    return () => controller.abort()
  }, [attempt])

  const locations = useMemo(() => {
    if (state.status !== 'ready') return []

    // Locations and risk predictions come from the backend. Weather and
    // official warnings are still prototype data, matched by slug.
    const conditionsById = new Map(
      prototypeLocations.map((location) => [location.id, location]),
    )
    return state.locations.map((location) =>
      toMapLocation(location, conditionsById.get(location.slug) ?? null),
    )
  }, [prototypeLocations, state])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  return {
    status: state.status,
    error: state.status === 'error' ? state.message : null,
    locations,
    retry,
  }
}
