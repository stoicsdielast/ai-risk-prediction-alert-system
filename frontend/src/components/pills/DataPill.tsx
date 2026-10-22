import type { AlertStatus, RiskLevel } from '../../types/prototype'

export type PillValue =
  | AlertStatus
  | RiskLevel
  | 'AI_PREDICTION'
  | 'NO_ALERTS'
  | 'NO_PREDICTION'
  | 'SAMPLE_RISK'
  | 'STALE'
  | 'SYNTHETIC_DATA'
  | 'SYNTHETIC_PREDICTION'

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
  NO_ALERTS: 'No approved alert',
  NO_PREDICTION: 'No prediction',
  SAMPLE_RISK: 'Sample risk',
  STALE: 'Stale',
  SYNTHETIC_DATA: 'Synthetic data',
  SYNTHETIC_PREDICTION: 'Synthetic research',
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

export function RiskPill({
  risk,
  compact,
}: {
  risk: RiskLevel | null
  compact?: boolean
}) {
  return <DataPill value={risk ?? 'NO_PREDICTION'} compact={compact} />
}

export function StatusPill({ status }: { status: AlertStatus }) {
  return <DataPill value={status} />
}
