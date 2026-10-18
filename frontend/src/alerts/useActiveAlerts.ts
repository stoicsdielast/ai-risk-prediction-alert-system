import { useCallback, useEffect, useState } from 'react'
import { getActiveAlerts } from '../api/alerts'
import { ApiError } from '../api/client'
import type { ApiAlert } from '../types/alert'

export type ActiveAlertsStatus = 'loading' | 'error' | 'ready'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; alerts: ApiAlert[] }

/** Alerts a MET administrator has approved for the public, newest first. */
export function useActiveAlerts() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })

    getActiveAlerts(controller.signal)
      .then((alerts) => setState({ status: 'ready', alerts }))
      .catch((caughtError: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          message:
            caughtError instanceof ApiError
              ? caughtError.message
              : 'Unable to load active alerts. Please try again.',
        })
      })

    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  return {
    status: state.status,
    error: state.status === 'error' ? state.message : null,
    alerts: state.status === 'ready' ? state.alerts : [],
    retry,
  }
}

export type ActiveAlertsState = ReturnType<typeof useActiveAlerts>
