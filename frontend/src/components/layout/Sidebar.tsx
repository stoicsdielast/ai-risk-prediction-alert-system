import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { Brand } from '../Brand'
import { SidebarIcon } from './SidebarIcon'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isAdmin = user?.role === 'MET_ADMIN'

  const handleLogout = () => {
    logout()
    onClose()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <button
        className={`sidebar-backdrop${isOpen ? ' is-visible' : ''}`}
        type="button"
        aria-label="Close navigation"
        onClick={onClose}
      />
      <aside className={`workspace-sidebar${isOpen ? ' is-open' : ''}`}>
        <div className="workspace-sidebar__brand">
          <Brand inverse />
          <button type="button" aria-label="Close navigation" onClick={onClose}>×</button>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          <span className="sidebar-nav__label">Workspace</span>

          {isAdmin && (
            <NavLink to="/admin/dashboard" onClick={onClose}>
              <SidebarIcon name="dashboard" />
              <span>Dashboard</span>
            </NavLink>
          )}

          {!isAdmin && user && (
            <NavLink to="/dashboard" onClick={onClose}>
              <SidebarIcon name="account" />
              <span>My overview</span>
            </NavLink>
          )}

          <NavLink to="/weather-map" onClick={onClose}>
            <SidebarIcon name="map" />
            <span>Weather map</span>
          </NavLink>

          {isAdmin && (
            <NavLink to="/admin/alerts" onClick={onClose}>
              <SidebarIcon name="alerts" />
              <span>Alerts</span>
            </NavLink>
          )}

          {isAdmin && (
            <NavLink to="/admin/users/pending" onClick={onClose}>
              <SidebarIcon name="users" />
              <span>Users / Admin</span>
            </NavLink>
          )}
        </nav>

        <div className="workspace-sidebar__footer">
          {user ? (
            <>
              <div className="sidebar-user">
                <span aria-hidden="true">{user.name.slice(0, 1).toUpperCase()}</span>
                <div><strong>{user.name}</strong><small>{isAdmin ? 'MET administrator' : 'Community user'}</small></div>
              </div>
              <button className="sidebar-logout" type="button" onClick={handleLogout}>
                <SidebarIcon name="logout" /> Log out
              </button>
            </>
          ) : (
            <div className="sidebar-guest">
              <p>Sign in to access protected dashboards and account tools.</p>
              <NavLink to="/login" onClick={onClose}>
                <SidebarIcon name="login" /> Sign in
              </NavLink>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
