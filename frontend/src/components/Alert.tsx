import type { ReactNode } from 'react'

interface AlertProps {
  children: ReactNode
  tone?: 'error' | 'success' | 'info'
}

export function Alert({ children, tone = 'info' }: AlertProps) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="alert__dot" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}
