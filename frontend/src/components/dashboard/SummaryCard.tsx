import type { ReactNode } from 'react'

interface SummaryCardProps {
  label: string
  value: number | string
  detail: string
  icon: ReactNode
  tone?: 'indigo' | 'teal' | 'amber' | 'red'
}

export function SummaryCard({
  label,
  value,
  detail,
  icon,
  tone = 'indigo',
}: SummaryCardProps) {
  return (
    <article className="metric-card">
      <div className={`metric-card__icon metric-card__icon--${tone}`}>
        {icon}
      </div>
      <span className="metric-card__label">{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}
