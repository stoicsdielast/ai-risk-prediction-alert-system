import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Brand } from './Brand'

function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <Brand compact />

          <nav className="app-nav" aria-label="Primary navigation">
            <NavLink to="/dashboard">Overview</NavLink>
            {user.role === 'MET_ADMIN' && (
              <NavLink to="/admin/users/pending">Account review</NavLink>
            )}
          </nav>

          <div className="user-menu">
            <div className="user-avatar" aria-hidden="true">
              {initials(user.name)}
            </div>
            <div className="user-menu__copy">
              <strong>{user.name}</strong>
              <small>{user.role === 'MET_ADMIN' ? 'MET administrator' : 'Community user'}</small>
            </div>
            <button className="text-button" type="button" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
