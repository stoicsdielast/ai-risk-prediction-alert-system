import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  PROTOTYPE_ALERTS,
  PROTOTYPE_LOCATIONS,
  PROTOTYPE_PREDICTIONS,
} from '../data/prototypeData'
import type { AlertRecord, AlertStatus } from '../types/prototype'
import { PrototypeDataContext } from './PrototypeDataContext'

interface PrototypeDataProviderProps {
  children: ReactNode
}

export function PrototypeDataProvider({ children }: PrototypeDataProviderProps) {
  const [alerts, setAlerts] = useState<AlertRecord[]>(PROTOTYPE_ALERTS)

  const updateAlertStatus = useCallback(
    async (alertId: string, status: AlertStatus): Promise<AlertRecord> => {
      await new Promise((resolve) => window.setTimeout(resolve, 450))

      const existingAlert = alerts.find((alert) => alert.id === alertId)
      if (!existingAlert) throw new Error('Alert not found')

      const updatedAlert = { ...existingAlert, status }
      setAlerts((currentAlerts) =>
        currentAlerts.map((alert) =>
          alert.id === alertId ? updatedAlert : alert,
        ),
      )
      return updatedAlert
    },
    [alerts],
  )

  const value = useMemo(
    () => ({
      alerts,
      locations: PROTOTYPE_LOCATIONS,
      predictions: PROTOTYPE_PREDICTIONS,
      updateAlertStatus,
      isPrototypeData: true as const,
    }),
    [alerts, updateAlertStatus],
  )

  return (
    <PrototypeDataContext.Provider value={value}>
      {children}
    </PrototypeDataContext.Provider>
  )
}
