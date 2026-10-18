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
