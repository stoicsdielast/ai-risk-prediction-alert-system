import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import {
  getPriorityLocations,
  removePriorityLocation,
  savePriorityLocation,
} from '../api/priorityLocations'
import { useAuth } from '../auth/useAuth'
import type { ApiLocation } from '../types/location'

/** `signed-out` means priority areas are unavailable: there is no account to save them to. */
export type PriorityLocationsStatus = 'signed-out' | 'loading' | 'error' | 'ready'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; locations: ApiLocation[] }

function messageFrom(caughtError: unknown, fallback: string) {
  return caughtError instanceof ApiError ? caughtError.message : fallback
}

function byName(first: ApiLocation, second: ApiLocation) {
  return first.name.localeCompare(second.name)
}

/** The signed-in user's saved priority areas, with save and remove actions. */
export function usePriorityLocations() {
  const { user, token } = useAuth()
  const sessionToken = user ? token : null
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [pendingSlugs, setPendingSlugs] = useState<ReadonlySet<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionToken) return

    const controller = new AbortController()
    setState({ status: 'loading' })

    getPriorityLocations(sessionToken, controller.signal)
      .then((locations) => setState({ status: 'ready', locations }))
      .catch((caughtError: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          message: messageFrom(
            caughtError,
            'Unable to load your priority areas. Please try again.',
          ),
        })
      })

    return () => controller.abort()
  }, [attempt, sessionToken])

  // Ignore whatever was loaded for a previous session once signed out.
  const locations = useMemo(
    () => (sessionToken && state.status === 'ready' ? state.locations : []),
    [sessionToken, state],
  )
  const savedSlugs = useMemo(
    () => new Set(locations.map((location) => location.slug)),
    [locations],
  )

  const setPending = (slug: string, isPending: boolean) =>
    setPendingSlugs((current) => {
      const next = new Set(current)
      if (isPending) next.add(slug)
      else next.delete(slug)
      return next
    })

  const toggle = useCallback(
    async (slug: string) => {
      if (!sessionToken || state.status !== 'ready' || pendingSlugs.has(slug)) return

      const isSaved = savedSlugs.has(slug)
      setActionError(null)
      setPending(slug, true)

      try {
        let saved: ApiLocation | null = null
        if (isSaved) await removePriorityLocation(sessionToken, slug)
        else saved = await savePriorityLocation(sessionToken, slug)

        setState((current) => {
          if (current.status !== 'ready') return current
          const others = current.locations.filter((location) => location.slug !== slug)
          return {
            status: 'ready',
            locations: saved ? [...others, saved].sort(byName) : others,
          }
        })
      } catch (caughtError) {
        setActionError(
          messageFrom(
            caughtError,
            isSaved
              ? 'Unable to remove this priority area. Please try again.'
              : 'Unable to save this priority area. Please try again.',
          ),
        )
      } finally {
        setPending(slug, false)
      }
    },
    [pendingSlugs, savedSlugs, sessionToken, state.status],
  )

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  return {
    status: (sessionToken ? state.status : 'signed-out') as PriorityLocationsStatus,
    error: sessionToken && state.status === 'error' ? state.message : null,
    actionError,
    locations,
    savedSlugs,
    pendingSlugs,
    toggle,
    retry,
  }
}

export type PriorityLocationsState = ReturnType<typeof usePriorityLocations>
