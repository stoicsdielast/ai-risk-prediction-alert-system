import type { ReactNode } from 'react'
import { PublicAlertContext } from './PublicAlertContext'
import { usePublicAlertPolling } from './useAlertFeed'

export function PublicAlertProvider({ children }: { children: ReactNode }) {
  const feed = usePublicAlertPolling()
  return <PublicAlertContext.Provider value={feed}>{children}</PublicAlertContext.Provider>
}
