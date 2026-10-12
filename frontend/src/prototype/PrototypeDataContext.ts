import { createContext } from 'react'
import type {
  AlertRecord,
  AlertStatus,
  PredictionRecord,
  WeatherLocation,
} from '../types/prototype'

export interface PrototypeDataContextValue {
  alerts: AlertRecord[]
  locations: WeatherLocation[]
  predictions: PredictionRecord[]
  updateAlertStatus: (alertId: string, status: AlertStatus) => Promise<AlertRecord>
  isPrototypeData: true
}

export const PrototypeDataContext =
  createContext<PrototypeDataContextValue | null>(null)
