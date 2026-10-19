import { Route, Routes } from 'react-router-dom'
import './App.css'
import './public-auth.css'
import './prototype.css'
import { PublicOnlyRoute, RequireAdmin, RequireAuth } from './auth/RouteGuards'
import { AuthLayout } from './components/AuthLayout'
import { WorkspaceLayout } from './components/layout/WorkspaceLayout'
import { AdminDashboardPage } from './pages/AdminDashboardPage'
import { AdminUsersPage } from './pages/AdminUsersPage'
import { AlertsDashboardPage } from './pages/AlertsDashboardPage'
import { CommunityAlertsPage } from './pages/CommunityAlertsPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RegisterPage } from './pages/RegisterPage'
import { RegistrationSubmittedPage } from './pages/RegistrationSubmittedPage'
import { WeatherMapPage } from './pages/WeatherMapPage'
import { WelcomePage } from './pages/WelcomePage'
import { SyntheticReplay } from './components/research/SyntheticReplayPanel'

function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route index element={<WelcomePage />} />
        <Route path="login" element={<LoginPage />} />

        <Route element={<AuthLayout />}>
          <Route path="register" element={<RegisterPage />} />
          <Route
            path="registration-submitted"
            element={<RegistrationSubmittedPage />}
          />
        </Route>
      </Route>

      <Route element={<WorkspaceLayout />}>
        <Route path="weather-map" element={<WeatherMapPage />} />
        <Route path="simulation" element={<SyntheticReplay />} />
        <Route path="alerts" element={<CommunityAlertsPage />} />

        <Route element={<RequireAuth />}>
          <Route path="dashboard" element={<DashboardPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="admin/dashboard" element={<AdminDashboardPage />} />
            <Route path="admin/alerts" element={<AlertsDashboardPage />} />
            <Route path="admin/users/pending" element={<AdminUsersPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
