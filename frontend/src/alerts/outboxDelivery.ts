import { API_BASE_URL, ApiError } from '../api/client'
import { acknowledgeNotification, checkNotification, claimNotification, getNotificationPreferences, getNotifications } from '../api/notifications'
import { browserAlertPermission } from './browserNotificationService'

// Database claims serialize devices; the local receipt bridges a lost server ACK.
// No service worker: the page must stay open and the browser must permit display.
export async function deliverOutbox(token: string, userId: number, openAlert: (id: number) => void,
  active: () => boolean = () => true) {
  if (!active() || browserAlertPermission() !== 'granted') return
  const preference = await getNotificationPreferences(token)
  if (!preference.browser_enabled || !preference.delivery_enabled || !active()) return
  const rows = await getNotifications(token, true)
  for (const row of rows) {
    if (!active() || browserAlertPermission() !== 'granted') return
    if (row.next_attempt_at && Date.parse(row.next_attempt_at) > Date.now()) continue
    let claim
    try { claim = await claimNotification(token, row.id) }
    catch (error) { if (error instanceof ApiError && error.status === 409) continue; throw error }
    if (!active()) return
    const key = `fiji-outbox:${API_BASE_URL}:${userId}:${row.id}`
    // If storage is unavailable, fail before displaying rather than lose dedup protection.
    let shown = false
    try {
      shown = localStorage.getItem(key) === 'shown'
      if (!shown) {
        await checkNotification(token, row.id, claim.token)
        if (!active() || browserAlertPermission() !== 'granted') return
        localStorage.setItem(key, 'ready')
        await new Promise<void>((resolve, reject) => {
          const demo = claim.alert.is_demo || claim.alert.prediction?.is_sample
          const notification = new Notification(`${demo ? 'DEMO ONLY — ' : ''}FloodWatch: ${claim.alert.location.name}`, {
            body: claim.alert.message, tag: key, icon: '/fijimetlogo.svg',
          })
          const timer = setTimeout(() => { notification.close(); reject(new Error('Browser display timed out')) }, 10_000)
          notification.onshow = () => { clearTimeout(timer); resolve() }
          notification.onerror = () => { clearTimeout(timer); reject(new Error('Browser could not display notification')) }
          notification.onclick = () => { window.focus(); openAlert(claim.alert.id); notification.close() }
        })
        shown = true
        localStorage.setItem(key, 'shown')
      }
    } catch (error) {
      // Never mark a successfully shown message failed just because receipt storage failed.
      if (!shown) {
        await acknowledgeNotification(token, row.id, claim.token, 'FAILED', error instanceof Error ? error.message : 'Browser failure')
        continue
      }
    }
    await acknowledgeNotification(token, row.id, claim.token, 'DELIVERED')
  }
}
