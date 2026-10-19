import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePublicAlerts } from './PublicAlertContext'
import { browserAlertPermission, createBrowserAlertService } from './browserNotificationService'

export function useBrowserAlerts() {
  const feed = usePublicAlerts()
  const navigate = useNavigate()
  const [permission, setPermission] = useState(browserAlertPermission)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const service = useRef<ReturnType<typeof createBrowserAlertService> | null>(null)
  if (!service.current) service.current = createBrowserAlertService((id) => navigate(id ? `/alerts#alert-${id}` : '/alerts'))

  useEffect(() => {
    const update = () => setPermission(browserAlertPermission())
    window.addEventListener('focus', update)
    document.addEventListener('visibilitychange', update)
    return () => {
      window.removeEventListener('focus', update)
      document.removeEventListener('visibilitychange', update)
    }
  }, [])

  useEffect(() => {
    if (!feed.data || feed.error || feed.refreshing) return
    let active = true
    void service.current!.sync(feed.data, (message) => { if (active) setError(message) })
      .catch(() => { if (active) setError('Browser alert delivery failed. The website alert feed remains available.') })
    return () => { active = false }
  }, [feed.data, feed.error, feed.refreshing, permission])

  async function enable() {
    if (busy) return
    setError(null)
    const current = browserAlertPermission()
    if (current !== 'default') { setPermission(current); return }
    setBusy(true)
    try {
      // Invoked only from the permission button's click handler.
      setPermission(await window.Notification.requestPermission())
    } catch {
      setError('The browser could not request permission. Open this site directly in a desktop browser using localhost or HTTPS.')
    } finally {
      setBusy(false)
    }
  }

  return { permission, busy, error, enable, test: () => { setError(null); service.current!.test(setError) } }
}
