import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as api from '../api/notifications'
import { ApiError } from '../api/client'
import { sampleAlert } from '../test/alertApiFixture'
import { deliverOutbox } from './outboxDelivery'

vi.mock('../api/notifications')
class BrowserNotification {
  static permission = 'granted'
  static requestPermission = vi.fn()
  static instances: BrowserNotification[] = []
  static fail = false
  onshow?: () => void
  onerror?: () => void
  onclick?: () => void
  close = vi.fn()
  title: string
  constructor(title: string) {
    this.title = title
    BrowserNotification.instances.push(this)
    queueMicrotask(() => BrowserNotification.fail ? this.onerror?.() : this.onshow?.())
  }
}
beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  BrowserNotification.permission = 'granted'
  BrowserNotification.fail = false
  BrowserNotification.instances = []
  vi.stubGlobal('Notification', BrowserNotification)
  vi.stubGlobal('isSecureContext', true)
  vi.mocked(api.getNotificationPreferences).mockResolvedValue({ browser_enabled: true, delivery_enabled: true })
  vi.mocked(api.getNotifications).mockResolvedValue([{ id: 1, next_attempt_at: null } as api.NotificationRecord])
  vi.mocked(api.claimNotification).mockResolvedValue({ id: 1, token: 'claim', expires_at: '', alert: sampleAlert({ status: 'APPROVED', is_demo: true }) })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
it.each(['denied', 'default'])('never requests consent or claims with %s permission', async permission => {
  BrowserNotification.permission = permission
  await deliverOutbox('token', 1, vi.fn())
  expect(api.claimNotification).not.toHaveBeenCalled()
  expect(BrowserNotification.requestPermission).not.toHaveBeenCalled()
})
it('respects both account opt-out and operator gate', async () => {
  for (const preference of [{ browser_enabled: false, delivery_enabled: true }, { browser_enabled: true, delivery_enabled: false }]) {
    vi.mocked(api.getNotificationPreferences).mockResolvedValue(preference)
    await deliverOutbox('token', 1, vi.fn())
  }
  expect(api.claimNotification).not.toHaveBeenCalled()
})
it('acknowledges display, labels demo and retries a lost receipt without redisplaying', async () => {
  vi.mocked(api.acknowledgeNotification).mockRejectedValueOnce(new Error('network'))
  await expect(deliverOutbox('token', 1, vi.fn())).rejects.toThrow('network')
  await deliverOutbox('token', 1, vi.fn())
  expect(BrowserNotification.instances).toHaveLength(1)
  expect(BrowserNotification.instances[0].title).toContain('DEMO ONLY')
  expect(api.acknowledgeNotification).toHaveBeenLastCalledWith('token', 1, 'claim', 'DELIVERED')
})
it('records browser failures then displays on retry', async () => {
  BrowserNotification.fail = true
  await deliverOutbox('token', 1, vi.fn())
  expect(api.acknowledgeNotification).toHaveBeenCalledWith('token', 1, 'claim', 'FAILED', expect.any(String))
  BrowserNotification.fail = false
  await deliverOutbox('token', 1, vi.fn())
  expect(api.acknowledgeNotification).toHaveBeenLastCalledWith('token', 1, 'claim', 'DELIVERED')
})
it('does not display when another browser owns the claim', async () => {
  vi.mocked(api.claimNotification).mockRejectedValue(new ApiError(409, 'claimed'))
  await deliverOutbox('token', 1, vi.fn())
  expect(BrowserNotification.instances).toHaveLength(0)
})
it('rechecks suppression before displaying', async () => {
  vi.mocked(api.checkNotification).mockRejectedValue(new ApiError(409, 'suppressed'))
  await deliverOutbox('token', 1, vi.fn())
  expect(BrowserNotification.instances).toHaveLength(0)
})
it('does not deliver after logout and separates receipt storage by account', async () => {
  await deliverOutbox('token', 1, vi.fn(), () => false)
  expect(api.getNotifications).not.toHaveBeenCalled()
  await deliverOutbox('token', 1, vi.fn())
  await deliverOutbox('other-token', 2, vi.fn())
  expect(BrowserNotification.instances).toHaveLength(2)
})
