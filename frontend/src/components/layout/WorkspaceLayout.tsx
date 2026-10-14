import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { PrototypeBadge } from './PrototypeBadge'
import { Sidebar } from './Sidebar'

export function WorkspaceLayout() {
  const { user } = useAuth()
  const location = useLocation()
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const usesLiveAuthData =
    location.pathname === '/dashboard' ||
    location.pathname === '/admin/users/pending'

  const dataBadge = usesLiveAuthData ? (
    <span className="live-api-badge">
      <span aria-hidden="true" /> Live auth API
    </span>
  ) : location.pathname === '/alerts' || location.pathname === '/admin/alerts' ? (
    <span className="live-api-badge"><span aria-hidden="true" /> Live alerts</span>
  ) : (
    <PrototypeBadge />
  )

  return (
    <div className="workspace-shell">
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
      <div className="workspace-content">
        <header className="workspace-mobile-bar">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setIsSidebarOpen(true)}
          >
            <span /> <span /> <span />
          </button>
          <strong>FloodWatch Fiji</strong>
          {dataBadge}
        </header>
        <div className="workspace-utility-bar">
          <span>{user ? `Signed in as ${user.name}` : 'Public community information'}</span>
          {dataBadge}
        </div>
        <main className="workspace-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
