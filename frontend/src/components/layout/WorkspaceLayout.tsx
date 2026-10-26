import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { DataSourceStatus } from './DataSourceStatus'
import { Sidebar } from './Sidebar'
import { PublicAlertProvider } from '../../alerts/PublicAlertProvider'
import { BrowserAlertControl } from '../alerts/BrowserAlertControl'
import { ApprovedAlertBanner } from '../alerts/ApprovedAlertBanner'
import { InAppAlerts } from '../alerts/InAppAlerts'

export function WorkspaceLayout() {
  const { user } = useAuth()
  const location = useLocation()
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const syntheticView = ['/simulation', '/research'].includes(location.pathname)
  const dataBadge = <DataSourceStatus key={location.pathname} synthetic={syntheticView} />

  return (
    <PublicAlertProvider>
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
          <BrowserAlertControl />
          <InAppAlerts />
          <ApprovedAlertBanner />
          <Outlet />
        </main>
      </div>
    </div>
    </PublicAlertProvider>
  )
}
