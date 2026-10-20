import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  detail?: ReactNode
  badge?: ReactNode
}

export function StatCard({ label, value, detail, badge }: StatCardProps) {
  return (
    <article className="stat-card">
      <span className="stat-card__label">{label}</span>
      <strong className="stat-card__value">{value}</strong>
      {badge && <div className="stat-card__badge">{badge}</div>}
      {detail && <small className="stat-card__detail">{detail}</small>}
    </article>
  )
}
