import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'

interface LoginLocationState {
  from?: string
}

type LoginFeedbackKind = 'error' | 'pending' | 'rejected' | 'inactive'

interface LoginFeedback {
  kind: LoginFeedbackKind
  label?: string
  message: string
}

function feedbackForError(caughtError: unknown): LoginFeedback {
  if (!(caughtError instanceof ApiError)) {
    return {
      kind: 'error',
      message: 'Unable to sign in. Please try again.',
    }
  }

  if (caughtError.status === 401) {
    return {
      kind: 'error',
      message: 'Invalid email or password.',
    }
  }

  const detail = caughtError.message.toLowerCase()

  if (caughtError.status === 403 && detail.includes('pending')) {
    return {
      kind: 'pending',
      label: 'Pending approval',
      message: 'Your account is awaiting approval from a Fiji MET administrator.',
    }
  }

  if (caughtError.status === 403 && detail.includes('rejected')) {
    return {
      kind: 'rejected',
      label: 'Account rejected',
      message: 'This account request was rejected. Contact a Fiji MET administrator for help.',
    }
  }

  if (caughtError.status === 403 && detail.includes('inactive')) {
    return {
      kind: 'inactive',
      label: 'Account inactive',
      message: 'This account is inactive. Contact a Fiji MET administrator to restore access.',
    }
  }

  return {
    kind: 'error',
    message: caughtError.message,
  }
}

function FieldIcon({ name }: { name: 'email' | 'password' }) {
  if (name === 'email') {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2.5" />
        <path d="m4 7 8 6 8-6" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="10" width="16" height="11" rx="2.5" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14.5v2" />
    </svg>
  )
}

export function LoginPage() {
  const { login, sessionError } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [feedback, setFeedback] = useState<LoginFeedback | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const displayedFeedback: LoginFeedback | null = feedback ?? (
    !isSubmitting && sessionError ? { kind: 'error', message: sessionError } : null
  )

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFeedback(null)
    setIsSubmitting(true)

    try {
      const user = await login({ email, password })
      const requestedPath = (location.state as LoginLocationState | null)?.from
      const destination =
        requestedPath ||
        (user.role === 'MET_ADMIN' ? '/admin/dashboard' : '/dashboard')
      navigate(destination, { replace: true })
    } catch (caughtError) {
      setFeedback(feedbackForError(caughtError))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="About the flood-risk system">
        <Link className="login-brand" to="/" aria-label="Fiji Meteorological Service home">
          <img src="/fijimetlogo.svg" alt="" />
          <span>
            <strong>Fiji Meteorological Service</strong>
            <small>Government of the Republic of Fiji</small>
          </span>
        </Link>

        <div className="login-brand-panel__content">
          <span className="login-brand-panel__kicker">AI-powered decision support</span>
          <h1>
            Flood Risk Prediction
            <span>&amp; Community Alert System</span>
          </h1>
          <p>
            AI-powered decision support for flood-risk monitoring and community
            alert management across Fiji.
          </p>
          <div className="login-brand-panel__pills" aria-label="System capabilities">
            <span>Fiji MET</span>
            <span>Flood intelligence</span>
            <span>Secure access</span>
          </div>
        </div>

        <p className="login-brand-panel__footer">
          FloodWatch Fiji · Flood monitoring & community alerts
        </p>
      </section>

      <section className="login-form-panel">
        <Link className="login-mobile-brand" to="/" aria-label="Fiji Meteorological Service home">
          <img src="/fijimetlogo.svg" alt="" />
          <span>
            <strong>Fiji Meteorological Service</strong>
            <small>Flood Risk System</small>
          </span>
        </Link>

        <div className="login-form-card">
          <Link className="login-back-link" to="/">
            <span aria-hidden="true">←</span> Back to home
          </Link>

          <header className="login-form-card__header">
            <span>Secure system access</span>
            <h2>Welcome back</h2>
            <p>Sign in to access your Fiji MET flood-risk dashboard.</p>
          </header>

          {displayedFeedback && (
            <div
              className={`login-feedback login-feedback--${displayedFeedback.kind}`}
              role="alert"
            >
              {displayedFeedback.label && (
                <span className="login-feedback__pill">{displayedFeedback.label}</span>
              )}
              <p>{displayedFeedback.message}</p>
            </div>
          )}

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="login-field" htmlFor="login-email">
              <span>Email address</span>
              <div className="login-field__control">
                <FieldIcon name="email" />
                <input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>
            </label>

            <label className="login-field" htmlFor="login-password">
              <span>Password</span>
              <div className="login-field__control">
                <FieldIcon name="password" />
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  className="login-password-toggle"
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((currentValue) => !currentValue)}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>

            <button
              className="login-submit"
              type="submit"
              disabled={isSubmitting}
              aria-busy={isSubmitting}
            >
              {isSubmitting && <span className="login-submit__spinner" aria-hidden="true" />}
              {isSubmitting ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <p className="login-register-link">
            Need an account? <Link to="/register">Request access</Link>
          </p>
          <p className="login-help-text">
            Only approved and active accounts can access protected dashboards.
          </p>
        </div>

        <p className="login-form-panel__footer">
          Secure access for authorised Fiji MET and community users
        </p>
      </section>
    </main>
  )
}
