import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getLocations } from '../api/locations'
import type { ApiLocation } from '../types/location'

export type LocationsStatus = 'loading' | 'error' | 'ready'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; locations: ApiLocation[] }

export function useLocations() {
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

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  return {
    status: state.status,
    error: state.status === 'error' ? state.message : null,
    locations: state.status === 'ready' ? state.locations : [],
    retry,
  }
}
