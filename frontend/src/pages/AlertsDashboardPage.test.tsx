import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../auth/AuthProvider'
import { installAlertApi, sampleAlert } from '../test/alertApiFixture'

function renderApp(path = '/admin/alerts') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}
const details = () => within(screen.getByRole('complementary', { name: 'Selected alert details' }))

beforeEach(() => {
  sessionStorage.setItem('fiji-flood-access-token', 'test-token')
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('persisted alert management', () => {
  it('loads every status and sends the bearer token', async () => {
    const { fetchMock } = installAlertApi([
      sampleAlert(),
      sampleAlert({ id: 42, status: 'REJECTED' }),
    ])
    renderApp()
    await screen.findByRole('button', { name: /Rejected 1/ })
    expect(details().getByText('TEST ONLY: Move to higher ground.')).toBeInTheDocument()
    const reads = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/admin/alerts'))
    expect(reads).toHaveLength(6)
    expect(
      reads.every(
        ([, options]) => new Headers(options?.headers).get('Authorization') === 'Bearer test-token',
      ),
    ).toBe(true)
  })

  it('creates and edits a draft, retaining the saved data after remount', async () => {
    const user = userEvent.setup()
    const { state, fetchMock } = installAlertApi([])
    const first = renderApp()
    await user.click(await screen.findByRole('button', { name: 'New alert' }))
    await screen.findByRole('option', { name: 'Suva' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Location' }), '1')
    await user.type(
      screen.getByRole('textbox', { name: 'Alert message' }),
      'TEST ONLY: River watch.',
    )
    await user.click(screen.getByRole('button', { name: 'Create draft' }))
    await screen.findByText('Alert draft created.')
    expect(state.alerts[0]).toMatchObject({
      location_id: 1,
      message: 'TEST ONLY: River watch.',
      status: 'PENDING',
    })
    await user.click(details().getByRole('button', { name: 'Edit alert' }))
    await user.clear(screen.getByRole('textbox', { name: 'Alert message' }))
    await user.type(
      screen.getByRole('textbox', { name: 'Alert message' }),
      'TEST ONLY: Updated warning.',
    )
    await user.selectOptions(screen.getByRole('combobox', { name: 'Severity' }), 'VERY_HIGH')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByText('Alert changes saved.')
    const patch = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      message: 'TEST ONLY: Updated warning.',
      severity: 'VERY_HIGH',
    })
    first.unmount()
    renderApp()
    await screen.findByRole('button', { name: /Pending 1/ })
    expect(details().getByText('TEST ONLY: Updated warning.')).toBeInTheDocument()
  })

  it.each(['Approve', 'Reject'] as const)(
    '%s changes status through the API and disables further review',
    async (action) => {
      const user = userEvent.setup()
      const { state } = installAlertApi()
      renderApp()
      await screen.findByRole('button', { name: /Pending 1/ })
      await user.click(details().getByRole('button', { name: action }))
      await screen.findByText(`Alert #41 ${action === 'Approve' ? 'approved' : 'rejected'}.`)
      expect(state.alerts[0].status).toBe(action === 'Approve' ? 'APPROVED' : 'REJECTED')
      expect(details().getByRole('button', { name: 'Approve' })).toBeDisabled()
      expect(details().getByRole('button', { name: 'Edit alert' })).toBeDisabled()
    },
  )

  it('requires a nonblank suppression reason and shows the saved reason', async () => {
    const user = userEvent.setup()
    const { fetchMock } = installAlertApi([
      sampleAlert({ status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' }),
    ])
    renderApp()
    await screen.findByRole('button', { name: /Approved 1/ })
    const button = details().getByRole('button', { name: 'Suppress' })
    expect(button).toBeDisabled()
    await user.type(details().getByRole('textbox', { name: 'Action reason' }), '   ')
    expect(button).toBeDisabled()
    await user.type(
      details().getByRole('textbox', { name: 'Action reason' }),
      'Test-only warning withdrawn.  ',
    )
    await user.click(button)
    await screen.findByText('Alert #41 suppressed.')
    expect(details().getByText('Test-only warning withdrawn.')).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/suppress'))
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ reason: 'Test-only warning withdrawn.' })
  })

  it('does not send an action when confirmation is cancelled', async () => {
    vi.mocked(window.confirm).mockReturnValue(false)
    const user = userEvent.setup()
    const { fetchMock } = installAlertApi()
    renderApp()
    await screen.findByRole('button', { name: /Pending 1/ })
    await user.click(details().getByRole('button', { name: 'Approve' }))
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })

  it.each([400, 409, 500])(
    'shows HTTP %s action failures without claiming success',
    async (status) => {
      const user = userEvent.setup()
      const { state } = installAlertApi()
      renderApp()
      await screen.findByRole('button', { name: /Pending 1/ })
      state.failure = {
        path: '/api/admin/alerts/41/approve',
        status,
        detail: 'Test-only action failure',
      }
      await user.click(details().getByRole('button', { name: 'Approve' }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Test-only action failure')
      expect(screen.queryByText('Alert #41 approved.')).not.toBeInTheDocument()
      expect(state.alerts[0].status).toBe('PENDING')
      expect(details().getByRole('button', { name: 'Approve' })).toBeEnabled()
    },
  )

  it('allows a failed initial load to be retried', async () => {
    const user = userEvent.setup()
    const { state } = installAlertApi()
    state.failure = {
      path: '/api/admin/alerts',
      status: 500,
      detail: 'Test-only service unavailable',
    }
    renderApp()
    expect(await screen.findByRole('alert')).toHaveTextContent('Test-only service unavailable')
    await user.click(screen.getByRole('button', { name: 'Refresh alerts' }))
    await screen.findByRole('button', { name: /Pending 1/ })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([401, 403])(
    'clears the session on HTTP %s and explains why sign-in is needed',
    async (status) => {
      const user = userEvent.setup()
      const { state } = installAlertApi()
      renderApp()
      await screen.findByRole('button', { name: /Pending 1/ })
      state.failure = {
        path: '/api/admin/alerts/41/approve',
        status,
        detail: 'Expired or forbidden',
      }
      await user.click(details().getByRole('button', { name: 'Approve' }))
      await waitFor(() => expect(sessionStorage.getItem('fiji-flood-access-token')).toBeNull())
      expect(await screen.findByRole('alert')).toHaveTextContent(
        status === 401 ? 'Your session expired' : 'no longer has access',
      )
      expect(screen.queryByRole('heading', { name: 'Alert management' })).not.toBeInTheDocument()
    },
  )

  it('denies community users access to management without requesting private alerts', async () => {
    const { state, fetchMock } = installAlertApi()
    state.user.role = 'COMMUNITY'
    renderApp()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'MET administrator access is required',
    )
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/admin/alerts'))).toBe(
      false,
    )
    expect(screen.queryByRole('button', { name: 'New alert' })).not.toBeInTheDocument()
  })

  it('sends anonymous management visitors to sign-in', async () => {
    sessionStorage.clear()
    const { fetchMock } = installAlertApi()
    renderApp()
    await screen.findByRole('button', { name: /Sign in/i })
    // The shared public feed may start before the route guard redirects.
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/admin/'))).toBe(false)
    expect(fetchMock.mock.calls.every(([, options]) => !new Headers(options?.headers).has('Authorization'))).toBe(true)
  })

  it.each(['Resolve', 'Cancel alert'])('confirms %s and keeps the closed record in history', async (action) => {
    const user = userEvent.setup()
    installAlertApi([sampleAlert({ status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' })])
    renderApp()
    await screen.findByRole('button', { name: /Approved 1/ })
    await user.click(screen.getByRole('button', { name: 'Active alerts' }))
    expect(details().getByRole('button', { name: action })).toBeDisabled()
    await user.type(details().getByRole('textbox', { name: 'Action reason' }), 'Test exercise ended')
    vi.mocked(window.confirm).mockReturnValue(false)
    await user.click(details().getByRole('button', { name: action }))
    expect(details().getByText('TEST ONLY: Move to higher ground.')).toBeInTheDocument()
    vi.mocked(window.confirm).mockReturnValue(true)
    await user.click(details().getByRole('button', { name: action }))
    await screen.findByText(`Alert #41 ${action === 'Resolve' ? 'resolved' : 'cancelled'}.`)
    expect(screen.queryByRole('button', { name: action })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Alert history' }))
    expect(details().getByText(/Test exercise ended/)).toBeInTheDocument()
    expect(details().getByText(/Administrator #7/)).toBeInTheDocument()
  })

  it('shows expired alerts in history and allows acknowledgement only for current approved alerts', async () => {
    const user = userEvent.setup()
    installAlertApi([sampleAlert({ status: 'APPROVED', expires_at: '2020-01-01T00:00:00Z' })])
    renderApp()
    await screen.findByRole('button', { name: /Approved 1/ })
    expect(details().queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Active alerts' }))
    expect(details().getByText('Select an alert')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Alert history' }))
    expect(details().getByText('Expired', { exact: true })).toBeInTheDocument()
  })

  it('acknowledges an active alert without closing it', async () => {
    const user = userEvent.setup()
    installAlertApi([sampleAlert({ status: 'APPROVED' })])
    renderApp()
    await user.click(await screen.findByRole('button', { name: 'Acknowledge' }))
    await screen.findByText('Alert #41 acknowledged.')
    expect(details().getByRole('button', { name: 'Acknowledged' })).toBeDisabled()
    expect(details().getByText('Approved', { exact: true, selector: '.data-pill' })).toBeInTheDocument()
  })

  it('uses API counts on the admin dashboard, including only public active alerts', async () => {
    installAlertApi([
      sampleAlert(),
      sampleAlert({ id: 42 }),
      sampleAlert({ id: 43, status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' }),
      sampleAlert({
        id: 44,
        status: 'APPROVED',
        location: { id: 2, name: 'Inactive fixture', is_active: false },
      }),
    ])
    renderApp('/admin/dashboard')
    await waitFor(() =>
      expect(
        screen.getByText('Pending alerts').parentElement?.querySelector('strong'),
      ).toHaveTextContent('2'),
    )
    expect(
      screen.getByText('Active alerts').parentElement?.querySelector('strong'),
    ).toHaveTextContent('1')
  })
})
