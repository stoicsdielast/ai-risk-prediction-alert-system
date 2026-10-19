import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sampleAlert } from '../test/alertApiFixture'
import { browserAlertPermission, createBrowserAlertService, NOTIFICATION_HISTORY_KEY } from './browserNotificationService'

class TestNotification {
  static permission: NotificationPermission = 'granted'
  static requestPermission = vi.fn()
  static instances: TestNotification[] = []
  onclick: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  title: string
  options: NotificationOptions
  constructor(title: string, options: NotificationOptions) {
    this.title = title
    this.options = options
    TestNotification.instances.push(this)
  }
}
const approved = (id: number, severity: 'HIGH' | 'VERY_HIGH' | 'LOW' | 'MODERATE' = 'HIGH') => sampleAlert({ id, severity, status: 'APPROVED' })

beforeEach(() => {
  localStorage.clear()
  TestNotification.instances = []
  TestNotification.permission = 'granted'
  TestNotification.requestPermission.mockReset()
  vi.stubGlobal('Notification', TestNotification)
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('baselines existing alerts then notifies new approved HIGH and VERY_HIGH only once across polling and reloads', async () => {
  const service = createBrowserAlertService(vi.fn())
  const report = vi.fn()
  await service.sync([approved(1)], report)
  expect(TestNotification.instances).toHaveLength(0)
  const next = [approved(1), approved(2), approved(3, 'VERY_HIGH')]
  await service.sync(next, report)
  expect(TestNotification.instances).toHaveLength(2)
  expect(TestNotification.instances[0].options.tag).toBe('flood-alert-2')
  expect(TestNotification.instances[1].options.body).toContain('VERY HIGH')
  await service.sync(next, report)
  await createBrowserAlertService(vi.fn()).sync(next, report)
  expect(TestNotification.instances).toHaveLength(2)
  expect(JSON.parse(localStorage.getItem(NOTIFICATION_HISTORY_KEY)!).ids).toEqual([1, 2, 3])
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
})

it('does not notify pending, rejected, suppressed or lower-severity alerts; a later approval does notify', async () => {
  const service = createBrowserAlertService(vi.fn())
  await service.sync([], vi.fn())
  await service.sync([
    sampleAlert({ id: 2 }), sampleAlert({ id: 3, status: 'REJECTED' }),
    sampleAlert({ id: 4, status: 'SUPPRESSED' }), approved(5, 'LOW'), approved(6, 'MODERATE'),
  ], vi.fn())
  expect(TestNotification.instances).toHaveLength(0)
  await service.sync([approved(2)], vi.fn())
  expect(TestNotification.instances).toHaveLength(1)
})

it.each(['default', 'denied'] as const)('does not prompt or notify with %s permission', async (permission) => {
  TestNotification.permission = permission
  const service = createBrowserAlertService(vi.fn())
  await service.sync([], vi.fn())
  await service.sync([approved(2)], vi.fn())
  expect(TestNotification.instances).toHaveLength(0)
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
})

it('labels simulated output and handles notification clicks', async () => {
  const open = vi.fn()
  vi.spyOn(window, 'focus').mockImplementation(() => {})
  const service = createBrowserAlertService(open)
  await service.sync([], vi.fn())
  await service.sync([sampleAlert({ ...approved(2), is_demo: true })], vi.fn())
  const notification = TestNotification.instances[0]
  expect(notification.title).toContain('DEMO')
  expect(notification.options.body).toContain('Simulated prediction')
  expect(notification.options.icon).toBe('/fijimetlogo.svg')
  notification.onclick!()
  expect(window.focus).toHaveBeenCalled()
  expect(open).toHaveBeenCalledWith(2)
  expect(notification.close).toHaveBeenCalled()
})

it('continues without crashing when storage is blocked and retains in-memory deduplication', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  const report = vi.fn()
  const service = createBrowserAlertService(vi.fn())
  await service.sync([], report)
  await service.sync([approved(2)], report)
  await service.sync([approved(2)], report)
  expect(TestNotification.instances).toHaveLength(1)
  expect(report).toHaveBeenCalledWith(expect.stringContaining('Duplicate protection'))
})

it('reports constructor failure and retries successfully without consuming the alert ID', async () => {
  const service = createBrowserAlertService(vi.fn())
  const report = vi.fn()
  await service.sync([], report)
  const failing = vi.fn(function () { throw new Error('unsupported platform') })
  Object.assign(failing, { permission: 'granted' })
  vi.stubGlobal('Notification', failing)
  await service.sync([approved(2)], report)
  expect(report).toHaveBeenCalledWith(expect.stringContaining('Unable to display'))
  vi.stubGlobal('Notification', TestNotification)
  await service.sync([approved(2)], report)
  expect(TestNotification.instances).toHaveLength(1)
  TestNotification.instances[0].onerror!()
  expect(report).toHaveBeenCalledWith(expect.stringContaining('operating-system'))
})

it('coordinates two tab services using a shared lock and history', async () => {
  const request = vi.fn(async (_name: string, callback: () => void) => callback())
  vi.stubGlobal('navigator', { locks: { request } })
  const first = createBrowserAlertService(vi.fn())
  const second = createBrowserAlertService(vi.fn())
  await first.sync([], vi.fn())
  await Promise.all([first.sync([approved(2)], vi.fn()), second.sync([approved(2)], vi.fn())])
  expect(request).toHaveBeenCalled()
  expect(TestNotification.instances).toHaveLength(1)
})

describe('platform and test controls', () => {
  it('detects unsupported and insecure contexts', () => {
    vi.stubGlobal('isSecureContext', false)
    expect(browserAlertPermission()).toBe('insecure')
    vi.stubGlobal('Notification', undefined)
    expect(browserAlertPermission()).toBe('unsupported')
  })
  it('test sends a labelled notification in development, and nothing in production', () => {
    const service = createBrowserAlertService(vi.fn())
    service.test(vi.fn())
    expect(TestNotification.instances[0].title).toBe('Flood Alert Test')
    vi.stubEnv('DEV', false)
    service.test(vi.fn())
    expect(TestNotification.instances).toHaveLength(1)
  })
})
