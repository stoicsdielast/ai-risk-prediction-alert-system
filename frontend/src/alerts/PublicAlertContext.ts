import { createContext, useContext } from 'react'
import type { usePublicAlertPolling } from './useAlertFeed'

export const PublicAlertContext = createContext<ReturnType<typeof usePublicAlertPolling> | null>(null)

export function usePublicAlerts() {
  const feed = useContext(PublicAlertContext)
  if (!feed) throw new Error('Public alerts require the workspace alert provider')
  return feed
}
