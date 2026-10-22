import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getLatestWeather } from '../api/weather'
import type { ApiLatestWeather } from '../types/weather'

export type LocationWeatherStatus = 'idle' | 'loading' | 'error' | 'ready'

type WeatherState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; latest: ApiLatestWeather }

export function useLocationWeather(locationId: number | null) {
  const [state, setState] = useState<WeatherState>({ status: 'idle' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (locationId === null) {
      setState({ status: 'idle' })
      return
    }

    const controller = new AbortController()
    setState({ status: 'loading' })

    getLatestWeather(locationId, 'synthetic', controller.signal)
      .then((latest) => {
        if (!controller.signal.aborted) setState({ status: 'ready', latest })
      })
      .catch((caughtError: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          message:
            caughtError instanceof ApiError
              ? caughtError.message
              : 'Unable to load weather observations. Please try again.',
        })
      })

    return () => controller.abort()
  }, [locationId, attempt])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  return {
    status: state.status,
    error: state.status === 'error' ? state.message : null,
    latest: state.status === 'ready' ? state.latest : null,
    retry,
  }
}
