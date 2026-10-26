import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { usePublicAlerts } from '../../alerts/PublicAlertContext'
import { inAppStorageKey } from '../../alerts/useInAppAlerts'
import { useAuth } from '../../auth/useAuth'
import { getSavedLocations } from '../../api/notifications'
import { sampleAdmin, sampleAlert } from '../../test/alertApiFixture'
import { InAppAlerts } from './InAppAlerts'

vi.mock('../../alerts/PublicAlertContext', () => ({ usePublicAlerts: vi.fn() }))
vi.mock('../../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/notifications', () => ({ getSavedLocations: vi.fn() }))

let feed: ReturnType<typeof usePublicAlerts>
let requestPermission: ReturnType<typeof vi.fn>
let fetchMock: ReturnType<typeof vi.fn>
const approved = (id = 41) => sampleAlert({ id, status: 'APPROVED' })

beforeEach(() => {
  localStorage.clear()
  feed = { data: [approved()], setData: vi.fn(), error: null, refreshing: false, updatedAt: null, refresh: vi.fn() }
  vi.mocked(usePublicAlerts).mockImplementation(() => feed)
  vi.mocked(useAuth).mockReturnValue({ user: null, token: null, isLoading: false,
    sessionError: null, login: vi.fn(), logout: vi.fn(), retrySession: vi.fn() })
  requestPermission = vi.fn()
  vi.stubGlobal('Notification', { permission: 'denied', requestPermission })
  // Any unexpected network call fails locally; no backend is contacted.
  fetchMock = vi.fn(() => { throw new Error('Unexpected network request') })
  vi.stubGlobal('fetch', fetchMock)
  vi.mocked(getSavedLocations).mockReset().mockResolvedValue([{ id: 1, name: 'Suva', is_active: true }])
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

function View() {
  return <MemoryRouter><InAppAlerts /><Routes><Route path="/alerts" element={<><h1>Public alert details</h1><article id="alert-41">Selected alert record</article></>} /><Route path="*" element={null} /></Routes></MemoryRouter>
}

function inbox() {
  const details = screen.getByText('In-app alerts').closest('details')!
  fireEvent.click(details.querySelector('summary')!)
  details.open = true
  return within(details)
}

function signIn(id = 7) {
  vi.mocked(useAuth).mockReturnValue({ user: { ...sampleAdmin, id, role: 'COMMUNITY' }, token: 'fixture-only',
    isLoading: false, sessionError: null, login: vi.fn(), logout: vi.fn(), retrySession: vi.fn() })
}

async function locationsReady() {
  await waitFor(() => expect(screen.queryByText('Checking saved locations…')).not.toBeInTheDocument())
}

it('works without browser permission or API writes and does not announce the initial backlog', () => {
  vi.stubGlobal('Notification', undefined)
  render(<View />)
  expect(screen.getByText('1 unread')).toBeInTheDocument()
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  expect(inbox().getByText(/all monitored locations/)).toBeInTheDocument()
  expect(requestPermission).not.toHaveBeenCalled()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('announces a new approved alert once, marks a dismissed notice read, and retains the inbox record', async () => {
  const view = render(<View />)
  feed = { ...feed, data: [approved(42), approved()] }
  view.rerender(<View />)
  const notice = screen.getByLabelText('New alert for Suva')
  expect(screen.getByText('2 unread')).toBeInTheDocument()
  await userEvent.click(within(notice).getByRole('button', { name: 'Dismiss alert for Suva' }))
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  expect(screen.getByText('1 unread')).toBeInTheDocument()
  expect(inbox().getAllByRole('link', { name: 'View alert for Suva' })).toHaveLength(2)
  feed = { ...feed, data: [approved(42), approved()] }
  view.rerender(<View />)
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('persists read state on remount and keeps guest and different account histories separate', async () => {
  signIn()
  let view = render(<View />)
  await screen.findByText('1 unread')
  await userEvent.click(inbox().getByRole('button', { name: 'Mark all as read' }))
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  view.unmount()
  view = render(<View />)
  await locationsReady()
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  vi.mocked(useAuth).mockReturnValue({ ...useAuth(), user: { ...sampleAdmin, id: 99 } })
  view.rerender(<View />)
  expect(await screen.findByText('1 unread')).toBeInTheDocument()
  vi.mocked(useAuth).mockReturnValue({ ...useAuth(), user: null, token: null })
  view.rerender(<View />)
  expect(screen.getByText('1 unread')).toBeInTheDocument()
})

it('filters expired, invalid, pending and lower severity records and removes withdrawn alerts', () => {
  feed.data = [approved(), sampleAlert({ status: 'PENDING' }), sampleAlert({ id: 42, status: 'APPROVED', severity: 'LOW' }),
    sampleAlert({ id: 43, status: 'APPROVED', severity: 'MODERATE' }),
    sampleAlert({ id: 44, status: 'APPROVED', expires_at: '2000-01-01T00:00:00Z' }),
    sampleAlert({ id: 45, status: 'APPROVED', expires_at: 'invalid' }),
    sampleAlert({ id: 46, status: 'APPROVED', message: '' })]
  const view = render(<View />)
  expect(screen.getByText('1 unread')).toBeInTheDocument()
  feed = { ...feed, data: [] }
  view.rerender(<View />)
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  expect(inbox().getByText('No active high-risk community alerts.')).toBeInTheDocument()
})

it('does not establish a baseline from loading or failed data, and warns on later feed failure', () => {
  feed = { ...feed, data: null, refreshing: true }
  const view = render(<View />)
  expect(inbox().getByRole('status')).toHaveTextContent('Loading community alerts')
  feed = { ...feed, data: [approved()], refreshing: false }
  view.rerender(<View />)
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  feed = { ...feed, error: 'Offline', data: [approved(42), approved()] }
  view.rerender(<View />)
  expect(screen.getByText(/Saved feed information may be out of date/)).toBeInTheDocument()
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  feed = { ...feed, error: null }
  view.rerender(<View />)
  expect(screen.getByLabelText('New alert for Suva')).toBeInTheDocument()
})

it.each(['demo', 'sample prediction'])('labels %s alerts clearly in both tray and new notice', (source) => {
  const view = render(<View />)
  feed = { ...feed, data: [sampleAlert({ id: 42, status: 'APPROVED', is_demo: source === 'demo',
    prediction: source === 'sample prediction' ? {
      id: 1, risk_level: 'HIGH', flood_probability: 0.9, confidence_percent: 90,
      model_version: 'sample', is_sample: true, predicted_at: '2026-10-14T00:00:00Z',
    } : null })] }
  view.rerender(<View />)
  expect(within(screen.getByLabelText('New simulated alert for Suva')).getByText(/Not an emergency warning/)).toBeInTheDocument()
  expect(inbox().getByText(/Not an emergency warning/)).toBeInTheDocument()
})

it('keeps read actions working in memory when storage is unavailable or corrupt', async () => {
  localStorage.setItem(inAppStorageKey('guest'), '{broken')
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled') })
  render(<View />)
  const tray = inbox()
  expect(tray.getByText(/Notification history cannot be saved/)).toBeInTheDocument()
  await userEvent.click(tray.getByRole('button', { name: 'Mark all as read' }))
  expect(screen.getByText('0 unread')).toBeInTheDocument()
})

it('opens the matching public alert and marks it read without a delivery receipt', async () => {
  render(<View />)
  const link = inbox().getByRole('link', { name: 'View alert for Suva' })
  expect(link).toHaveAttribute('href', '/alerts#alert-41')
  await userEvent.click(link)
  expect(screen.getByRole('heading', { name: 'Public alert details' })).toBeInTheDocument()
  expect(document.activeElement).toBe(document.getElementById('alert-41'))
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  expect(link.closest('details')).not.toHaveAttribute('open')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('uses shared refresh and announces severity escalation, limiting visible notices to three', async () => {
  const view = render(<View />)
  await userEvent.click(inbox().getByRole('button', { name: 'Refresh inbox' }))
  expect(feed.refresh).toHaveBeenCalledOnce()
  feed = { ...feed, data: [sampleAlert({ ...approved(), severity: 'VERY_HIGH' }), ...[42, 43, 44, 45].map(approved)] }
  view.rerender(<View />)
  expect(screen.getByText('5 unread')).toBeInTheDocument()
  expect(screen.getAllByLabelText('New alert for Suva')).toHaveLength(3)
})

it('removes an expired notice and unread count on the next feed render', () => {
  const now = Date.now()
  const view = render(<View />)
  feed = { ...feed, data: [sampleAlert({ ...approved(42), expires_at: new Date(now + 60_000).toISOString() })] }
  view.rerender(<View />)
  expect(screen.getByLabelText('New alert for Suva')).toBeInTheDocument()
  vi.spyOn(Date, 'now').mockReturnValue(now + 60_001)
  feed = { ...feed, data: [...feed.data!] }
  view.rerender(<View />)
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  expect(screen.getByText('0 unread')).toBeInTheDocument()
})

it('only notifies approved signed-in users about active saved locations', async () => {
  signIn()
  const view = render(<View />)
  await screen.findByText('1 unread')
  expect(getSavedLocations).toHaveBeenCalledWith('fixture-only', expect.any(AbortSignal))
  feed = { ...feed, data: [approved(), approved(42), sampleAlert({ ...approved(43), location_id: 2, location: { id: 2, name: 'Nadi', is_active: true } })] }
  view.rerender(<View />)
  await screen.findByLabelText('New alert for Suva')
  expect(screen.getByText('2 unread')).toBeInTheDocument()
  expect(screen.queryByLabelText('New alert for Nadi')).not.toBeInTheDocument()
  expect(inbox().getByText(/for your saved locations/)).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('pauses authenticated notifications on subscription failures and never falls back to public locations', async () => {
  signIn()
  vi.mocked(getSavedLocations).mockRejectedValue(new Error('Unauthorized'))
  const view = render(<View />)
  expect(await screen.findByText(/Saved locations are unavailable/)).toBeInTheDocument()
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  await locationsReady()
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  expect(requestPermission).not.toHaveBeenCalled()
})

it('does not notify pending accounts or users with no saved active locations', async () => {
  signIn()
  vi.mocked(useAuth).mockReturnValue({ ...useAuth(), user: { ...sampleAdmin, status: 'PENDING' } })
  const view = render(<View />)
  expect(screen.getByText(/Sign in with an approved account/)).toBeInTheDocument()
  expect(getSavedLocations).not.toHaveBeenCalled()
  signIn()
  vi.mocked(getSavedLocations).mockResolvedValue([{ id: 1, name: 'Suva', is_active: false }])
  view.rerender(<View />)
  await locationsReady()
  expect(screen.getByText('0 unread')).toBeInTheDocument()
})

it('does not announce existing alerts when saving another location', async () => {
  signIn()
  vi.mocked(getSavedLocations).mockResolvedValue([])
  const view = render(<View />)
  await locationsReady()
  vi.mocked(getSavedLocations).mockResolvedValue([{ id: 1, name: 'Suva', is_active: true }])
  feed = { ...feed, data: [approved()] }
  view.rerender(<View />)
  await screen.findByText('1 unread')
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
})

it('does not repeat a previously announced alert after it disappears or after a reload', async () => {
  let view = render(<View />)
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  expect(screen.getByLabelText('New alert for Suva')).toBeInTheDocument()
  feed = { ...feed, data: [] }
  view.rerender(<View />)
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
  view.unmount()
  feed = { ...feed, data: [] }
  view = render(<View />)
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  expect(screen.queryByLabelText('New alert for Suva')).not.toBeInTheDocument()
})

it('keeps a verified banner mounted while checking subscriptions on the next poll', async () => {
  signIn()
  const view = render(<View />)
  await locationsReady()
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  const notice = await screen.findByLabelText('New alert for Suva')
  let resolveLocations!: (rows: Awaited<ReturnType<typeof getSavedLocations>>) => void
  vi.mocked(getSavedLocations).mockReturnValueOnce(new Promise(resolve => { resolveLocations = resolve }))
  feed = { ...feed, data: [approved(42)] }
  view.rerender(<View />)
  expect(screen.getByLabelText('New alert for Suva')).toBe(notice)
  await act(async () => { resolveLocations([{ id: 1, name: 'Suva', is_active: true }]) })
  expect(screen.getByLabelText('New alert for Suva')).toBe(notice)
})
