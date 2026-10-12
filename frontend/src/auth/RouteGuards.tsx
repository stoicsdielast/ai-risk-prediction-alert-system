import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { LoadingScreen } from '../components/LoadingScreen'
import { SessionErrorScreen } from '../components/SessionErrorScreen'
import { useAuth } from './useAuth'

export function PublicOnlyRoute() {
  const { user, token, isLoading, sessionError } = useAuth()

  if (isLoading) return <LoadingScreen />
  if (token && sessionError) return <SessionErrorScreen />
  if (!user) return <Outlet />

  return (
    <Navigate
      to={user.role === 'MET_ADMIN' ? '/admin/dashboard' : '/dashboard'}
      replace
    />
  )
}

export function RequireAuth() {
  const { user, token, isLoading, sessionError } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingScreen />
  if (token && sessionError) return <SessionErrorScreen />

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

export function RequireAdmin() {
  const { user } = useAuth()

  if (user?.role !== 'MET_ADMIN') {
    return (
      <Navigate
        to="/dashboard"
        replace
        state={{ accessDenied: 'MET administrator access is required.' }}
      />
    )
  }

  return <Outlet />
}
