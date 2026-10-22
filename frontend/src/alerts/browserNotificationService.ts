import { API_BASE_URL } from '../api/client'
import type { PublicAlert } from '../types/alert'
import { isPublicAlert } from './validateAlert'

export type BrowserAlertPermission = NotificationPermission | 'unsupported' | 'insecure'
export const NOTIFICATION_HISTORY_KEY = `fiji-flood-notified-alerts-v1:${API_BASE_URL}`

export function browserAlertPermission(): BrowserAlertPermission {
  if (typeof window.Notification !== 'function') return 'unsupported'
  if (window.isSecureContext === false) return 'insecure'
  return window.Notification.permission
}

export function createBrowserAlertService(openAlert: (id?: number) => void) {
  const remembered = new Set<number>()
  let initialized = false

  function readHistory(report: (message: string) => void) {
    try {
      const raw = localStorage.getItem(NOTIFICATION_HISTORY_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      if (saved.initialized === true && Array.isArray(saved.ids)) {
        initialized = true
        for (const id of saved.ids) if (Number.isSafeInteger(id) && id > 0) remembered.add(id)
      }
    } catch {
      report('Notification history is unavailable. Duplicate protection lasts until this page is closed.')
    }
  }

  function saveHistory(report: (message: string) => void) {
    try {
      localStorage.setItem(NOTIFICATION_HISTORY_KEY, JSON.stringify({ initialized, ids: [...remembered] }))
    } catch {
      report('Notification history could not be saved. Duplicate protection lasts until this page is closed.')
    }
  }

  function show(title: string, options: NotificationOptions, report: (message: string) => void, id?: number) {
    const notification = new window.Notification(title, { icon: '/fijimetlogo.svg', ...options })
    notification.onclick = () => {
      window.focus()
      openAlert(id)
      notification.close()
    }
    notification.onerror = () => report('The browser could not display a notification. Check browser and operating-system notification settings.')
    return notification
  }

  async function sync(alerts: PublicAlert[], report: (message: string) => void) {
    const process = () => {
      readHistory(report)
      const valid = alerts.filter(isPublicAlert)
      // First successful visit establishes a baseline instead of announcing a backlog.
      if (!initialized) {
        valid.forEach((alert) => remembered.add(alert.id))
        initialized = true
        saveHistory(report)
        return
      }
      for (const alert of valid) {
        if (remembered.has(alert.id)) continue
        if (browserAlertPermission() !== 'granted' || !['HIGH', 'VERY_HIGH'].includes(alert.severity)) {
          remembered.add(alert.id)
          continue
        }
        const demo = alert.is_demo === true || alert.prediction?.is_sample === true
        const confidence = alert.prediction?.confidence_percent
        const score = typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0 && confidence <= 100
          ? ` ${demo ? 'Demo' : 'Model'} score: ${Math.round(confidence)}%.` : ''
        try {
          show(demo ? 'Flood Risk Warning — DEMO' : 'Flood Risk Warning', {
            body: `${demo ? 'DEMO ONLY. ' : ''}${alert.severity.replace('_', ' ')} flood risk alert for ${alert.location.name}.${score} ${demo ? 'Simulated prediction.' : 'University decision-support prototype.'} Not an official Fiji MET warning.`,
            tag: `flood-alert-${alert.id}`,
          }, report, alert.id)
          remembered.add(alert.id)
        } catch {
          report('Unable to display browser alerts. Try a desktop browser and check notification settings.')
        }
      }
      saveHistory(report)
    }
    // Serializes simultaneous polls in tabs on the same origin where supported.
    if (navigator.locks?.request) await navigator.locks.request(NOTIFICATION_HISTORY_KEY, process)
    else process()
  }

  function test(report: (message: string) => void) {
    if (!import.meta.env.DEV || browserAlertPermission() !== 'granted') return
    try {
      show('Flood Alert Test', { body: 'TEST ONLY: Browser notifications are working.', tag: 'flood-alert-test' }, report)
    } catch {
      report('Unable to display the test notification. Try a desktop browser and check notification settings.')
    }
  }

  return { sync, test }
}
