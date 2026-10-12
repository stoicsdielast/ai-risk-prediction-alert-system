import type { AlertStatus, RiskLevel } from '../../types/prototype'

type PillValue = AlertStatus | RiskLevel | 'AI_PREDICTION' | 'OFFICIAL_WARNING'

interface DataPillProps {
  value: PillValue
  label?: string
  compact?: boolean
}

const labels: Record<PillValue, string> = {
  LOW: 'Low',
  MODERATE: 'Moderate',
  HIGH: 'High',
  VERY_HIGH: 'Very high',
  PENDING: 'Pending',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  SUPPRESSED: 'Suppressed',
  AI_PREDICTION: 'AI prediction',
  OFFICIAL_WARNING: 'Official warning',
}

export function DataPill({ value, label, compact = false }: DataPillProps) {
  return (
    <span
      className={`data-pill data-pill--${value.toLowerCase()}${
        compact ? ' data-pill--compact' : ''
      }`}
    >
      <span className="data-pill__dot" aria-hidden="true" />
      {label || labels[value]}
    </span>
  )
}

export function RiskPill({ risk, compact }: { risk: RiskLevel; compact?: boolean }) {
  return <DataPill value={risk} compact={compact} />
}

export function StatusPill({ status }: { status: AlertStatus }) {
  return <DataPill value={status} />
}
