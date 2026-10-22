import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export type ResourceState<T> =
  | { status: 'loading'; data: T | null }
  | { status: 'error'; message: string; data: T | null }
  | { status: 'ready'; data: T }

/** Single authenticated fetch with abort-on-change and manual retry; keeps stale data while reloading. */
export function useApiResource<T>(load: ((signal: AbortSignal) => Promise<T>) | null, deps: unknown[]) {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading', data: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!load) return
    const controller = new AbortController()
    setState((previous) => ({ status: 'loading', data: previous.data }))
    load(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ status: 'ready', data }) })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        const message = caught instanceof ApiError || caught instanceof Error ? caught.message : 'Unable to load analytics.'
        setState((previous) => ({ status: 'error', message, data: previous.data }))
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, ...deps])
  const retry = useCallback(() => setAttempt((value) => value + 1), [])
  return { ...state, retry }
}
