import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { getNotificationPreferences, setNotificationPreference } from '../api/notifications'
import { browserAlertPermission, createBrowserAlertService } from './browserNotificationService'
import { deliverOutbox } from './outboxDelivery'

export function useBrowserAlerts() {
  const { token, user } = useAuth()
  const navigate = useNavigate()
  const [permission, setPermission] = useState(browserAlertPermission)
  const [enabled, setEnabled] = useState(false)
  const [deliveryEnabled, setDeliveryEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const update = () => setPermission(browserAlertPermission())
    window.addEventListener('focus', update)
    return () => window.removeEventListener('focus', update)
  }, [])
  useEffect(() => {
    if (!token || !user) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const prefs = await getNotificationPreferences(token!)
        if (!active) return
        setEnabled(prefs.browser_enabled)
        setDeliveryEnabled(prefs.delivery_enabled)
        setPermission(browserAlertPermission())
        await deliverOutbox(token!, user!.id, id => navigate(`/alerts#alert-${id}`), () => active)
        if (active) setError(null)
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : 'Unable to load notifications')
      } finally {
        if (active) timer = setTimeout(() => void poll(), 30_000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [token, user, navigate])

  async function enable() {
    if (!token || busy) return
    setBusy(true)
    setError(null)
    try {
      const current = browserAlertPermission()
      const granted = current === 'default' ? await Notification.requestPermission() : current
      setPermission(granted)
      if (granted === 'granted') {
        const prefs = await setNotificationPreference(token, true)
        setEnabled(prefs.browser_enabled)
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to save preference') }
    finally { setBusy(false) }
  }
  async function disable() {
    if (!token || busy) return
    setBusy(true)
    try { await setNotificationPreference(token, false); setEnabled(false); setError(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to save preference') }
    finally { setBusy(false) }
  }
  return { permission, enabled, deliveryEnabled, busy, error, enable, disable,
    test: () => createBrowserAlertService(() => navigate('/alerts')).test(setError) }
}
