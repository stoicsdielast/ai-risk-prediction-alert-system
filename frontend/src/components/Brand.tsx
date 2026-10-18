import { Link } from 'react-router-dom'

interface BrandProps {
  inverse?: boolean
  compact?: boolean
}

export function BrandMark() {
  return (
    <img
      aria-hidden="true"
      className="brand-mark"
      src="/fijimetlogo.svg"
      alt=""
    />
  )
}

export function Brand({ inverse = false, compact = false }: BrandProps) {
  return (
    <Link
      className={`brand${inverse ? ' brand--inverse' : ''}`}
      to="/"
      aria-label="Fiji FloodWatch home"
    >
      <BrandMark />
      <span className="brand__copy">
        <strong>FloodWatch Fiji</strong>
        {!compact && <small>Fiji Meteorological Service</small>}
      </span>
    </Link>
  )
}
