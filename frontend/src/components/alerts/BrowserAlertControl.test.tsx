import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/notifications'
import { deliverOutbox } from '../../alerts/outboxDelivery'
import { BrowserAlertControl } from './BrowserAlertControl'

vi.mock('../../api/notifications')
vi.mock('../../alerts/outboxDelivery')
vi.mock('../../auth/useAuth', () => {
  const user = { id: 1 }
  return { useAuth: () => ({ user, token: 'test-token' }) }
})
class TestNotification {
  static permission: NotificationPermission = 'default'
  static requestPermission = vi.fn(async (): Promise<NotificationPermission> => {
    TestNotification.permission = 'granted'
    return 'granted'
  })
}
beforeEach(() => {
  vi.clearAllMocks()
  TestNotification.permission = 'default'
  vi.stubGlobal('Notification', TestNotification)
  vi.stubGlobal('isSecureContext', true)
  vi.mocked(api.getNotificationPreferences).mockResolvedValue({ browser_enabled: false, delivery_enabled: false })
  vi.mocked(api.setNotificationPreference).mockResolvedValue({ browser_enabled: true, delivery_enabled: false })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })
const renderControls = () => render(<MemoryRouter><BrowserAlertControl /></MemoryRouter>)
it('requests permission only on click and persists opt-in', async () => {
  renderControls()
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
  await userEvent.click(screen.getByText('Enable Browser Alerts'))
  expect(api.setNotificationPreference).toHaveBeenCalledWith('test-token', true)
  expect(await screen.findByText(/opted in for saved locations/)).toBeInTheDocument()
  expect(screen.getByText(/disabled by the operator/)).toBeInTheDocument()
})
it('persists opt-out independently of browser permission', async () => {
  TestNotification.permission = 'granted'
  vi.mocked(api.getNotificationPreferences).mockResolvedValue({ browser_enabled: true, delivery_enabled: false })
  renderControls()
  await userEvent.click(await screen.findByText('Disable Browser Alerts'))
  expect(api.setNotificationPreference).toHaveBeenCalledWith('test-token', false)
  expect(await screen.findByText(/account notifications disabled/)).toBeInTheDocument()
})
it('explains denied consent without prompting or enabling the account', async () => {
  TestNotification.permission = 'denied'
  renderControls()
  expect(screen.getByText(/permission was denied/)).toBeInTheDocument()
  await waitFor(() => expect(api.getNotificationPreferences).toHaveBeenCalled())
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
  expect(api.setNotificationPreference).not.toHaveBeenCalled()
})
it('reports permission rejection and permits another click', async () => {
  TestNotification.requestPermission.mockRejectedValueOnce(new Error('blocked'))
  renderControls()
  await userEvent.click(screen.getByText('Enable Browser Alerts'))
  expect(await screen.findByRole('alert')).toHaveTextContent('blocked')
  expect(screen.getByText('Enable Browser Alerts')).toBeEnabled()
})
it('keeps dashboard usage available on unsupported browsers', async () => {
  vi.stubGlobal('Notification', undefined)
  renderControls()
  expect(screen.getByText(/does not support desktop notifications/)).toBeInTheDocument()
  await waitFor(() => expect(api.getNotificationPreferences).toHaveBeenCalled())
})
it('recovers from API failure on polling and stops after unmount', async () => {
  vi.useFakeTimers()
  vi.mocked(api.getNotificationPreferences).mockRejectedValueOnce(new Error('Unavailable'))
  const view = renderControls()
  await act(async () => {})
  expect(screen.getByRole('alert')).toHaveTextContent('Unavailable')
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(deliverOutbox).toHaveBeenCalledTimes(1)
  view.unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
  expect(deliverOutbox).toHaveBeenCalledTimes(1)
})
it('observes permission changes without silently enabling account preference', async () => {
  vi.stubEnv('DEV', false)
  renderControls()
  TestNotification.permission = 'granted'
  fireEvent.focus(window)
  expect(screen.getByText(/account notifications disabled/)).toBeInTheDocument()
  expect(screen.queryByText('Test Browser Notification')).not.toBeInTheDocument()
  await waitFor(() => expect(api.getNotificationPreferences).toHaveBeenCalled())
})
