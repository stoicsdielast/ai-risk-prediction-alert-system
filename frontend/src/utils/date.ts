export function formatRelativeTime(value: string): string {
  const differenceMinutes = Math.max(
    0,
    Math.round((Date.now() - new Date(value).getTime()) / 60_000),
  )

  if (differenceMinutes < 1) return 'Just now'
  if (differenceMinutes < 60) return `${differenceMinutes} min ago`

  const hours = Math.round(differenceMinutes / 60)
  return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('en-FJ', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Pacific/Fiji',
  }).format(new Date(value))
}

/**
 * A stored prediction older than this many hours is shown as stale. Aligned
 * with the 24-hour horizon of the V1 research model; the client computes this
 * from `predicted_at` so no backend contract change is needed. Unparseable
 * timestamps count as stale (freshness cannot be confirmed).
 */
export const PREDICTION_STALE_AFTER_HOURS = 24

export function isStaleTimestamp(
  value: string,
  afterHours: number = PREDICTION_STALE_AFTER_HOURS,
  now: number = Date.now(),
): boolean {
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) return true
  return now - timestamp > afterHours * 3_600_000
}
