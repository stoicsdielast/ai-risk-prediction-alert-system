import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../api/client'
import { getSavedLocations } from '../api/notifications'
import { useAuth } from '../auth/useAuth'
import { usePublicAlerts } from './PublicAlertContext'
import { isPublicAlert } from './validateAlert'
import type { PublicAlert } from '../types/alert'

const STORAGE_WARNING = 'Notification history cannot be saved in this browser. Read status and duplicate protection will last until you leave this page.'
const HISTORY_LIMIT = 500
export const inAppAlertKey = (alert: PublicAlert) => `${alert.id}:${alert.approved_at}:${alert.severity}`
export const inAppStorageKey = (scope: string) => `fiji-in-app-alerts-v1:${API_BASE_URL}:${scope}`

function activeAlerts(rows: PublicAlert[]) {
  return rows.filter(alert => isPublicAlert(alert)
    && ['HIGH', 'VERY_HIGH'].includes(alert.severity)
    && (!alert.expires_at || Date.parse(alert.expires_at) > Date.now()))
    .sort((a, b) => Date.parse(b.approved_at!) - Date.parse(a.approved_at!) || b.id - a.id)
}

function readHistory(key: string) {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? '{"read":[],"seen":[]}')
    // Preserve read markers from the first local implementation.
    const read: unknown = Array.isArray(value) ? value : value?.read
    const seen: unknown = Array.isArray(value) ? [] : value?.seen
    if (![read, seen].every(list => Array.isArray(list) && list.every(item => typeof item === 'string'))) throw new Error('Invalid history')
    return { read: new Set((read as string[]).slice(-HISTORY_LIMIT)), seen: new Set((seen as string[]).slice(-HISTORY_LIMIT)), warning: null }
  } catch {
    return { read: new Set<string>(), seen: new Set<string>(), warning: STORAGE_WARNING }
  }
}

function saveHistory(key: string, read: Set<string>, seen: Set<string>) {
  try {
    const saved = readHistory(key)
    const mergedRead = new Set([...saved.read, ...read])
    const mergedSeen = new Set([...saved.seen, ...seen])
    localStorage.setItem(key, JSON.stringify({ read: [...mergedRead].slice(-HISTORY_LIMIT), seen: [...mergedSeen].slice(-HISTORY_LIMIT) }))
    return null
  } catch { return STORAGE_WARNING }
}

// Uses only GET subscriptions and the existing shared public poll. It never claims
// a browser delivery, writes a server receipt, or requests Notification permission.
// The caller remounts this hook when the account scope changes.
export function useInAppAlerts(scope: string) {
  const feed = usePublicAlerts()
  const { user, token } = useAuth()
  const guest = !user && !token
  const authorized = Boolean(user?.status === 'APPROVED' && token)
  const storageKey = inAppStorageKey(scope)
  const [initial] = useState(() => readHistory(storageKey))
  const [read, setRead] = useState(initial.read)
  const readRef = useRef(initial.read)
  const seen = useRef(initial.seen)
  const initialized = useRef(false)
  const [warning, setWarning] = useState<string | null>(initial.warning)
  const [announced, setAnnounced] = useState<string[]>([])
  const [subscriptions, setSubscriptions] = useState<{
    feed: PublicAlert[]; token: string; keys: Set<string>; error: string | null
  } | null>(null)

  // Until the saved-location read succeeds, authenticated banners fail closed.
  useEffect(() => {
    if (!authorized || !token || !feed.data || feed.error || feed.refreshing) return
    const controller = new AbortController()
    const snapshot = feed.data
    void getSavedLocations(token, controller.signal).then(rows => {
      if (controller.signal.aborted) return
      if (!Array.isArray(rows) || !rows.every(row => Number.isSafeInteger(row.id) && typeof row.is_active === 'boolean')) throw new Error('Invalid saved locations')
      const ids = new Set(rows.filter(row => row.is_active).map(row => row.id))
      setSubscriptions({ feed: snapshot, token, keys: new Set(activeAlerts(snapshot).filter(alert => ids.has(alert.location_id)).map(inAppAlertKey)), error: null })
    }).catch(() => {
      if (!controller.signal.aborted) setSubscriptions({ feed: snapshot, token, keys: new Set(), error: 'Saved locations are unavailable. In-app notifications are paused until they can be checked.' })
    })
    return () => controller.abort()
  }, [authorized, token, feed.data, feed.error, feed.refreshing])

  useEffect(() => {
    if (feed.data === null || feed.error || feed.refreshing) return
    const keys = activeAlerts(feed.data).map(inAppAlertKey)
    const stored = readHistory(storageKey)
    stored.seen.forEach(key => seen.current.add(key))
    const fresh = initialized.current ? keys.filter(key => !seen.current.has(key)) : []
    setAnnounced(previous => [...new Set([...fresh, ...previous.filter(key => keys.includes(key))])].slice(0, 3))
    // Remember unselected locations too: saving an old location must not
    // turn its existing alerts into new notifications.
    keys.forEach(key => seen.current.add(key))
    initialized.current = true
    setWarning(saveHistory(storageKey, readRef.current, seen.current))
  }, [feed.data, feed.error, feed.refreshing, storageKey])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== storageKey) return
      const saved = readHistory(storageKey)
      saved.seen.forEach(key => seen.current.add(key))
      readRef.current = new Set([...readRef.current, ...saved.read])
      setRead(readRef.current)
      setWarning(saved.warning)
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [storageKey])

  function markRead(items: PublicAlert[]) {
    const next = new Set(readRef.current)
    items.forEach(alert => next.add(inAppAlertKey(alert)))
    readRef.current = next
    setRead(next)
    setWarning(saveHistory(storageKey, next, seen.current))
  }

  const snapshotReady = subscriptions?.feed === feed.data && subscriptions?.token === token
  const filterLoading = authorized && !snapshotReady
  const filterError = guest ? null : !authorized ? 'Sign in with an approved account to receive saved-location notifications.' : subscriptions?.error ?? null
  // Keep previously verified notices mounted during a refresh. New identities
  // remain hidden until that snapshot's subscription check succeeds.
  const alerts = activeAlerts(feed.data ?? []).filter(alert => guest || (authorized && subscriptions?.token === token && !filterError && subscriptions.keys.has(inAppAlertKey(alert))))
  const unread = alerts.filter(alert => !read.has(inAppAlertKey(alert)))
  const notices = feed.error ? [] : unread.filter(alert => announced.includes(inAppAlertKey(alert)))
  return { alerts, unread, notices, markRead, warning, feed, guest, filterLoading, filterError }
}
