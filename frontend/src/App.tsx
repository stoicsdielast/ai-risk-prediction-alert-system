import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import './App.css'
import './public-auth.css'
import './prototype.css'
import './analytics.css'
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
import { SyntheticResearchPage } from './pages/SyntheticResearchPage'

const SyntheticReplay = lazy(() => import('./components/research/SyntheticReplay').then(m => ({ default: m.SyntheticReplay })))

// Charts pull in Recharts, so the analytics pages load on demand rather than in the main bundle.
const AdminAnalyticsPage = lazy(() => import('./pages/AdminAnalyticsPage').then((m) => ({ default: m.AdminAnalyticsPage })))
const AdminModelPerformancePage = lazy(() =>
  import('./pages/AdminModelPerformancePage').then((m) => ({ default: m.AdminModelPerformancePage })))
const lazyPage = (page: React.ReactNode) => <Suspense fallback={<p role="status">Loading…</p>}>{page}</Suspense>

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
        <Route path="simulation" element={lazyPage(<SyntheticReplay />)} />
        <Route path="research" element={<SyntheticResearchPage />} />
        <Route path="alerts" element={<CommunityAlertsPage />} />

        <Route element={<RequireAuth />}>
          <Route path="dashboard" element={<DashboardPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="admin/dashboard" element={<AdminDashboardPage />} />
            <Route path="admin/analytics" element={lazyPage(<AdminAnalyticsPage />)} />
            <Route path="admin/model-performance" element={lazyPage(<AdminModelPerformancePage />)} />
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
