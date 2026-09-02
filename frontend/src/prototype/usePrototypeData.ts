import { useContext } from 'react'
import { PrototypeDataContext } from './PrototypeDataContext'

export function usePrototypeData() {
  const context = useContext(PrototypeDataContext)
  if (!context) {
    throw new Error('usePrototypeData must be used inside PrototypeDataProvider')
  }
  return context
}
