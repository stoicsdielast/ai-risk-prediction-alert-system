import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminAlerts, getPublicAlerts } from '../api/alerts'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'

export const ALERT_REFRESH_MS = 30_000
export { usePublicAlerts } from './PublicAlertContext'

export function usePollingResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const refresh = useCallback(() => setAttempt((value) => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function fetchData() {
      setRefreshing(true)
      try {
        const result = await load(controller.signal)
        if (controller.signal.aborted) return
        setData(result)
        setError(null)
        setUpdatedAt(new Date().toISOString())
      } catch (caught) {
        if (controller.signal.aborted) return
        setError(
          caught instanceof Error ? caught.message : 'Unable to load alerts. Please try again.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setRefreshing(false)
          timer = setTimeout(() => void fetchData(), ALERT_REFRESH_MS)
        }
      }
    }
    void fetchData()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [load, attempt])

  return { data, setData, error, refreshing, updatedAt, refresh }
}

export function useAdminRequest() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return useCallback(
    async <T>(request: () => Promise<T>): Promise<T> => {
      try {
        return await request()
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          logout(
            error.status === 401
              ? 'Your session expired. Please sign in again.'
              : 'Your account no longer has access to alert management. Please sign in again.',
          )
          navigate('/login', { replace: true })
        }
        throw error
      }
    },
    [logout, navigate],
  )
}

export function useAdminAlerts() {
  const { token, user } = useAuth()
  const request = useAdminRequest()
  const isAdmin = user?.role === 'MET_ADMIN'
  const load = useCallback(
    (signal: AbortSignal) => {
      if (!token || !isAdmin) return Promise.resolve([])
      return request(() => getAdminAlerts(token, signal))
    },
    [token, isAdmin, request],
  )
  return usePollingResource(load)
}

export function usePublicAlertPolling() {
  return usePollingResource(getPublicAlerts)
}
